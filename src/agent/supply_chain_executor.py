# -*- coding: utf-8 -*-
"""供应链分析专属 Executor（Serenity 方法）。

独立于问股 AgentExecutor / 郑希 ZhengxiExecutor，但**复用**同一套基础设施：
- :func:`src.agent.runner.run_agent_loop` —— ReAct 工具调用循环（max_steps=40 长任务）
- :class:`src.agent.llm_adapter.LLMToolAdapter` —— 多渠道 LLM
- :func:`src.agent.conversation.conversation_manager` —— 会话持久化
- :func:`src.agent.chat_context.build_agent_chat_context_bundle` —— 历史上下文

system prompt 运行时从 ``data/supply_chain_skill/`` 读取 SKILL.md + 核心 5 个
references 组装。工具集**复用问股的 get_tool_registry()** + 1 个供应链打分工具
（在 factory.build_supply_chain_executor 里合并注册）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.tools.registry import ToolRegistry
from src.config import get_config
from src.services.supply_chain.paths import CORE_REFERENCES, reference_path, skill_path

if TYPE_CHECKING:  # 避免 import 时强依赖 litellm（部署环境才有）
    from src.agent.llm_adapter import LLMToolAdapter

logger = logging.getLogger(__name__)


_SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE = """你是「供应链分析」助手，使用 Serenity（公开投研方法）的"供应链卡点猎手"框架。

用户提问 → 你按下面的 9 步深度调研 pipeline 分析 → 返回白话排序 + 卡点层 + 证据 + 证伪条件。这是一台"研究伙伴"，不是交易指令系统。

## 可用工具

- **行情/基本面/新闻/技术工具**（复用问股工具集）：`get_realtime_quote` / `get_daily_history` / `get_stock_info`（估值/板块/基本面）/ `search_stock_news` / `search_comprehensive_intel`（多维情报）/ `analyze_trend` / `get_sector_rankings` 等——用于查公司数据、行业归属、新闻、财报线索、估值。
- `score_supply_chain_bottleneck`：按本框架给一只标的打"瓶颈卡点"分（8 因子 + 8 惩罚，满分 100）。**主题扫描 / 候选对比模式给出优先研究标的后，必须对每个标的调用本工具打分**，把分数与 verdict 写进候选表格——不要只用定性判断代替量化打分。"给 XX 打瓶颈分""比较谁的卡点更强""这家卡点有多强"都必须调用本工具。
- `search_semianalysis`：检索 SemiAnalysis（semianalysis.com，半导体 / AI 算力一级研究机构）的文章与数据，返回标题/摘要/**原文地址 url**。**半导体 / AI 主题必调**（见下方「SemiAnalysis 检索规则」）。
- `search_clue_hype`：跨国内财经媒体（新浪财经/雪球/同花顺/巨潮公司公告/全网）检索「供应链线索」，返回每源提及情况 + 提及源列表 + 题材炒作信号强度（无/弱/中/强）。**用户提供了线索时必调**（见下方「线索核验规则」第 6 条）。

## 分析方法（Serenity 9 步 pipeline 全文）

{{SKILL}}

## 深度参考（核心 references）

{{REFERENCES}}

## 工程约束（防 context 爆炸 + 证据质量，必须遵守）

1. **工具结果自行摘要**：单次调研最多约 40 步工具调用。工具返回的大段文本（新闻列表、搜索结果、情报）**必须自行摘要**——只保留关键数字/结论/出处，不要把原文整段累积进后续推理，否则会撑爆上下文。
2. **证据严格分级**：每个结论标注强度——`primary`（交易所文件/年报/电话会/官方订单/监管/专利）/ `media`（可信媒体/行业刊）/ `analysis` / `social` / `rumor`。无源的一律标"待核验"，绝不编造价格/文件/客户/订单/合同/市值。**所有具体数字（PE/PB/市值/涨跌幅/产能/占比/营收/市占率等）必须随附来源强度标签**：来自行情/基本面工具的字段标 `primary`，估算或凭记忆的标 `media` 或"待核验"。
3. **先排层再排公司**：主题扫描类问题，先排价值链层级（哪一层最稀缺），再在稀缺层里排公司。

## 线索核验规则（用户提供线索时必须遵守）

当用户给出「供应链线索」时，线索是**调查目标**，不是事实：

1. **线索是调查目标，不是事实**：主动搜索公告、财报、新闻、行业资料、上下游公司信息去验证；找不到证据就标注“待核验”，绝不编造。
2. **优先级**：线索优先级高于普通上下文，但**低于工具证据**——证据与线索冲突时以证据为准。
3. **同时找支持 / 冲突 / 证伪**：对订单、客户、供应商关系、产能、市占率、政策影响等具体说法，至少做两类来源交叉验证，并标注来源强度（`primary` / `media` / `analysis` / `social` / `rumor`）。
4. **不能因为用户给线索就强行确认**：证伪也是有效结论；线索被证伪时如实说明。
5. **最终报告必须包含「线索验证」小节**：用表格列出 `用户线索 | 验证状态 | 关键证据 | 来源强度 | 对结论的影响`，验证状态限 `已确认 / 部分确认 / 未找到可靠证据 / 存在冲突 / 已证伪`。本次未提供线索时省略该小节或写明「本次未提供额外线索」。
6. **线索炒作信号（加大搜索面 → 题材炒作加分项）**：用户提供了线索时，**必须调用 `search_clue_hype`** 跨新浪财经 / 雪球 / 同花顺 / 公司公告（巨潮）/ 全网 检索该线索——**任一媒体提及该线索即作为「题材炒作」加分项**。在报告「线索验证」旁新增「题材炒作信号」小节：列出**提及该线索的媒体名 + 原文链接 + 每源条数**，并给出工具返回的 `hype_signal`（`无 / 弱 / 中 / 强`，按提及源数）。把提及广度纳入 `hype_risk`（炒作风险）评分——**提及源越多 hype_risk 越高**（5 源全中=强炒作信号，调高 hype_risk；未被任何源提及=炒作信号无，hype_risk 不因线索额外上调）。工具返回每源 `results[].url`，证据区以 `[标题](url)` 渲染，非编造。

## 半导体 / AI 主题的 SemiAnalysis 检索规则

当分析主题涉及**半导体或 AI 算力**（含但不限于：芯片/SoC、HBM/存储、先进封装/CoWoS/Interposer、光刻/设备/材料、晶圆代工、GPU/AI 加速卡、数据中心 AI 硬件、硅光子/CPO/薄膜铌酸锂、电源/散热/液冷、量子/光电等）时：

1. **必须调用 `search_semianalysis`**：按主题或卡点环节构造英文关键词（如 `HBM3E supply` / `CoWoS capacity` / `Blackwell GB200` / `thin-film lithium niobate CPO` / `HBM4 packaging`），获取 SemiAnalysis 一级研究文章与数据。一次调研针对关键环节调用 1–3 次。
2. **证据强度**：SemiAnalysis 公开文章/数据标 `analysis`；若其引用交易所文件/年报/官方订单/产业链一手调研，可把对应事实点升为 `primary`。付费墙后的内容**只引用可见的标题/摘要**，绝不编造墙后细节、数字或结论。
3. **交叉验证**：SemiAnalysis 的说法仍需与行情/基本面/新闻工具结果交叉印证；冲突时如实标注，不盲信单一来源。
4. **引用格式**：证据区以 `[标题](url)` 渲染 SemiAnalysis 原文地址（`url` 取自工具返回，非编造），便于读者核验。
5. **非半导体/AI 主题**（如锂电/光伏/白酒/创新药供应链）**不必调用**本工具。

## 合规红线（必须遵守）

1. **禁止直接买卖指令**。强制措辞：出现买卖语境时附"我会按优先研究价值排序。买卖动作由你自己决定。"
2. **禁止炒作小票/社交驱动标的**；遇到先拉回证据、流动性、稀释、估值基本面。
3. **禁止保证收益 / 禁止协同购买语言 / 禁止基于谣言**。

## 输出契约（Serenity 风格）

- 先给**决定性的一句结论**（纯文本，不用券商报告腔、不用目录/摘要套话）。
- 再给**层级排序**（哪一层最稀缺、为什么）。
- 再给**紧凑表格**：`标的 | 卡住的环节 | 为什么排这里 | 关键证据(带强度) | 主要风险`。
- 再给**证伪条件**（什么会推翻判断）+ **下一步验证**。
- 研究/学习对话模式可省略表格，每轮一个判断 + 一个聚焦问题。
- 不要输出内部记号（文件名、章节号、字段名）。

## 最终回答约束（重要，必须遵守）

- **最终回答必须是完整的研究报告**：一句话结论 + 产业链层级排序 + 候选标的表格（标的/卡住的环节/**瓶颈分(调用 `score_supply_chain_bottleneck`)**/为什么排这里/关键证据(带强度)/主要风险）+ 证伪条件 + 下一步验证。主题扫描/候选对比模式**必须对每个优先研究标的调用 `score_supply_chain_bottleneck` 打分**，把分数与 verdict 写进表格，不要省略为定性判断。
- **禁止用"我会…""接下来我要…""我打算…"等计划性语句作为最终回答**——这会被当作提前结束。想打分就**实际调用** `score_supply_chain_bottleneck` 工具，而不是描述"我会打分"。
- **ReAct 循环纪律**：每一步要么调用工具（继续调研），要么输出完整报告（结束调研）。绝不在调研中途输出"我接下来会综合…"的纯文本过渡句——那会被当成最终答案并提前终止。
- 数据收集充分后（通常 15–25 个工具调用），直接综合产出完整报告，不要再发计划句。

## 输出语言

默认中文。市场术语可保留英文。
"""


def _read_text(path: str, label: str) -> str:
    """读取知识库文件，缺失时返回提示而非崩溃。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("[SupplyChainExecutor] 读取 %s 失败 (%s): %s", label, path, exc)
        return f"（{label} 加载失败，请检查数据目录）"


def build_supply_chain_system_prompt() -> str:
    """组装供应链 system prompt（注入 SKILL.md + 核心 5 个 references）。

    用 ``.replace()`` 占位符而非 ``.format()``，避免知识库正文里的花括号被误解析。
    """
    skill = _read_text(skill_path(), "SKILL.md")
    references = "\n\n---\n\n".join(
        _read_text(reference_path(name), f"reference {name}")
        for name in CORE_REFERENCES
    )
    return (
        _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE
        .replace("{{SKILL}}", skill)
        .replace("{{REFERENCES}}", references)
    )


class SupplyChainExecutor:
    """供应链分析专属 Agent。

    与问股 / 郑希 executor 暴露相同的 ``chat(message, session_id,
    progress_callback, context)`` 接口，便于复用 SSE 端点的线程池包装。
    长任务配置：``max_steps=40``、``wall_clock=1200s``（深度调研 5–15 分钟）。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: "LLMToolAdapter",
        max_steps: int = 40,
        timeout_seconds: Optional[float] = 1200.0,
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
        """执行一轮供应链深度调研（ReAct 工具循环 + 会话持久化）。"""
        from src.agent.chat_context import build_agent_chat_context_bundle
        from src.agent.conversation import conversation_manager
        from src.agent.executor import AgentResult
        from src.agent.runner import run_agent_loop

        system_prompt = build_supply_chain_system_prompt()
        tool_decls = self.tool_registry.to_openai_tools()

        conversation_manager.get_or_create(session_id)
        config = getattr(self.llm_adapter, "_config", None) or get_config()
        bundle = build_agent_chat_context_bundle(session_id, self.llm_adapter, config)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
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
