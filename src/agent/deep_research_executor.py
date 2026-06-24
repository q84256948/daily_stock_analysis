# -*- coding: utf-8 -*-
"""深度投研报告专属 Executor（五层穿透框架）。

独立于问股 AgentExecutor / 郑希 / 供应链 executor，但**复用**同一套基建：
- :func:`src.agent.runner.run_agent_loop` —— ReAct 工具调用循环（max_steps=30 长任务）
- :class:`src.agent.llm_adapter.LLMToolAdapter` —— 多渠道 LLM
- :class:`src.agent.deep_research_validator.DeepResearchValidator` —— 质量校验

与对话框式 executor 的差异：
- **表单一次性生成**，不做多轮会话 bundle（历史通过 storage.deep_research_reports 表持久化）。
- 暴露 ``generate(stock_code, stock_name, ...)`` 而非 ``chat(message, session_id, ...)``，
  便于 SSE 端点用 ``asyncio.to_thread`` 包装。
- 内置「降级」+「质量校验重生成」：步数耗尽不返回空报告；校验失败追加提示重跑一轮。

system prompt 运行时从 ``data/deep_research/system_prompt.md`` 读取，便于迭代不改代码。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:  # 避免 import 时强依赖 litellm（部署环境才有）
    from src.agent.llm_adapter import LLMToolAdapter
    from src.agent.runner import RunLoopResult
    from src.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SYSTEM_PROMPT_PATH = os.path.join(_PROJECT_ROOT, "data", "deep_research", "system_prompt.md")


# system_prompt.md 缺失时的兜底（极简版，保证不崩）
_FALLBACK_SYSTEM_PROMPT = """你是 A 股投研总监。对指定股票生成深度投研报告，遵循五层穿透框架：宏观→产业→财务→估值→博弈。
每层必须调用工具获取真实数据，每章首句用【结论】前置，三情景概率和=100%，数字锚定所有观点，禁止编造数据。
（注：完整框架加载失败，正在使用兜底提示，请检查 data/deep_research/system_prompt.md）"""


def build_deep_research_system_prompt() -> str:
    """读取 data/deep_research/system_prompt.md 作为 system prompt。"""
    try:
        with open(_SYSTEM_PROMPT_PATH, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("[DeepResearch] system_prompt.md 读取失败 (%s): %s", _SYSTEM_PROMPT_PATH, exc)
        return _FALLBACK_SYSTEM_PROMPT


@dataclass
class DeepResearchResult:
    """深度投研报告生成结果。"""

    success: bool = False
    status: str = "failed"  # success | partial | failed
    markdown: str = ""
    stock_code: str = ""
    stock_name: str = ""
    quality_score: int = 0  # 0-100，来自 validator
    missing_layers: List[str] = field(default_factory=list)
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    error: Optional[str] = None


class DeepResearchExecutor:
    """深度投研报告专属 Agent。

    长任务配置：``max_steps=30``、``wall_clock=1200s``（五层穿透 + 报告生成 2–5 分钟）。
    """

    def __init__(
        self,
        tool_registry: "ToolRegistry",
        llm_adapter: "LLMToolAdapter",
        max_steps: int = 30,
        timeout_seconds: Optional[float] = 1200.0,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def generate(
        self,
        stock_code: str,
        stock_name: str,
        report_type: str = "deep",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> DeepResearchResult:
        """生成一份深度投研报告（ReAct 工具循环 + 质量校验 + 降级）。"""
        from src.agent.deep_research_validator import DeepResearchValidator
        from src.agent.runner import run_agent_loop

        system_prompt = build_deep_research_system_prompt()
        user_message = self._build_user_message(stock_code, stock_name, report_type)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if progress_callback:
            progress_callback(
                {
                    "type": "thinking",
                    "step": 0,
                    "message": f"开始对 {stock_name}（{stock_code}）进行五层穿透深度分析...",
                }
            )

        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
            max_wall_clock_seconds=self.timeout_seconds,
            stock_scope=None,
        )

        validator = DeepResearchValidator()

        # 基础内容判定 + 降级
        if loop_result.success and loop_result.content and loop_result.content.strip():
            markdown = self._strip_preamble(loop_result.content)
            status = "success"
            base_error: Optional[str] = None
        else:
            markdown = self._build_partial_report(loop_result, stock_code, stock_name)
            status = "partial" if markdown else "failed"
            base_error = loop_result.error or "报告生成未完成（步数/时长限制）"

        # 质量校验
        validation = validator.validate(markdown, loop_result.tool_calls_log)

        # L3 兜底：仅对 success 报告尝试重生成（partial/failed 不再重试，避免雪上加霜）
        if status == "success" and not validation.passed and validation.missing_layers:
            retry_result = self._retry_with_hints(
                messages, validation.missing_layers, progress_callback
            )
            if retry_result is not None and retry_result.success and retry_result.content:
                retry_validation = validator.validate(
                    retry_result.content, retry_result.tool_calls_log
                )
                # 只在重生成确实更好时采纳
                if retry_validation.score >= validation.score:
                    logger.info(
                        "[DeepResearch] 重生成采纳: score %d -> %d",
                        validation.score,
                        retry_validation.score,
                    )
                    markdown = self._strip_preamble(retry_result.content)
                    loop_result = retry_result
                    validation = retry_validation

        # 最终状态
        missing_layers = list(validation.missing_layers)
        if status == "success" and missing_layers:
            status = "partial"
            markdown = self._prepend_partial_warning(markdown, missing_layers)

        return DeepResearchResult(
            success=(status != "failed"),
            status=status,
            markdown=markdown,
            stock_code=stock_code,
            stock_name=stock_name,
            quality_score=validation.score,
            missing_layers=missing_layers,
            tool_calls_log=loop_result.tool_calls_log or [],
            total_steps=loop_result.total_steps,
            total_tokens=loop_result.total_tokens,
            provider=loop_result.provider or "",
            error=None if status != "failed" else base_error,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_message(stock_code: str, stock_name: str, report_type: str) -> str:
        return (
            f"请对 A 股 **{stock_name}（{stock_code}）** 生成一份完整的深度投研报告（{report_type}）。\n\n"
            "严格要求：\n"
            "1. 严格按五层穿透框架（宏观→产业→财务→估值→博弈）逐层分析，**不可跳层**；\n"
            "2. 每一层都必须调用相应工具获取真实数据（宏观层调 get_market_indices + search_comprehensive_intel，"
            "产业层调 get_sector_rankings，财务层调 get_stock_info，博弈层调 analyze_trend/get_chip_distribution/get_capital_flow）；\n"
            "3. 每一层都注入「政策敏感度因子」和「筹码结构因子」；\n"
            "4. 每个一级章节首句用 **【结论】** 前置；\n"
            "5. 三情景（牛市/基准/熊市）概率和严格=100%；\n"
            "6. 所有观点用数字锚定，取不到的数据标注「数据缺失」，禁止编造。\n\n"
            "数据收集充分后，按 system prompt 的八章节骨架输出完整 Markdown 报告。"
        )

    @staticmethod
    def _strip_preamble(markdown: str) -> str:
        """截掉报告正文前的 LLM 过渡句/思考句。

        system prompt 要求最终回答首字符为 ``#``（一级标题），但 LLM 偶尔会在
        标题前泄漏过渡句（如「数据已收集，现在输出报告」「新闻不可用，但…」）。
        本方法兜底：定位第一个以 ``# `` 开头的行，截掉其前所有内容；若无标题行
        则原样返回（避免误删无标题的 partial 报告）。
        """
        if not markdown or not markdown.strip():
            return markdown
        lines = markdown.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("# "):
                return "\n".join(lines[i:]) if i > 0 else markdown
        return markdown

    def _retry_with_hints(
        self,
        messages: List[Dict[str, Any]],
        missing_layers: List[str],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> "Optional[RunLoopResult]":
        """质量校验失败后，追加提示重跑一轮。返回 None 表示重生成异常。"""
        from src.agent.runner import run_agent_loop

        hint = (
            "你的报告未通过五层穿透质量校验，以下层次的分析不充分或缺失："
            f"{', '.join(missing_layers)}。"
            "请调用必要工具补充这些层次的完整分析，然后重新输出**完整的**深度投研报告"
            "（必须包含全部八个章节，保留已写好的部分并补全缺失部分）。"
        )
        retry_messages = list(messages)
        retry_messages.append({"role": "user", "content": hint})

        if progress_callback:
            progress_callback(
                {
                    "type": "thinking",
                    "step": 0,
                    "message": f"质量校验发现 {', '.join(missing_layers)} 层不足，正在补充重生成...",
                }
            )

        try:
            return run_agent_loop(
                messages=retry_messages,
                tool_registry=self.tool_registry,
                llm_adapter=self.llm_adapter,
                max_steps=min(self.max_steps, 12),
                progress_callback=progress_callback,
                max_wall_clock_seconds=min(float(self.timeout_seconds or 1200.0), 360.0),
                stock_scope=None,
            )
        except Exception as exc:
            logger.warning("[DeepResearch] 重生成异常: %s", exc)
            return None

    def _build_partial_report(
        self,
        loop_result: "RunLoopResult",
        stock_code: str,
        stock_name: str,
    ) -> str:
        """步数耗尽/失败时，从已收集数据构建部分报告（不返回空）。"""
        # 优先用已有内容
        if loop_result.content and loop_result.content.strip():
            return loop_result.content

        tools_used = sorted(
            {
                str(entry.get("tool", ""))
                for entry in (loop_result.tool_calls_log or [])
                if isinstance(entry, dict) and entry.get("tool")
            }
        )
        summary = self._summarize_collected_data(loop_result)
        return (
            f"# {stock_name}（{stock_code}）深度投研报告（未完成）\n\n"
            f"> ⚠️ **本报告因分析时长/步数限制未能完整生成。** "
            f"以下为已收集数据的初步整理，建议稍后重新生成获取完整报告。\n\n"
            f"**分析状态**：{loop_result.error or '达到最大步数限制'}\n\n"
            f"**已调用工具（{len(tools_used)} 个）**：{', '.join(tools_used) if tools_used else '无'}\n\n"
            f"---\n\n## 已收集数据摘要\n\n{summary}\n"
        )

    @staticmethod
    def _summarize_collected_data(loop_result: "RunLoopResult") -> str:
        """从 messages 中 role=tool 的内容提取摘要（每个截断防爆）。"""
        chunks: List[str] = []
        for msg in loop_result.messages or []:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                name = str(msg.get("name", "工具"))
                raw = str(msg.get("content", ""))
                snippet = raw[:300]
                ellipsis = "..." if len(raw) > 300 else ""
                chunks.append(f"**{name}**：{snippet}{ellipsis}")
        if not chunks:
            return "（未收集到有效数据）"
        # 最多 10 条，防爆 context
        return "\n\n".join(chunks[:10])

    @staticmethod
    def _prepend_partial_warning(markdown: str, missing_layers: List[str]) -> str:
        """在报告顶部插入质量提示横幅。"""
        warning = (
            f"> ⚠️ **质量提示**：本报告以下层次分析不充分：{', '.join(missing_layers)}。"
            "建议结合其他信息源交叉验证，或重新生成。\n\n---\n\n"
        )
        return warning + markdown
