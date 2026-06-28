# -*- coding: utf-8 -*-
"""供应链分析专属工具集。

当前 2 个工具：
- ``score_supply_chain_bottleneck``（包装 serenity_scorecard）
- ``search_semianalysis``（半导体 / AI 主题检索 semianalysis.com 一级研究源）

其余数据/情报工具**复用问股的全局 ToolRegistry**（行情/新闻/基本面/技术），
通过 ``build_supply_chain_executor`` 在 factory 里合并注册（见 factory.py）。
"""

import logging
from typing import Any, Dict, List, Optional

from src.agent.tools.registry import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)

# serenity_scorecard 的 8 个加权因子 + 8 个惩罚项（各 0-5 分）
FACTOR_KEYS = (
    "demand_inflection",        # 需求拐点
    "architecture_coupling",    # 架构耦合
    "chokepoint_severity",      # 卡点严重度
    "supplier_concentration",   # 供应商集中度
    "expansion_difficulty",     # 扩产难度
    "evidence_quality",         # 证据质量
    "valuation_disconnect",     # 估值脱节
    "catalyst_timing",          # 催化时点
)
PENALTY_KEYS = (
    "dilution_financing",       # 稀释/融资
    "governance",               # 治理
    "geopolitics",              # 地缘
    "liquidity",                # 流动性
    "hype_risk",                # 炒作
    "accounting_quality",       # 会计质量
    "cyclicality",              # 周期性
    "alternative_design_risk",  # 替代路线
)

_FACTOR_HINT = {
    "demand_inflection": "需求是否处于明确拐点(0=无,5=强拐点)",
    "architecture_coupling": "是否深度耦合于系统架构变化",
    "chokepoint_severity": "卡点严重度(客户无它无法扩产)",
    "supplier_concentration": "供应商集中度(少数厂商主导)",
    "expansion_difficulty": "扩产难度(设备/许可/纯度/验证周期)",
    "evidence_quality": "证据质量(强源占比)",
    "valuation_disconnect": "估值与基本面脱节程度",
    "catalyst_timing": "催化时点临近度",
}
_PENALTY_HINT = {
    "dilution_financing": "稀释/融资压力",
    "governance": "治理问题",
    "geopolitics": "地缘/出口管制风险",
    "liquidity": "流动性差",
    "hype_risk": "炒作风险",
    "accounting_quality": "会计质量存疑",
    "cyclicality": "周期性回落风险",
    "alternative_design_risk": "替代技术路线风险",
}


def _coerce_rating(value: Any) -> float:
    """把 LLM 传入的评分强转为 0-5 的 float，非法值归 0。"""
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    if rating < 0:
        return 0.0
    if rating > 5:
        return 5.0
    return rating


def _normalize_ratings(raw: Optional[Dict[str, Any]], keys: tuple[str, ...]) -> Dict[str, float]:
    """补全缺失字段为 0，并把每个值规整到 0-5。"""
    raw = raw or {}
    return {key: _coerce_rating(raw.get(key, 0)) for key in keys}


# ============================================================
# score_supply_chain_bottleneck
# ============================================================

def _handle_score_supply_chain_bottleneck(
    ticker: str,
    company: str,
    market: str = "",
    factors: Optional[Dict[str, Any]] = None,
    penalties: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    what_could_weaken_view: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """按 Serenity 框架给一只标的打"供应链瓶颈"分（满分 100）。"""
    from src.services.supply_chain import scorecard

    data = {
        "ticker": ticker or "",
        "company": company or "",
        "market": market or "",
        "notes": notes or "",
        "factors": _normalize_ratings(factors, FACTOR_KEYS),
        "penalties": _normalize_ratings(penalties, PENALTY_KEYS),
        "evidence": evidence or [],
        "what_could_weaken_view": what_could_weaken_view or [],
    }
    try:
        result, verdict = scorecard.score(data)
    except Exception as exc:
        logger.error("supply chain scorecard failed for %s: %s", ticker, exc, exc_info=True)
        return {"error": f"打分失败: {exc}", "input_echo": data}

    return {
        "ticker": data["ticker"],
        "company": data["company"],
        "verdict": scorecard.verdict_zh(verdict),
        "score_report_markdown": scorecard.to_markdown_zh(result),
        "final_score": result.get("final_score"),
        "usage_note": (
            "以上为 Serenity 框架瓶颈打分卡结果。衡量『供应链卡点强度』，"
            "非买卖建议。引用时请保留证据强度标签（强/中/弱/待查），"
            "不使用内部文件名或字段名。"
        ),
    }


score_supply_chain_bottleneck_tool = ToolDefinition(
    name="score_supply_chain_bottleneck",
    description=(
        "按 Serenity 供应链框架给一只标的打『瓶颈卡点』分（满分 100）。"
        "8 个加权因子（需求拐点/架构耦合/卡点严重度/供应商集中度/扩产难度/"
        "证据质量/估值脱节/催化时点）+ 8 个惩罚项（稀释/治理/地缘/流动性/炒作/"
        "会计/周期/替代路线），各 0-5 分。返回 verdict 评级、Markdown 报告与总分。"
        "用于『给 XX 打瓶颈分』『这家卡点有多强』类量化问题。"
    ),
    parameters=[
        ToolParameter(
            name="ticker",
            type="string",
            description="标的代码（如 600519 / AAPL / hk00700）",
            required=True,
        ),
        ToolParameter(
            name="company",
            type="string",
            description="公司名称",
            required=True,
        ),
        ToolParameter(
            name="market",
            type="string",
            description="市场：US / HK / A-share / Taiwan / Japan / Korea / Europe",
            required=False,
            default="",
        ),
        ToolParameter(
            name="factors",
            type="object",
            description=(
                "8 个加权因子的 0-5 评分，key 固定："
                + "；".join(f"{k}({h})" for k, h in _FACTOR_HINT.items())
            ),
            required=True,
        ),
        ToolParameter(
            name="penalties",
            type="object",
            description=(
                "8 个惩罚项的 0-5 评分（越高扣越多），key 固定："
                + "；".join(f"{k}({h})" for k, h in _PENALTY_HINT.items())
            ),
            required=False,
            default=None,
        ),
        ToolParameter(
            name="evidence",
            type="array",
            description="证据列表，每项 {claim, source, strength(primary/media/analysis/social/rumor)}",
            required=False,
            default=None,
        ),
        ToolParameter(
            name="what_could_weaken_view",
            type="array",
            description="可能削弱判断的因素（证伪条件）列表",
            required=False,
            default=None,
        ),
        ToolParameter(
            name="notes",
            type="string",
            description="备注（可选）",
            required=False,
            default="",
        ),
    ],
    handler=_handle_score_supply_chain_bottleneck,
    category="analysis",
)


# ============================================================
# SemiAnalysis 检索（半导体 / AI 主题一级研究源，复用共享 SearchService）
# ============================================================

# SemiAnalysis 是长青研究（非每日新闻），时间窗放宽到 1 年覆盖大量分析文章
_SEARCH_DAYS = 365
_MAX_SNIPPET = 500
_SEMIANALYSIS_SITE = "semianalysis.com"


def _get_search_service():
    """Lazy 共享 SearchService 访问器（测试可 monkeypatch 替换为 fake，避免真实网络）。"""
    from src.search_service import get_search_service

    return get_search_service()


def _pick_search_provider(service: Any) -> Any:
    """返回共享 SearchService 上首个可用 provider（或 None）。

    走 provider 原生 ``.search()``，``site:semianalysis.com`` 站点限定由 query 字符串承载
    （所有 provider 都尊重 Google 风格 ``site:`` 操作符），无需改共享 search_service。
    """
    if service is None:
        return None
    for provider in getattr(service, "_providers", None) or []:
        if getattr(provider, "is_available", False):
            return provider
    return None


def _build_semianalysis_query(keywords: Any) -> str:
    """构造 SemiAnalysis 站点限定 query：``site:semianalysis.com {keywords}``。"""
    kw = str(keywords or "").strip()
    return f"site:{_SEMIANALYSIS_SITE} {kw}".strip()


def _handle_search_semianalysis(
    keywords: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """检索 SemiAnalysis（semianalysis.com）半导体/AI 一级研究文章，返回带原文 url 的结果。

    复用共享 ``SearchService`` 的 provider（配置 ``TAVILY_API_KEYS`` 等后可用），query
    前缀 ``site:semianalysis.com`` 做站点限定；每条结果含 ``url``（可直接填入证据）。
    服务不可用 / 检索失败时返回 ``error``，agent 据此标注「待核验」而非编造。
    """
    provider = _pick_search_provider(_get_search_service())
    if provider is None:
        return {
            "error": "搜索引擎不可用（未配置 TAVILY_API_KEYS 等），无法检索 SemiAnalysis，请将相关判断标注「待核验」",
            "keywords": keywords,
        }

    query = _build_semianalysis_query(keywords)
    try:
        response = provider.search(query, max_results=max_results, days=_SEARCH_DAYS)
    except Exception as exc:  # noqa: BLE001 - 检索异常不得拖垮 agent
        logger.error("[SupplyChain] SemiAnalysis 检索异常 (%s): %s", keywords, exc)
        return {"error": f"SemiAnalysis 检索异常: {exc}", "keywords": keywords, "query": query}

    if not getattr(response, "success", False):
        return {
            "error": getattr(response, "error_message", None) or "SemiAnalysis 搜索失败",
            "keywords": keywords,
            "query": query,
        }

    items = [
        {
            "title": getattr(r, "title", ""),
            "snippet": (getattr(r, "snippet", "") or "")[:_MAX_SNIPPET],
            "url": getattr(r, "url", ""),
            "source": getattr(r, "source", ""),
            "date": getattr(r, "published_date", ""),
        }
        for r in (getattr(response, "results", None) or [])[:max_results]
    ]
    return {
        "keywords": keywords,
        "query": query,
        "provider": getattr(response, "provider", ""),
        "count": len(items),
        "results": items,
        "source_note": (
            "SemiAnalysis 为半导体/AI 一级研究机构，证据强度按 analysis（含产业链一手调研可升 primary）；"
            "付费墙内容只引用可见标题/摘要，勿编造细节。"
        ),
    }


search_semianalysis_tool = ToolDefinition(
    name="search_semianalysis",
    description=(
        "检索 SemiAnalysis（semianalysis.com，半导体 / AI 算力一级研究机构）的文章与数据，"
        "返回标题/摘要/**原文地址 url**/来源/日期。**半导体 / AI 主题必调**（芯片/SoC、HBM/存储、"
        "先进封装/CoWoS、光刻/设备/材料、晶圆代工、GPU/AI 加速卡、数据中心 AI 硬件、硅光子/CPO/"
        "薄膜铌酸锂、电源/散热等），按主题或卡点环节构造关键词（如『HBM3E supply』『CoWoS capacity』"
        "『Blackwell GB200』『薄膜铌酸锂 CPO』）。配置 TAVILY_API_KEYS 后可用。"
    ),
    parameters=[
        ToolParameter(
            name="keywords",
            type="string",
            description="检索关键词（英文优先，按主题/环节构造，如『HBM3E supply』『CoWoS capacity』）",
            required=True,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="最大返回条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_search_semianalysis,
    category="search",
)


ALL_SUPPLY_CHAIN_TOOLS = [score_supply_chain_bottleneck_tool, search_semianalysis_tool]


# ============================================================
# 线索多源炒作检索（用户提供「线索」时，跨国内财经媒体查炒作信号）
# ============================================================

# 固定 5 源：点名的国内财经媒体 + 公司公告 + 全网（兜底东财/腾讯等其它媒体）。
# 每项 (显示名, 站点限定)；站点为 None 表示不做 site: 限定（全网检索）。
_CLUE_HYPE_SOURCES: tuple[tuple[str, Optional[str]], ...] = (
    ("新浪财经", "finance.sina.com.cn"),
    ("雪球", "xueqiu.com"),
    ("同花顺", "10jqka.com.cn"),
    ("巨潮资讯/公司公告", "cninfo.com.cn"),
    ("全网/Google", None),
)
# 线索炒作是近期话题，半年窗
_CLUE_HYPE_DAYS = 180
_CLUE_HYPE_MAX_PER_SOURCE = 3


def _build_clue_hype_query(site: Optional[str], clue: Any) -> str:
    """构造单源检索 query：有站点则 ``site:{site} {clue}``，全网源则裸 clue。"""
    clue_text = str(clue or "").strip()
    if site:
        return f"site:{site} {clue_text}".strip()
    return clue_text


def _hype_signal(mention_sources_count: Any) -> str:
    """按「提及该线索的源数量」给题材炒作信号强度：0=无 / 1-2=弱 / 3-4=中 / ≥5=强。"""
    n = int(mention_sources_count or 0)
    if n <= 0:
        return "无"
    if n <= 2:
        return "弱"
    if n <= 4:
        return "中"
    return "强"


def _handle_search_clue_hype(
    clue: str,
    max_results_per_source: int = 3,
) -> Dict[str, Any]:
    """跨国内财经媒体检索「供应链线索」，返回每源提及情况 + 题材炒作信号强度。

    复用共享 ``SearchService`` provider（配置 ``TAVILY_API_KEYS`` 等后可用）。逐源用
    ``site:`` 限定（全网源不限）调用 ``provider.search()``；**单源异常/失败不拖垮整体**，
    该源计 0 提及、继续其它源。任一源提及线索即题材炒作加分项；提及源越多 hype_signal 越强。
    服务不可用时返回 ``error``，agent 据此标注「待核验」。
    """
    clue_text = (clue or "").strip()
    provider = _pick_search_provider(_get_search_service())
    if provider is None:
        return {
            "error": "搜索引擎不可用（未配置 TAVILY_API_KEYS 等），无法跨源检索线索，请将炒作信号标注「待核验」",
            "clue": clue_text,
        }

    cap = max(1, int(max_results_per_source or _CLUE_HYPE_MAX_PER_SOURCE))
    queried: List[Dict[str, Any]] = []
    mention_sources: List[str] = []
    total_mentions = 0

    for name, site in _CLUE_HYPE_SOURCES:
        query = _build_clue_hype_query(site, clue_text)
        entry: Dict[str, Any] = {
            "source": name,
            "site": site,
            "query": query,
            "mention_count": 0,
            "results": [],
        }
        try:
            response = provider.search(query, max_results=cap, days=_CLUE_HYPE_DAYS)
        except Exception as exc:  # noqa: BLE001 - 单源异常不得拖垮整体检索
            logger.warning("[SupplyChain] 线索炒作检索 %s 异常: %s", name, exc)
            entry["error"] = str(exc)
            queried.append(entry)
            continue

        if not getattr(response, "success", False):
            entry["error"] = getattr(response, "error_message", None) or "搜索失败"
            queried.append(entry)
            continue

        items = [
            {
                "title": getattr(r, "title", ""),
                "url": getattr(r, "url", ""),
                "source": getattr(r, "source", ""),
            }
            for r in (getattr(response, "results", None) or [])[:cap]
        ]
        entry["mention_count"] = len(items)
        entry["results"] = items
        if items:
            mention_sources.append(name)
            total_mentions += len(items)
        queried.append(entry)

    return {
        "clue": clue_text,
        "queried": queried,
        "mention_sources": mention_sources,
        "total_mentions": total_mentions,
        "hype_signal": _hype_signal(len(mention_sources)),
        "note": (
            "任一媒体提及线索即「题材炒作」加分项；提及源越多炒作信号越强（无/弱/中/强）。"
            "把提及源 + 原文链接写入报告「题材炒作信号」小节，并把提及广度纳入 hype_risk（炒作风险）评分。"
        ),
    }


search_clue_hype_tool = ToolDefinition(
    name="search_clue_hype",
    description=(
        "用户提供了「供应链线索」时必调：跨国内财经媒体（新浪财经/雪球/同花顺/巨潮公司公告/全网）"
        "检索该线索，返回每源提及情况、提及源列表与「题材炒作」信号强度（无/弱/中/强）。"
        "任一媒体提及线索即题材炒作加分项（提及源越多炒作信号越强），用于报告『题材炒作信号』小节并纳入 hype_risk 评分。"
    ),
    parameters=[
        ToolParameter(
            name="clue",
            type="string",
            description="供应链线索文本（用户本轮提供的一次性调查目标，如客户/供应商/订单/技术路线/产能关键词）",
            required=True,
        ),
        ToolParameter(
            name="max_results_per_source",
            type="integer",
            description="每个源最多返回条数（默认 3）",
            required=False,
            default=3,
        ),
    ],
    handler=_handle_search_clue_hype,
    category="search",
)


ALL_SUPPLY_CHAIN_TOOLS = [
    score_supply_chain_bottleneck_tool,
    search_semianalysis_tool,
    search_clue_hype_tool,
]
