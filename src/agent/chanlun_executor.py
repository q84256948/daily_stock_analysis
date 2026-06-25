# -*- coding: utf-8 -*-
"""缠论分析 Agent Executor。"""

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from src.agent.llm_adapter import LLMToolAdapter


_SYSTEM_PROMPT = """你是「缠论技术分析」助手，基于缠中说禅的缠论体系对股票进行深度技术分析。

## 工作流程

1. 从用户输入中提取股票代码和市场
2. 调用 `analyze_chanlun` 工具获取缠论结构化分析结果
3. 基于分析结果撰写完整技术分析报告

## 缠论核心概念

### 分型
- 顶分型：三根K线，中间一根最高
- 底分型：三根K线，中间一根最低

### 笔
- 连接相邻同向分型，至少5根K线
- 笔破坏是趋势转折标志

### 中枢
- 三段重叠区间，趋势的锚点
- 突破/跌破中枢是重要信号

### 背驰
- 趋势背驰：价格创新高/低但MACD未跟随
- 盘整背驰：同向笔力度衰竭

### 买卖点
- 1买/2买/3买：结构性买点
- 1卖/2卖/3卖：对应卖点

## 输出要求

### 一句话结论
简洁概括当前走势状态。

### 缠论结构解读
- 当前趋势（上涨/下跌/盘整）
- 最新一笔的方向和状态
- 中枢位置与价格关系
- 是否出现背驰

### 买卖点信号
列出所有买卖点及评分。

### 未来三个月走势预测（重点）
基于缠论结构预测：
1. 当前在上涨中，判断是否背驰导致回调
2. 当前在下跌中，判断是否背驰导致反弹
3. 在中枢震荡中，判断突破方向
4. 给出关键价位（支撑/压力）

### 风险提示
- 当前分析风险因素
- 需要关注的关键信号

## 合规约束
- 不提供具体买卖建议
- 明确分析局限性
- 缠论分析仅是参考之一
"""


class ChanlunExecutor:
    """缠论分析专属 Agent。"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: "LLMToolAdapter",
        max_steps: int = 10,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        message: str,
        session_id: str,
        progress_callback: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """执行缠论分析。"""
        from src.agent.chat_context import build_agent_chat_context_bundle
        from src.agent.conversation import conversation_manager
        from src.agent.executor import AgentResult
        from src.agent.runner import run_agent_loop

        conversation_manager.get_or_create(session_id)
        bundle = build_agent_chat_context_bundle(
            session_id, self.llm_adapter, self.llm_adapter._config
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
        ]
        messages.extend(bundle.context_messages)
        messages.append({"role": "user", "content": message})

        conversation_manager.add_message(session_id, "user", message)

        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
            max_wall_clock_seconds=self.timeout_seconds,
            stock_scope=None,
        )

        if loop_result.success:
            conversation_manager.add_message(
                session_id, "assistant", loop_result.content
            )
        else:
            conversation_manager.add_message(
                session_id, "assistant", f"[分析失败] {loop_result.error or '未知错误'}"
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
