# -*- coding: utf-8 -*-
"""郑希投研分析专属 Executor。

独立于问股的 :class:`src.agent.executor.AgentExecutor`（后者强耦合股票
scope / 股票 context / 决策仪表盘 JSON），但**复用**同一套基础设施：
- :func:`src.agent.runner.run_agent_loop` —— ReAct 工具调用循环
- :class:`src.agent.llm_adapter.LLMToolAdapter` —— 多渠道 LLM
- :func:`src.agent.conversation.conversation_manager` —— 会话持久化
- :func:`src.agent.chat_context.build_agent_chat_context_bundle` —— 历史上下文

system prompt 运行时从 ``data/fund_manager_views/zhengxi/`` 读取
method.md + scorecard.md 组装，知识库更新无需改代码。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.tools.registry import ToolRegistry
from src.config import get_config
from src.services.zhengxi.paths import method_path, scorecard_path

if TYPE_CHECKING:  # 避免 import 时强依赖 litellm（部署环境才有）
    from src.agent.llm_adapter import LLMToolAdapter

logger = logging.getLogger(__name__)


_ZHENGXI_SYSTEM_PROMPT_TEMPLATE = """你是「郑希投研分析」助手，专注于易方达基金经理郑希（权益投资管理部副总经理）的投研问答。你基于三类可溯源材料作答：

1. 郑希本人的公开观点语料（季报/中报/年报、基金经理手记、媒体专访共 76 篇，2012–2026）；
2. 他的投资方法框架（从语料蒸馏，每条配原话佐证）；
3. 他管理的 8 只基金的真实数据（持仓、净值、规模、任职回报，静态快照）。

## 可用工具（按问题类型选用）

- `search_zhengxi_views`：检索郑希公开观点原文，返回带日期与出处的段落。用于「郑希怎么看 X」「他在哪篇报告里说过 Y」类溯源问题，以及了解他的投资方法。
- `get_zhengxi_fund_data`：查询他管理的某只基金的最新持仓（含集中度、换手代理）与业绩摘要（收益、回撤、规模、配置、任职回报）。用于「001513 最近持仓」「信息产业今年涨了多少」类数据问题。
- `score_fund_zhengxi`：按郑希框架对某基金做六维风格契合度评分，返回证据档案与评分指引。用于「这只基金有多像郑希会买的」类评分问题。

## 诚实红线（必须严格遵守）

1. **三种话分开**：
   - 【郑希原话】：忠实引用，并自然标注出处（如「他在 2026 年 6 月接受中国证券报采访时表示……」），不改动原意。
   - 【按他方法的推演】：当语料没有直接表态时，用下面的方法框架推演，但必须在段落首句加粗声明「以下非郑希本人观点，是按其投资方法的推演」。
   - 【需核实的事实】：涉及具体公司、价格、个股 ROE、流动性细节等没有语料或数据支撑的，标注「需核实」，绝不编造。
2. **不报内部记号**：回答里绝不出现文件路径、method.md、scorecard.md、§章节号、工具返回的 path 字段等任何内部格式。
3. **数据必标日期**：持仓/业绩必须带季度或日期，只来自工具返回，不编造数字；明确这是静态快照、非实时。
4. **评分守定位**：六维评的是「与郑希风格的契合度」，不是「基金优劣」；防御型/红利/纯债天然低分要讲清楚，这不代表基金差。

## 工作流程

1. 先判断问题类型（溯源/方法、数据查询、评分、前瞻推演），调用对应工具。
2. 溯源问答：先 `search_zhengxi_views` 检索，用命中原文作答，区分【郑希原话】与你的归纳。
3. 检索无结果时，如实告知「语料未见他就该话题的直接表态」，可选择用方法框架推演（遵守红线 1 的声明要求）。
4. 评分：调 `score_fund_zhengxi` 取证据，严格按六维逐项给分+证据（带季度）+总分+评级，结尾声明契合度定位。

## 郑希投资方法

{{METHOD}}

## 六维评分卡（评分时严格遵循）

{{SCORECARD}}

## 输出语言

默认中文回答。
"""


def _read_text(path: str, label: str) -> str:
    """读取知识库文件，缺失时返回提示而非崩溃（保证 prompt 可用）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("[ZhengxiExecutor] 读取 %s 失败 (%s): %s", label, path, exc)
        return f"（{label} 加载失败，请检查数据目录）"


def build_zhengxi_system_prompt() -> str:
    """组装郑希 system prompt（注入 method.md + scorecard.md 全文）。

    用 ``.replace()`` 占位符而非 ``.format()``，避免知识库正文里的花括号
    被误解析。
    """
    method = _read_text(method_path(), "投资方法")
    scorecard = _read_text(scorecard_path(), "评分卡")
    return (
        _ZHENGXI_SYSTEM_PROMPT_TEMPLATE
        .replace("{{METHOD}}", method)
        .replace("{{SCORECARD}}", scorecard)
    )


class ZhengxiExecutor:
    """郑希投研分析专属 Agent。

    与问股 :class:`AgentExecutor` 暴露相同的 ``chat(message, session_id,
    progress_callback, context)`` 接口，便于复用 SSE 端点的线程池包装。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: LLMToolAdapter,
        max_steps: int = 10,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        message: str,
        session_id: str,
        progress_callback: Optional[Callable[..., Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """执行一轮郑希投研问答（ReAct 工具循环 + 会话持久化）。"""
        from src.agent.chat_context import build_agent_chat_context_bundle
        from src.agent.conversation import conversation_manager
        from src.agent.executor import AgentResult
        from src.agent.runner import run_agent_loop

        system_prompt = build_zhengxi_system_prompt()
        tool_decls = self.tool_registry.to_openai_tools()

        conversation_manager.get_or_create(session_id)
        config = getattr(self.llm_adapter, "_config", None) or get_config()
        bundle = build_agent_chat_context_bundle(session_id, self.llm_adapter, config)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(bundle.context_messages)
        messages.append({"role": "user", "content": message})

        # 持久化用户消息，使会话在处理期间即出现在历史列表
        conversation_manager.add_message(session_id, "user", message)

        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
            max_wall_clock_seconds=self.timeout_seconds,
            stock_scope=None,  # 郑希是基金/基金经理主题，不做股票 scope 约束
        )

        # 持久化助手回复（或失败标注），保证多轮上下文连续
        if loop_result.success:
            conversation_manager.add_message(session_id, "assistant", loop_result.content)
        else:
            conversation_manager.add_message(
                session_id,
                "assistant",
                f"[分析失败] {loop_result.error or '未知错误'}",
            )

        return AgentResult(
            success=loop_result.success,
            content=loop_result.content,
            tool_calls_log=loop_result.tool_calls_log,
            total_steps=loop_result.total_steps,
            total_tokens=loop_result.total_tokens,
            provider=loop_result.provider,
            model=loop_result.model,
            error=loop_result.error,
            messages=loop_result.messages,
        )
