# -*- coding: utf-8 -*-
"""政策与公告双维度排雷专属 Executor（α 公告 + β 政策 并行 → Ω 综合裁决）。

复用同一套基建：
- :func:`src.agent.runner.run_agent_loop` —— ReAct 工具循环（通过 DI ``loop_runner`` 注入，便于单测）
- :class:`src.agent.llm_adapter.LLMToolAdapter` —— 多渠道 LLM
- :func:`src.services.policy_minesweeper_scorecard.score` —— 确定性评分（Ω 通过工具调用）

与 deep_research 的差异：
- **三 Agent 并行裁决**：α/β 用 ``ThreadPoolExecutor`` 并行，Ω 串行综合。
- **DI 注入 loop_runner**：默认 ``_default_loop``（lazy import run_agent_loop）；
  测试可注入 fake，使编排/降级逻辑 100% 可测，无需 monkeypatch 局部 import。
- 无 validator / 无重试：评分工具确定性输出即结构保证；任一环节失败走降级。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # 避免 import 时强依赖 litellm（部署环境才有）
    from src.agent.llm_adapter import LLMToolAdapter
    from src.agent.runner import RunLoopResult
    from src.agent.tools.registry import ToolRegistry

from src.services.policy_minesweeper_scorecard import DISCLAIMER

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SYSTEM_PROMPT_PATH = os.path.join(_PROJECT_ROOT, "data", "policy_minesweeper", "system_prompt.md")

# system_prompt.md 缺失时的兜底（保证不崩；完整方法论在文件中）
_FALLBACK_SYSTEM_PROMPT = (
    "你是 A 股政策与公告双维度排雷分析师。三角色共享本方法论："
    "α-公司公告扫描器（微观 8 维）、β-国家政策分析师（宏观 6 维 + 政策-业务映射 + DCF 三要素）、"
    "Ω-综合裁决器（信号一致性 + 主导因子 + 时间窗权重）。"
    "所有结论用证据锚定（来源+日期），不编造；预期冲击为历史经验区间，非预测。"
    "（注：完整 system_prompt.md 加载失败，使用兜底提示。）"
)

# 角色职责（注入 system prompt 末尾；方法论由 system_prompt.md 共享）
_ALPHA_ROLE = (
    "\n\n## 你的角色：α-公司公告与经营事件扫描器\n"
    "只做公司微观层面。调用公告/新闻/基本面工具（search_stock_news / "
    "search_comprehensive_intel / get_stock_info / get_realtime_quote），按 8 维扫描："
    "事件性质、超预期程度、盈利影响、合规风险、股东行为、资本运作、行业地位、历史可比。\n"
    "产出：micro_score（-100~+100）+ 关键事件清单 + 证据（来源+日期）。"
    "禁止做宏观政策分析（那是 β 的职责）。"
)
_BETA_ROLE = (
    "\n\n## 你的角色：β-国家政策与产业互动分析师\n"
    "只做宏观/政策层面。调用政策/产业/板块工具（search_comprehensive_intel / "
    "get_sector_rankings / get_stock_info），按 6 维评估：政策方向、超预期程度、"
    "业务暴露度、传导时滞、竞争格局、政策持续性；并做政策-业务映射与 DCF 三要素"
    "（现金流规模/时间/折现率）的定性影响。\n"
    "产出：macro_score（-100~+100）+ 政策-业务暴露度映射 + 证据（来源+日期）。"
    "禁止做公司公告微观分析（那是 α 的职责）。"
)
_OMEGA_ROLE = (
    "\n\n## 你的角色：Ω-综合裁决器\n"
    "综合 α 报告与 β 报告，做信号一致性检验（共振/冲突）、主导因子判定、"
    "按时间窗口动态权重（short α0.7/β0.3，medium 0.5/0.5，long α0.3/β0.7）。\n"
    "然后**必须调用 score_policy_minesweeper 工具**给出六维评分、综合分（-100~+100）、"
    "5 档等级、仓位指令、预期冲击区间与情景分析，并据此输出最终排雷 Markdown。"
    "报告末尾必须包含免责声明。"
)


def _load_system_prompt() -> str:
    """读取 data/policy_minesweeper/system_prompt.md；缺失走兜底。"""
    try:
        with open(_SYSTEM_PROMPT_PATH, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("[PolicyMinesweeper] system_prompt.md 读取失败 (%s): %s", _SYSTEM_PROMPT_PATH, exc)
        return _FALLBACK_SYSTEM_PROMPT


def _default_loop(role: str, **kwargs: Any) -> "RunLoopResult":
    """默认 loop_runner：lazy import run_agent_loop（忽略 role 标记）。"""
    from src.agent.runner import run_agent_loop

    return run_agent_loop(**kwargs)


@dataclass
class PolicyMinesweeperResult:
    """政策与公告双维度排雷生成结果。"""

    success: bool = False
    status: str = "failed"  # success | partial | failed
    markdown: str = ""
    stock_code: str = ""
    stock_name: str = ""
    horizon: str = "medium"
    alpha_ok: bool = False
    beta_ok: bool = False
    omega_ok: bool = False
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    error: Optional[str] = None


class PolicyMinesweeperExecutor:
    """政策与公告双维度排雷专属 Agent（α/β 并行 → Ω 综合）。"""

    def __init__(
        self,
        tool_registry: "ToolRegistry",
        llm_adapter: "LLMToolAdapter",
        *,
        max_steps_ab: int = 10,
        max_steps_omega: int = 6,
        wall_ab: float = 300.0,
        wall_omega: float = 240.0,
        max_workers: int = 2,
        loop_runner: Optional[Callable[..., "RunLoopResult"]] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.max_steps_ab = max_steps_ab
        self.max_steps_omega = max_steps_omega
        self.wall_ab = wall_ab
        self.wall_omega = wall_omega
        self.max_workers = max_workers
        self._loop = loop_runner or _default_loop
        self._system_prompt = system_prompt

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def generate(
        self,
        stock_code: str,
        stock_name: str,
        horizon: str = "medium",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> PolicyMinesweeperResult:
        """生成一份政策与公告双维度排雷报告（α/β 并行 → Ω 综合 + 降级）。"""
        cb = progress_callback or (lambda _e: None)
        base = self._system_prompt if self._system_prompt is not None else _load_system_prompt()

        _emit(cb, "thinking", f"开始对 {stock_name}（{stock_code}）政策与公告双维度排雷（窗口 {horizon}）…")

        alpha_msgs = _build_messages(base, _ALPHA_ROLE, stock_code, stock_name, horizon)
        beta_msgs = _build_messages(base, _BETA_ROLE, stock_code, stock_name, horizon)

        _emit(cb, "thinking", "▸公告扫描（α）与 ▸政策分析（β）并行进行中…")
        alpha_result, beta_result = self._run_parallel(alpha_msgs, beta_msgs, cb)

        omega_msgs = _build_omega_messages(
            base, stock_code, stock_name, horizon, alpha_result, beta_result
        )
        _emit(cb, "thinking", "▸综合裁决（Ω）进行中…")
        omega_result = self._loop_safe("omega", omega_msgs, self.max_steps_omega, self.wall_omega, cb)

        return self._assemble(
            stock_code, stock_name, horizon, alpha_result, beta_result, omega_result
        )

    # ------------------------------------------------------------------
    # 并行 + 安全包装
    # ------------------------------------------------------------------

    def _run_parallel(
        self,
        alpha_msgs: List[Dict[str, Any]],
        beta_msgs: List[Dict[str, Any]],
        cb: Callable[[Dict[str, Any]], None],
    ) -> Tuple["RunLoopResult", "RunLoopResult"]:
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            fa = pool.submit(self._loop_safe, "alpha", alpha_msgs, self.max_steps_ab, self.wall_ab, cb)
            fb = pool.submit(self._loop_safe, "beta", beta_msgs, self.max_steps_ab, self.wall_ab, cb)
            return fa.result(), fb.result()

    def _loop_safe(
        self,
        role: str,
        messages: List[Dict[str, Any]],
        max_steps: int,
        wall: float,
        cb: Callable[[Dict[str, Any]], None],
    ) -> "RunLoopResult":
        """单 loop 调用；异常降级为失败 RunLoopResult，不得拖垮整体。"""
        try:
            return self._loop(
                role,
                messages=messages,
                tool_registry=self.tool_registry,
                llm_adapter=self.llm_adapter,
                max_steps=max_steps,
                max_wall_clock_seconds=wall,
                progress_callback=_tagged(role, cb),
                stock_scope=None,
            )
        except Exception as exc:  # noqa: BLE001 - 单 loop 异常降级，不向上传播
            from src.agent.runner import RunLoopResult

            logger.warning("[PolicyMinesweeper] %s loop 异常: %s", role, exc)
            return RunLoopResult(success=False, error=f"{role} loop error: {exc}")

    # ------------------------------------------------------------------
    # 组装 + 降级
    # ------------------------------------------------------------------

    def _assemble(
        self,
        stock_code: str,
        stock_name: str,
        horizon: str,
        alpha_result: "RunLoopResult",
        beta_result: "RunLoopResult",
        omega_result: "RunLoopResult",
    ) -> PolicyMinesweeperResult:
        alpha_ok = _ok(alpha_result)
        beta_ok = _ok(beta_result)
        omega_ok = _ok(omega_result)

        tool_calls = (
            (alpha_result.tool_calls_log or [])
            + (beta_result.tool_calls_log or [])
            + (omega_result.tool_calls_log or [])
        )
        total_steps = alpha_result.total_steps + beta_result.total_steps + omega_result.total_steps
        total_tokens = alpha_result.total_tokens + beta_result.total_tokens + omega_result.total_tokens
        provider = next(
            (p.provider for p in (omega_result, alpha_result, beta_result) if getattr(p, "provider", "")),
            "",
        )

        if omega_ok:
            markdown = omega_result.content
            status = "success" if (alpha_ok and beta_ok) else "partial"
            error: Optional[str] = None
        elif alpha_ok or beta_ok:
            markdown = _build_degraded_report(stock_code, stock_name, alpha_result, beta_result)
            status = "partial"
            error = omega_result.error or "综合裁决失败，已降级输出公司/政策层面原始分析"
        else:
            markdown = ""
            status = "failed"
            error = (
                omega_result.error or alpha_result.error or beta_result.error
                or "排雷分析未完成（α/β/Ω 均无有效输出）"
            )

        return PolicyMinesweeperResult(
            success=(status != "failed"),
            status=status,
            markdown=markdown,
            stock_code=stock_code,
            stock_name=stock_name,
            horizon=horizon,
            alpha_ok=alpha_ok,
            beta_ok=beta_ok,
            omega_ok=omega_ok,
            tool_calls_log=tool_calls,
            total_steps=total_steps,
            total_tokens=total_tokens,
            provider=provider,
            error=error,
        )


# ==================================================================
# 模块级辅助（纯函数，便于复用与单测）
# ==================================================================

def _ok(result: Any) -> bool:
    """结果是否有效（成功且 content 非空）。"""
    content = getattr(result, "content", "")
    return bool(getattr(result, "success", False) and content and str(content).strip())


def _emit(cb: Callable[[Dict[str, Any]], None], etype: str, message: str) -> None:
    cb({"type": etype, "step": 0, "message": message})


def _tagged(role: str, cb: Callable[[Dict[str, Any]], None]) -> Callable[[Dict[str, Any]], None]:
    """给单 loop 的 progress 事件打上 agent 标记，供前端分阶段高亮。"""

    def _wrap(event: Dict[str, Any]) -> None:
        tagged = dict(event) if isinstance(event, dict) else {"type": "tool", "message": str(event)}
        tagged["agent"] = role
        cb(tagged)

    return _wrap


def _build_messages(
    base: str, role_block: str, stock_code: str, stock_name: str, horizon: str
) -> List[Dict[str, Any]]:
    return [
        {"role": "system", "content": base + role_block},
        {"role": "user", "content": _build_user_task(stock_code, stock_name, horizon)},
    ]


def _build_omega_messages(
    base: str,
    stock_code: str,
    stock_name: str,
    horizon: str,
    alpha_result: Any,
    beta_result: Any,
) -> List[Dict[str, Any]]:
    alpha_text = (
        alpha_result.content.strip()
        if _ok(alpha_result)
        else "（α 公告扫描不可用/失败，请仅基于 β 与已知信息裁决并显式标注）"
    )
    beta_text = (
        beta_result.content.strip()
        if _ok(beta_result)
        else "（β 政策分析不可用/失败，请仅基于 α 与已知信息裁决并显式标注）"
    )
    user = (
        _build_user_task(stock_code, stock_name, horizon)
        + "\n\n## α-公司公告与经营事件扫描结果\n" + alpha_text
        + "\n\n## β-国家政策与产业互动分析结果\n" + beta_text
        + "\n\n请综合以上两份分析，做信号一致性检验与主导因子判定，"
        "**必须调用 score_policy_minesweeper 工具**给出综合分、5 档等级、仓位指令、"
        "预期冲击区间与情景分析，输出最终排雷 Markdown（末尾含免责声明）。"
    )
    return [
        {"role": "system", "content": base + _OMEGA_ROLE},
        {"role": "user", "content": user},
    ]


def _build_user_task(stock_code: str, stock_name: str, horizon: str) -> str:
    return (
        f"标的：{stock_name}（{stock_code}）　时间窗口：{horizon}\n"
        "按你的角色职责完成分析，调用必要工具获取真实数据，"
        "所有结论用证据锚定（来源+日期），不编造。"
    )


def _build_degraded_report(
    stock_code: str, stock_name: str, alpha_result: Any, beta_result: Any
) -> str:
    """Ω 失败时，用 α/β 原始分析降级输出（无综合评分/仓位指令）。"""
    lines = [
        f"# 政策与公告双维度排雷：{stock_name}（{stock_code}）（综合裁决未完成）",
        "",
        "> ⚠️ **综合裁决（Ω）失败，以下为公司/政策层面的原始分析降级输出，"
        "未给出综合评分与仓位指令。**",
        "",
    ]
    if _ok(alpha_result):
        lines += ["## α-公司公告与经营事件扫描", "", alpha_result.content.strip(), ""]
    else:
        lines += ["## α-公司公告与经营事件扫描", "", "（α 扫描不可用）", ""]
    if _ok(beta_result):
        lines += ["## β-国家政策与产业互动分析", "", beta_result.content.strip(), ""]
    else:
        lines += ["## β-国家政策与产业互动分析", "", "（β 分析不可用）", ""]
    lines += ["---", DISCLAIMER, ""]
    return "\n".join(lines)
