# -*- coding: utf-8 -*-
"""郑希投研 Agent 工具集。

三个工具，覆盖 MVP 核心三件：
- ``search_zhengxi_views``：语料检索（溯源问答）
- ``get_zhengxi_fund_data``：基金业绩/持仓查询
- ``score_fund_zhengxi``：郑希框架六维评分证据档案

所有工具返回**精炼摘要**（剔除逐日净值序列），并带出处/截止日期，
便于 LLM 做可溯源引用、避免杜撰。工具集注册到独立 ToolRegistry 实例，
不污染问股的全局工具集。
"""

import logging
from typing import Any, List, Optional

from src.agent.tools.registry import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)

_SNIPPET_LIMIT = 600  # 单条语料片段截断长度，控制进 LLM context 的体量


# ============================================================
# 1. search_zhengxi_views — 语料检索
# ============================================================

def _handle_search_zhengxi_views(
    keywords: List[str],
    match_any: bool = False,
    doc_types: Optional[List[str]] = None,
    max_results: int = 8,
) -> dict[str, Any]:
    """检索郑希公开观点原文（季报/手记/媒体专访）。"""
    from src.services.zhengxi import corpus

    if not keywords:
        return {"error": "至少提供一个关键词"}

    hits = corpus.search_corpus(
        keywords,
        match_all=not match_any,
        doc_types=doc_types,
        context=0,
        max_results=max_results,
    )

    results = []
    for hit in hits:
        snippet = hit["snippet"]
        if len(snippet) > _SNIPPET_LIMIT:
            snippet = snippet[:_SNIPPET_LIMIT] + "…"
        results.append({
            "date": hit["date"],
            "type": hit["type"],
            "title": hit["title"],
            "source": hit["source"],
            "link": hit["link"],
            "matched_keywords": hit["matched"],
            "quote": snippet,
        })

    return {
        "query_keywords": keywords,
        "match_mode": "any" if match_any else "all",
        "corpus_scope": corpus.load_corpus_summary(),
        "total_hits": len(hits),
        "results": results,
        "usage_note": (
            "以上为郑希本人公开观点原文片段。引用时请自然标注出处，"
            "例如『他在 2026 年 6 月接受中国证券报采访时表示』；"
            "禁止使用文件路径、工具字段名等内部记号。"
        ),
    }


search_zhengxi_views_tool = ToolDefinition(
    name="search_zhengxi_views",
    description=(
        "检索基金经理郑希的公开观点原文（季报/中报/年报、基金经理手记、"
        "媒体专访），返回带日期与出处的段落片段。用于回答『郑希怎么看 X』"
        "类溯源问题。默认要求段落同时命中全部关键词（AND），传 match_any=true "
        "改为命中任一（OR）。"
    ),
    parameters=[
        ToolParameter(
            name="keywords",
            type="array",
            description="关键词列表，如 ['光通信'] 或 ['AI算力','光模块']",
            required=True,
        ),
        ToolParameter(
            name="match_any",
            type="boolean",
            description="true=命中任一关键词即可(OR)；false(默认)=须全部命中(AND)",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="doc_types",
            type="array",
            description="限定文档类型，可选值：定期报告 / 基金经理手记 / 媒体报道",
            required=False,
            default=None,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="最多返回片段数（默认 8）",
            required=False,
            default=8,
        ),
    ],
    handler=_handle_search_zhengxi_views,
    category="search",
)


# ============================================================
# 2. get_zhengxi_fund_data — 基金业绩/持仓查询
# ============================================================

def _handle_get_zhengxi_fund_data(
    fund: str,
    sections: Optional[List[str]] = None,
) -> dict[str, Any]:
    """查询郑希管理的某只基金的最新持仓与业绩摘要。"""
    from src.services.zhengxi import fund_data

    meta = fund_data.resolve_fund(fund)
    if not meta:
        return {
            "error": f"未找到基金：{fund}",
            "supported_funds": [
                f"{f['code']} {f['name']}（{f['role']}）"
                for f in fund_data.list_funds()
            ],
            "note": "当前仅支持郑希管理过的 8 只基金（在任或曾任）。全市场任意基金对比为后续版本能力。",
        }

    requested = sections or ["holdings", "performance"]
    payload = {
        "fund_code": meta["code"],
        "fund_name": meta["name"],
        "role": meta["role"],
        "type": meta.get("type", ""),
        "tenure": f"{meta.get('start', '')} ~ {meta.get('end', '--')}",
        "data_cutoff_note": "静态快照（天天基金/易方达官网公开数据），非实时",
    }
    if "holdings" in requested:
        latest = fund_data.latest_holdings(meta["code"])
        if latest:
            payload["latest_holdings"] = latest
    if "performance" in requested:
        payload["performance"] = fund_data.load_performance_summary(meta["code"])
    return payload


get_zhengxi_fund_data_tool = ToolDefinition(
    name="get_zhengxi_fund_data",
    description=(
        "查询郑希管理的某只基金的最新前十大持仓（含集中度、换手代理）与"
        "业绩摘要（区间收益、最大回撤、规模、资产配置、天天基金五维评价、"
        "郑希任职回报）。fund 接受 6 位代码或名称（如 '001513' 或 '信息产业'）。"
        "数据为静态快照，已标注截止日期，非实时。"
    ),
    parameters=[
        ToolParameter(
            name="fund",
            type="string",
            description="基金代码（如 001513）或名称关键词（如 信息产业）",
            required=True,
        ),
        ToolParameter(
            name="sections",
            type="array",
            description="返回哪些部分：holdings（持仓）/ performance（业绩），默认两者都返回",
            required=False,
            default=None,
        ),
    ],
    handler=_handle_get_zhengxi_fund_data,
    category="data",
)


# ============================================================
# 3. score_fund_zhengxi — 郑希框架六维评分证据档案
# ============================================================

_SIX_DIMENSIONS = [
    {"dim": "1 景气方向/通胀属性", "max": 25, "what": "重仓是否在涨价景气方向（新技术落地、供给端创造需求的科技型通胀最佳）"},
    {"dim": "2 ROE 低位弹性", "max": 20, "what": "偏好低 ROE 待修复（供求压制型/预先研发型），而非高 ROE 白马。个股精确 ROE 标『需核实』"},
    {"dim": "3 全球视野/中国比较优势", "max": 15, "what": "方向是否落在全球技术周期中中国有比较优势的环节"},
    {"dim": "4 流动性", "max": 10, "what": "重仓股流动性、基金规模与持仓风格是否匹配"},
    {"dim": "5 集中度与周期拼接", "max": 15, "what": "适度集中 + 季度间动态调仓（换手代理高=周期拼接=加分，非缺点）"},
    {"dim": "6 业绩与回撤印证", "max": 15, "what": "收益是否来自景气方向（高弹性高波动是风格自然结果，非追求低回撤）"},
]


def _handle_score_fund_zhengxi(fund: str) -> dict[str, Any]:
    """收集某基金的评分证据档案 + 六维评分指引，交 LLM 逐维打分。"""
    from src.services.zhengxi import fund_data

    meta = fund_data.resolve_fund(fund)
    if not meta:
        return {
            "error": f"未找到基金：{fund}",
            "supported_funds": [
                f"{f['code']} {f['name']}（{f['role']}）"
                for f in fund_data.list_funds()
            ],
            "note": "当前仅支持郑希管理过的 8 只基金。",
        }

    latest = fund_data.latest_holdings(meta["code"])
    performance = fund_data.load_performance_summary(meta["code"])
    return {
        "fund_code": meta["code"],
        "fund_name": meta["name"],
        "role": meta["role"],
        "scoring_purpose": (
            "衡量『这只基金有多像郑希会买的基金』，不是基金优劣判断。"
            "防御型/红利/纯债天然低分是正常的，不代表基金差。"
        ),
        "evidence": {
            "latest_holdings": latest,
            "performance": performance,
        },
        "six_dimensions": _SIX_DIMENSIONS,
        "rating_scale": "高度契合(80+) / 较契合(60–79) / 部分契合(40–59) / 不契合(<40)",
        "output_format_note": (
            "逐维给【得分】+【证据（带季度日期）】，给总分和评级，"
            "结尾固定声明『契合度非优劣，非投资建议；个股 ROE/流动性等无数据项请自行核实』。"
        ),
    }


score_fund_zhengxi_tool = ToolDefinition(
    name="score_fund_zhengxi",
    description=(
        "按郑希投资方法给某基金做六维风格契合度评分（满分 100）。返回评分所需的"
        "证据档案（最新持仓、集中度、换手代理、业绩、回撤）和六维评分指引。"
        "评分衡量『像不像郑希会买的』，不是基金优劣。fund 接受代码或名称。"
    ),
    parameters=[
        ToolParameter(
            name="fund",
            type="string",
            description="基金代码（如 001513）或名称关键词",
            required=True,
        ),
    ],
    handler=_handle_score_fund_zhengxi,
    category="analysis",
)


ALL_ZHENGXI_TOOLS = [
    search_zhengxi_views_tool,
    get_zhengxi_fund_data_tool,
    score_fund_zhengxi_tool,
]
