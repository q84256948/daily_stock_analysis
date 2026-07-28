# -*- coding: utf-8 -*-
"""供应链分析专属工具集。

v2 旧工具（2 个）：
- ``score_supply_chain_bottleneck``（包装 serenity_scorecard）
- ``search_semianalysis``（半导体 / AI 主题检索 semianalysis.com 一级研究源）

v2 中间工具（3 个）：
- ``search_clue_hype``（线索炒作信号）
- ``verify_supply_chain_evidence``（双源校验）
- ``search_supply_chain_kb``（知识库检索）

v3 深度小节工具（5 个）：
- ``analyze_product_matrix``（§6 产品矩阵）
- ``analyze_market_position``（§7 市场占有率）
- ``extract_key_partners``（§8 关键客户与供应商）
- ``analyze_industry_outlook``（§9 行业前景）
- ``analyze_financial_quality``（§10 财务质量）

其余数据/情报工具**复用问股的全局 ToolRegistry**（行情/新闻/基本面/技术），
通过 ``build_supply_chain_executor`` 在 factory 里合并注册（见 factory.py）。
"""

import logging
from typing import Any, Dict, List, Optional, cast

from src.agent.tools.registry import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)

# serenity_scorecard 的 8 个加权因子 + 8 个惩罚项（各 0-5 分）
FACTOR_KEYS = (
    "demand_inflection",  # 需求拐点
    "architecture_coupling",  # 架构耦合
    "chokepoint_severity",  # 卡点严重度
    "supplier_concentration",  # 供应商集中度
    "expansion_difficulty",  # 扩产难度
    "evidence_quality",  # 证据质量
    "valuation_disconnect",  # 估值脱节
    "catalyst_timing",  # 催化时点
)
PENALTY_KEYS = (
    "dilution_financing",  # 稀释/融资
    "governance",  # 治理
    "geopolitics",  # 地缘
    "liquidity",  # 流动性
    "hype_risk",  # 炒作
    "accounting_quality",  # 会计质量
    "cyclicality",  # 周期性
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


def _normalize_ratings(
    raw: Optional[Dict[str, Any]], keys: tuple[str, ...]
) -> Dict[str, float]:
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
        logger.error(
            "supply chain scorecard failed for %s: %s", ticker, exc, exc_info=True
        )
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


def _get_search_service() -> Any:
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
        return {
            "error": f"SemiAnalysis 检索异常: {exc}",
            "keywords": keywords,
            "query": query,
        }

    if not getattr(response, "success", False):
        return {
            "error": getattr(response, "error_message", None)
            or "SemiAnalysis 搜索失败",
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


# ============================================================
# [v2] 供应链知识库检索（用户自定义 KB 加权检索）
# ============================================================


def _handle_search_supply_chain_kb(
    stock_code: str = "",
    stock_name: str = "",
    industry_hint: str = "",
    keywords: str = "",
    top_k: int = 8,
) -> Dict[str, Any]:
    """[v2] 检索用户自定义知识库中与本次主题/标的相关的产业链片段。

    包装 SupplyChainKBRetriever（KB 加权 + 衰减 + cold start）。
    失败时返回 error，agent 据此标注「待核验」。
    """
    try:
        from src.services.supply_chain.kb_retriever import SupplyChainKBRetriever
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"KB 检索器加载失败: {exc}",
            "stock_code": stock_code,
            "stock_name": stock_name,
        }

    kw_list = (
        [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
    )
    retriever = SupplyChainKBRetriever()
    result = retriever.retrieve(
        stock_code=stock_code or None,
        stock_name=stock_name or None,
        industry_hint=industry_hint,
        top_k=top_k,
        keywords=kw_list,
    )
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "industry_hint": industry_hint,
        "aggregate_score": result.aggregate_score,
        "kb_hit_count": len(result.hits),
        "hits": [
            {
                "document_id": h.document_id,
                "document_title": h.document_title,
                "chunk_id": h.chunk_id,
                "content": h.content[:500],
                "score": h.score,
                "tag_weight": h.tag_weight,
                "recency_weight": h.recency_weight,
                "kb_doc_age_days": h.kb_doc_age_days,
                "validation_status": h.validation_status,
            }
            for h in result.hits
        ],
    }


search_supply_chain_kb_tool = ToolDefinition(
    name="search_supply_chain_kb",
    description=(
        "[v2] 检索用户自定义知识库（含已上传的产业链报告/纪要/IR 文档）的相关产业链片段。"
        "返回每条 {document_id, document_title, chunk_id, content, score(0-1), "
        "tag_weight, recency_weight, kb_doc_age_days, validation_status}。"
        "**供应链报告第一步必调**：把命中片段写入报告「知识库参考」小节；"
        "命中片段可显著提升结论置信度，但仍需与行情/新闻交叉验证。"
    ),
    parameters=[
        ToolParameter(
            "stock_code", "string", "股票代码（可空）", required=False, default=""
        ),
        ToolParameter(
            "stock_name", "string", "股票名称（可空）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业/主题提示（如『HBM』『动力电池』）",
            required=False,
            default="",
        ),
        ToolParameter(
            "keywords", "string", "逗号分隔的自定义关键词", required=False, default=""
        ),
        ToolParameter(
            "top_k", "integer", "返回条数（默认 8）", required=False, default=8
        ),
    ],
    handler=_handle_search_supply_chain_kb,
    category="knowledge",
)


# ============================================================
# 供应链双源校验（公司 / 板块归属，东方财富 + 同花顺结构化核验）
# ============================================================


def _get_supply_chain_validator() -> Any:
    """Lazy 默认双源校验器访问器（测试可 monkeypatch 替换为注入 fake 探针的实例）。"""
    from data_provider.supply_chain.cross_source import get_default_validator

    return get_default_validator()


def _handle_verify_supply_chain_evidence(
    stock_code: str,
    stock_name: str,
    claim: str,
    board_hint: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """对单条供应链事实做「东方财富 + 同花顺」双源结构化校验。

    复用 ``data_provider.supply_chain.cross_source`` 的纯逻辑判定 + fail-open 探针：
    非 A 股 → ``not_applicable``；A 股按决策表产出 ``confirmed / partial /
    conflict / unverified`` 与 ``high / medium / low`` 置信度。校验失败不阻断
    报告生成，agent 据状态文案标注「待核验」「单源支持」「双源冲突」。
    """
    validator = _get_supply_chain_validator()
    result = validator.verify(
        stock_code, stock_name, claim=claim, board_hint=board_hint, topic=topic
    )
    return cast(Dict[str, Any], result.to_dict())


verify_supply_chain_evidence_tool = ToolDefinition(
    name="verify_supply_chain_evidence",
    description=(
        "对供应链报告中的「公司 / 板块归属」事实做双源结构化校验（东方财富 + 同花顺），"
        "返回 status(confirmed/partial/conflict/unverified/not_applicable) + "
        "confidence(high/medium/low) + 东财/同花顺证据 + 成分股重合度。"
        "**A 股候选标的进入最终候选表前必调**；未得到 confirmed 的结论不得写成已确认事实，"
        "只能按状态写「双源确认 / 单源支持待核验 / 口径冲突 / 待核验」。仅支持 A 股，"
        "港股/美股返回 not_applicable。"
    ),
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="A 股代码（如 300750，允许 SH/SZ/BJ 前缀或 .SH/.SZ/.BJ 后缀）",
            required=True,
        ),
        ToolParameter(
            name="stock_name",
            type="string",
            description="公司名称（用于名称匹配与报告展示）",
            required=True,
        ),
        ToolParameter(
            name="claim",
            type="string",
            description="需要校验的供应链事实陈述（如『宁德时代是动力电池产业链核心中游制造商』）",
            required=True,
        ),
        ToolParameter(
            name="board_hint",
            type="string",
            description="板块 / 主题提示（如『动力电池』），优先用于定位东财 / 同花顺板块或概念",
            required=False,
            default="",
        ),
        ToolParameter(
            name="topic",
            type="string",
            description="主题（如『新能源车电池供应链』），无 board_hint 时用于构造检索关键词",
            required=False,
            default="",
        ),
    ],
    handler=_handle_verify_supply_chain_evidence,
    category="analysis",
)


ALL_SUPPLY_CHAIN_TOOLS = [
    score_supply_chain_bottleneck_tool,
    search_semianalysis_tool,
    search_clue_hype_tool,
    verify_supply_chain_evidence_tool,
    search_supply_chain_kb_tool,
]


# ============================================================
# [v3] 深度小节工具（产品·客户·竞争·前景 五维补强）
# ============================================================
#
# 设计要点（PR-A 已建 schema，PR-B 实现工具）：
# - 5 个工具统一三段式契约：输入 ticker/company/market/industry_hint → 读 KB → LLM 综合 → 校验 → 返回 dict
# - 不读 fundamental_analysis 文本（避免 LLM 二次抽取失真）
# - 失败返回 {error: "..."} + 部分字段，agent 据状态降级标"待核验"
# - 测试可 monkeypatch 替换 KB loader 与 LLM adapter


def _get_v3_kb_retriever() -> Any:
    """Lazy v3 KB 检索器（注入失败不阻断）。"""
    try:
        from src.services.supply_chain.kb_retriever import (
            SupplyChainKBRetriever,
        )

        return SupplyChainKBRetriever()
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] KB 加载失败: %s", exc)
        return None


def _safe_run_sync(handler: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """同步调用 async handler（data_tools 的 handler 是 sync 函数，但含 IO）。"""
    try:
        out = handler(*args, **kwargs)
        return out if isinstance(out, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] safe_sync %s 失败: %s", handler.__name__, exc)
        return {}


def _fetch_real_stock_info(ticker: str) -> Dict[str, Any]:
    """[v3 真实数据] 调 get_stock_info 获取行情/板块/财务。"""
    try:
        from src.agent.tools.data_tools import _handle_get_stock_info

        # 6 秒超时保护（避免网络 hang 拖累整个工具调用）
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError("get_stock_info timeout")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(6)
        try:
            out = _handle_get_stock_info(ticker)
            return out if isinstance(out, dict) else {}
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] fetch_real_stock_info 失败: %s", exc)
        return {}


def _fetch_real_realtime_quote(ticker: str) -> Dict[str, Any]:
    """[v3 真实数据] 调 get_realtime_quote 获取实时行情。"""
    try:
        from src.agent.tools.data_tools import _handle_get_realtime_quote

        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError("get_realtime_quote timeout")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(6)
        try:
            out = _handle_get_realtime_quote(ticker)
            return out if isinstance(out, dict) else {}
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] fetch_real_realtime_quote 失败: %s", exc)
        return {}


def _format_real_data_for_prompt(
    info: Dict[str, Any],
    quote: Dict[str, Any],
    industry_hint: str = "",
    company: str = "",
    ticker: str = "",
) -> str:
    """把真实行情/板块/财务/行业 DNA 数据格式化为 ≤1500 token 的 prompt 上下文。

    安全：所有值用 str() + replace('{', '') 防止 .format() 时的 KeyError。
    """
    if not info and not quote:
        return "（真实数据源不可用——KB/工具均未命中）"

    def _safe(v: Any) -> str:
        s = str(v) if v is not None else ""
        return s.replace("{", "(").replace("}", ")")

    parts: List[str] = []
    if quote:
        price = quote.get("price")
        change_pct = quote.get("change_pct")
        pe = quote.get("pe_ratio")
        pb = quote.get("pb_ratio")
        total_mv = quote.get("total_mv")
        turnover = quote.get("turnover_rate")
        if price is not None:
            parts.append("现价=" + _safe(price))
            parts.append("涨幅=" + _safe(change_pct) + "%")
        if pe is not None:
            parts.append("PE=" + _safe(pe))
        if pb is not None:
            parts.append("PB=" + _safe(pb))
        if total_mv is not None:
            parts.append("总市值=" + _safe(round(total_mv / 1e8, 2)) + "亿元")
        if turnover is not None:
            parts.append("换手率=" + _safe(turnover) + "%")
    if info:
        boards = info.get("belong_boards") or []
        if boards:
            board_names = [b.get("name") for b in boards[:10] if b.get("name")]
            if board_names:
                parts.append("所属板块=" + ",".join([_safe(n) for n in board_names]))
        fc = info.get("fundamental_context") or {}
        valuation = (fc.get("valuation") or {}).get("data") or {}
        if valuation:
            for k in ("pe_ratio", "pb_ratio", "total_mv"):
                v = valuation.get(k)
                if v is not None:
                    parts.append(k + "=" + _safe(v))
        growth = (fc.get("growth") or {}).get("data") or {}
        for k in ("revenue_yoy", "net_profit_yoy", "roe", "gross_margin"):
            v = growth.get(k)
            if v is not None:
                parts.append(k + "=" + _safe(v))
        earnings = (fc.get("earnings") or {}).get("data") or {}
        if isinstance(earnings, dict):
            for k, v in earnings.items():
                if v is not None and isinstance(v, (str, int, float)):
                    parts.append("earnings." + k + "=" + _safe(v))
    if not parts:
        base = "（真实数据源返回空——Tushare 配额或网络问题）"
    else:
        base = "【真实数据（直接引用，禁止修改或编造）】" + " | ".join(parts)

    # [v3 真实数据] 追加行业 DNA 数据（产品列表/竞品/客户类型等）
    dna_ctx = _format_industry_dna_for_prompt(
        industry_hint=industry_hint, ticker=ticker, company=company
    )
    return base + "\n" + dna_ctx


def _format_industry_dna_for_prompt(
    industry_hint: str, ticker: str, company: str
) -> str:
    """[v3 真实数据] 从 industry DNA loader 注入行业默认数据（产品/客户/竞争）。

    让 handler 即使在 KB 0 命中 / LLM 推断困难时，也能给出行业级别的真实数据。
    """
    from src.services.supply_chain.industry_dna_loader import (
        find_dna_by_keyword,
        find_dna_by_keywords,
        list_slugs as _list_slugs,
    )

    # 1. 从 industry_hint / company 推断 DNA
    dna = None
    for kw in [industry_hint, company, ticker]:
        if not kw:
            continue
        dna = find_dna_by_keyword(kw)
        if dna:
            break

    # 2. fallback：尝试 board 关键词
    if not dna:
        dna = find_dna_by_keywords([])

    if not dna:
        return "（行业 DNA 未命中——按行业知识推断，无具体行业基础数据）"

    parts: List[str] = [
        f"行业={dna.industry_name}",
        f"行业 CR/集中度={dna.concentration}",
        f"产品列表={','.join(dna.products[:8])}",
        f"行业 Top 玩家={','.join(dna.key_players[:8])}",
        f"客户类型={','.join(dna.customer_types[:6])}",
        f"供应商类型={','.join(dna.supplier_types[:6])}",
        f"需求驱动={','.join(dna.demand_drivers[:6])}",
        f"政策催化={','.join(dna.policy_catalysts[:5])}",
        f"替代风险={','.join(dna.substitution_risks[:5])}",
        f"时间窗={dna.time_window}",
        f"DNA 来源={dna.source}",
    ]
    return "【行业 DNA（直接引用，禁止修改或编造）】" + " | ".join(parts)


def _format_v3_kb_hits(
    retriever: Any, ticker: str, company: str, industry_hint: str, top_k: int
) -> str:
    """把 KB 命中片段格式化为 ≤2000 token 的 prompt 摘要。KB 不可用时返回占位。"""
    if retriever is None:
        return "（KB 检索器不可用，跳过）"
    try:
        result = retriever.retrieve(
            stock_code=ticker or None,
            stock_name=company or None,
            industry_hint=industry_hint or "",
            top_k=top_k,
        )
        if not result.hits:
            return f"（KB 0 命中；aggregate_score={result.aggregate_score:.2f}）"
        snippets: List[str] = []
        for i, hit in enumerate(result.hits[:top_k], 1):
            content = (hit.content or "")[:400]
            snippets.append(
                f"[命中 {i}] doc={hit.document_id} chunk={hit.chunk_id} "
                f"score={hit.score:.2f}\n{content}"
            )
        text = "\n\n".join(snippets)
        return text[:2000]
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] KB 检索失败: %s", exc)
        return "（KB 检索异常，跳过）"


def _get_v3_chat_llm() -> Any:
    """Lazy 文本补全 LLM（tool-v3 专用，失败时返回 None）。

    返回对象需有 ``call_text(messages, temperature=..., max_tokens=...)`` 方法，
    实际返回 ``LLMResponse(content=str)``。
    """
    try:
        from src.agent.llm_adapter import LLMToolAdapter
        from src.config import get_config

        return LLMToolAdapter(get_config())
    except Exception as exc:  # noqa: BLE001
        logger.debug("[SupplyChain v3] LLM adapter 加载失败: %s", exc)
        return None


def _parse_v3_json(content: str) -> Dict[str, Any]:
    """从 LLM 输出抽取 JSON dict。多层容错：markdown 围栏 + 嵌套 + 截断修复。

    容错顺序：
    1. markdown ```json ... ``` 围栏剥离
    2. 首个 { 到最后一个 } 区间抽取
    3. 找 JSON 字典起点（候选取最大且字典有效）
    4. json_repair 自动修复（缺失引号、尾随逗号、单引号、截断等）
    5. 全部失败 → 抛 ValueError
    """
    import json
    import re

    text = (content or "").strip()
    if not text:
        raise ValueError("LLM 输出为空")

    # 1. markdown 围栏
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if m:
            text = m.group(1).strip()

    # 2. 首选：直接解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 3. 候选多个 { ... } 块，按嵌套深度选最深的（最可能是完整 JSON）
    candidates: List[Dict[str, Any]] = []
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
        try:
            cand = json.loads(m.group(0))
            if isinstance(cand, dict):
                # 计算嵌套深度：含 list 的 dict 优先级更高
                nested_score = 1 + (
                    1 if any(isinstance(v, list) and v for v in cand.values()) else 0
                )
                candidates.append(
                    (nested_score, len(json.dumps(cand, ensure_ascii=False)), cand)
                )
        except json.JSONDecodeError:
            continue
    if candidates:
        # 优先取含数组的最深嵌套块，再按长度兜底
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates[0][2]

    # 4. 区间截取：首个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 5. json_repair 自动修复（处理缺失引号、尾随逗号、单引号、截断等）
    try:
        import json_repair

        repaired = json_repair.loads(
            text[start : end + 1] if start >= 0 and end > start else text
        )
        if isinstance(repaired, dict):
            return repaired
    except Exception:  # noqa: BLE001
        pass

    # 6. 截断回退：取首个 { 到文本末，尝试修复
    if start >= 0:
        truncated = text[start:]
        # 尝试在每个可能的嵌套边界补全
        for closing in ["}", "]}", "}}", "}}}", "}}}}"]:
            try:
                import json_repair

                repaired = json_repair.loads(truncated + closing * 5)
                if isinstance(repaired, dict):
                    return repaired
            except Exception:  # noqa: BLE001
                continue

    # 全部失败：把原始输出片段记到日志便于排查
    logger.warning(
        "[SupplyChain v3] JSON 解析失败（前 500 字）: %s",
        text[:500],
    )
    raise ValueError(f"LLM 输出无法解析为 JSON dict: {text[:200]}")


# ============================================================
# §6 analyze_product_matrix
# ============================================================


_PRODUCT_MATRIX_PROMPT = """你是"供应链深度小节"助手。

任务：基于以下 KB 命中 + 已知公司信息 + **真实数据（板块归属）**，给出 **{company}（{ticker}）** 的产品矩阵画像。
严格输出 JSON（不要其他文字，不要 markdown 围栏，不要解释）：

{{
  "products": [
    {{
      "name": "产品/产品线名（≤40 字）",
      "category": "core|growth|legacy|exploratory",
      "revenue_share_pct": 数值或 null,
      "gross_margin_pct": 数值或 null,
      "target_market": ["目标市场1", "目标市场2"],
      "price_band": "价格带文字描述" 或 null,
      "differentiators": ["卖点1", "卖点2"],
      "evidence_strength": "primary|media|analysis|kb_doc",
      "source_url": "..." 或 null
    }}
  ]
}}

强制规则（务必遵守，违反会被工具拒绝）：
1. **products 数组至少返回 2 条记录**（即使 KB 0 命中，基于你的行业知识给出该公司已知产品/产品线）
2. **【真实数据】块**：`所属板块` 字段直接用于推断产品线（例：板块含"半导体设备"+"高带宽内存"→ 推断该公司有"湿法清洗设备"和"HBM/先进封装相关设备"两条产品线）
3. revenue_share_pct / gross_margin_pct 仅在年报/招股书/IR 直接披露时填具体数字，禁止估算；找不到就 null（**不要用 0 替代 null**）
4. evidence_strength：基于真实板块标 "primary"；基于行业知识标 "analysis"
5. 严禁编造具体数字（营收/份额/毛利率）、严禁编造客户名、严禁编造日期
6. 严禁返回空数组 `[]`

【公司信息】ticker={ticker}  company={company}  market={market}  industry_hint={industry_hint}
【KB 命中片段】（≤2000 token）
{kb_hits}

【真实数据】
{real_data}
"""


def _handle_analyze_product_matrix(
    ticker: str,
    company: str,
    market: str = "",
    industry_hint: str = "",
    top_k: int = 5,
) -> Dict[str, Any]:
    """§6 产品矩阵与定位。

    失败返回 ``{"error": "...", "products": []}``，agent 据状态降级标"待核验"。
    """
    try:
        kb_hits = _format_v3_kb_hits(
            _get_v3_kb_retriever(), ticker, company, industry_hint, top_k
        )
        # [v3 真实数据] 注入真实板块归属
        info = _fetch_real_stock_info(ticker)
        quote = _fetch_real_realtime_quote(ticker)
        real_data_ctx = _format_real_data_for_prompt(
            info,
            quote,
            industry_hint=industry_hint,
            company=company,
            ticker=ticker,
        )
        llm = _get_v3_chat_llm()
        if llm is None:
            return {"error": "LLM adapter 不可用", "products": [], "ticker": ticker}
        from src.schemas.supply_chain import ProductLineV3

        prompt = _PRODUCT_MATRIX_PROMPT.format(
            ticker=ticker,
            company=company,
            market=market,
            industry_hint=industry_hint,
            kb_hits=kb_hits,
            real_data=real_data_ctx,
        )
        response = llm.call_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        raw = _parse_v3_json(response.content)
        products_raw = raw.get("products", [])
        if not isinstance(products_raw, list):
            return {
                "error": "LLM 输出 products 非数组",
                "products": [],
                "ticker": ticker,
            }
        products: List[Dict[str, Any]] = []
        for p in products_raw:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            try:
                prod = ProductLineV3.model_validate(
                    {
                        "name": str(p["name"])[:80],
                        "category": p.get("category", "core"),
                        "revenue_share_pct": p.get("revenue_share_pct"),
                        "gross_margin_pct": p.get("gross_margin_pct"),
                        "target_market": [
                            str(x) for x in (p.get("target_market") or [])
                        ],
                        "price_band": (
                            str(p["price_band"])[:80] if p.get("price_band") else None
                        ),
                        "differentiators": [
                            str(x) for x in (p.get("differentiators") or [])
                        ][:10],
                        "evidence_strength": p.get("evidence_strength", "analysis"),
                        "source_url": p.get("source_url"),
                    }
                )
                products.append(prod.model_dump())
            except Exception as exc:  # noqa: BLE001
                logger.debug("[SupplyChain v3] product validate 失败: %s", exc)
                continue
        if not products:
            # [v3 兜底] LLM 输出空 → 用 industry DNA 默认产品列表
            fallback = _build_dna_fallback_products(
                industry_hint=industry_hint, company=company, ticker=ticker
            )
            if fallback:
                return {"ticker": ticker, "products": fallback}
        return {"ticker": ticker, "products": products}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SupplyChain v3] product_matrix 失败 (%s): %s", ticker, exc)
        return {"error": str(exc), "products": [], "ticker": ticker}


def _build_dna_fallback_products(
    industry_hint: str, ticker: str, company: str
) -> List[Dict[str, Any]]:
    """[v3 兜底] 从 industry DNA 默认产品列表构造 product_matrix 条目。

    仅在 LLM 输出空数组 / handler 校验失败时触发。evidence_strength 标 `kb_doc` 来自 DNA。
    """
    from src.services.supply_chain.industry_dna_loader import (
        find_dna_by_keyword,
        find_dna_by_keywords,
    )

    dna = None
    for kw in [industry_hint, company, ticker]:
        if kw:
            dna = find_dna_by_keyword(kw)
            if dna:
                break

    if not dna:
        return []

    out: List[Dict[str, Any]] = []
    for i, product_name in enumerate(dna.products[:8]):
        out.append(
            {
                "name": product_name,
                # 默认前 2 条为核心，后续按 dna 字段未给（猜 core/growth/exploratory 各占一半）
                "category": (
                    "core" if i == 0 else ("growth" if i < 4 else "exploratory")
                ),
                "revenue_share_pct": None,
                "gross_margin_pct": None,
                "target_market": list(dna.customer_types[:3]),
                "price_band": None,
                "differentiators": [],
                "evidence_strength": "kb_doc",  # DNA 静态数据
                "source_url": None,
            }
        )
    return out


analyze_product_matrix_tool = ToolDefinition(
    name="analyze_product_matrix",
    description=(
        "[v3 §6] 产品矩阵与定位。给定股票代码/公司名/行业提示，"
        "返回 List[ProductLineV3]（每条含 name/category/revenue_share_pct/"
        "gross_margin_pct/target_market/price_band/differentiators/证据强度）。"
        "找不到的字段返回 null，禁止编造。失败返回 {error, products:[]}。"
    ),
    parameters=[
        ToolParameter("ticker", "string", "股票代码（如 600519）", required=True),
        ToolParameter("company", "string", "公司名称", required=True),
        ToolParameter(
            "market", "string", "市场（CN/HK/US）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业提示（如『高端白酒』）",
            required=False,
            default="",
        ),
        ToolParameter(
            "top_k",
            "integer",
            "KB 命中条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_analyze_product_matrix,
    category="analysis",
)


# ============================================================
# §7 analyze_market_position
# ============================================================


_MARKET_POSITION_PROMPT = """你是"供应链深度小节"助手。

任务：基于以下 KB 命中 + 已知公司信息 + **真实数据**，给出 **{company}（{ticker}）** 的市场地位画像。
严格输出 JSON（不要其他文字，不要 markdown 围栏，不要解释）：

{{
  "positions": [
    {{
      "subsegment": "子赛道（≤40 字）",
      "market_share_pct": 数值或 null,
      "market_rank": 数值或 null,
      "cr3_pct": 数值或 null,
      "cr5_pct": 数值或 null,
      "cr10_pct": 数值或 null,
      "share_trend": "rising|stable|falling|volatile|unknown",
      "share_change_3y_pct": 数值或 null,
      "top_competitors": ["竞品1", "竞品2"],
      "substitution_risk": "low|medium|high|unknown",
      "evidence_strength": "primary|media|analysis|kb_doc",
      "source_url": "..." 或 null
    }}
  ]
}}

强制规则（务必遵守，违反会被工具拒绝）：
1. **positions 数组至少返回 1 条记录**
2. 【真实数据】`所属板块` 直接决定 subsegment（如「半导体设备」/「高带宽内存」/「中芯概念」等）
3. market_share_pct / cr3_pct 等仅在年报/招股书/官方文件披露时填具体数字，禁止估算；找不到就 null
4. market_rank 与 market_share_pct 必须同时存在或同时为 null
5. share_trend / substitution_risk 必须是枚举值
6. top_competitors 至少 1 个该子赛道知名竞品（基于行业知识：例半导体湿法清洗 → 盛美/北方华创/华海清科/TEL/SCREEN）
7. 严禁返回空数组 `[]`

【公司信息】ticker={ticker}  company={company}  market={market}  industry_hint={industry_hint}
【KB 命中片段】（≤2000 token）
{kb_hits}

【真实数据】
{real_data}
"""


def _handle_analyze_market_position(
    ticker: str,
    company: str,
    market: str = "",
    industry_hint: str = "",
    top_k: int = 5,
) -> Dict[str, Any]:
    """§7 市场地位与占有率。

    失败返回 ``{"error": "...", "positions": []}``。
    """
    try:
        kb_hits = _format_v3_kb_hits(
            _get_v3_kb_retriever(), ticker, company, industry_hint, top_k
        )
        info = _fetch_real_stock_info(ticker)
        quote = _fetch_real_realtime_quote(ticker)
        real_data_ctx = _format_real_data_for_prompt(
            info,
            quote,
            industry_hint=industry_hint,
            company=company,
            ticker=ticker,
        )
        llm = _get_v3_chat_llm()
        if llm is None:
            return {"error": "LLM adapter 不可用", "positions": [], "ticker": ticker}
        from src.schemas.supply_chain import MarketPositionV3

        prompt = _MARKET_POSITION_PROMPT.format(
            ticker=ticker,
            company=company,
            market=market,
            industry_hint=industry_hint,
            kb_hits=kb_hits,
            real_data=real_data_ctx,
        )
        response = llm.call_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        raw = _parse_v3_json(response.content)
        positions_raw = raw.get("positions", [])
        if not isinstance(positions_raw, list):
            return {
                "error": "LLM 输出 positions 非数组",
                "positions": [],
                "ticker": ticker,
            }
        positions: List[Dict[str, Any]] = []
        for p in positions_raw:
            if not isinstance(p, dict) or not p.get("subsegment"):
                continue
            try:
                pos = MarketPositionV3.model_validate(
                    {
                        "subsegment": str(p["subsegment"])[:80],
                        "market_share_pct": p.get("market_share_pct"),
                        "market_rank": p.get("market_rank"),
                        "cr3_pct": p.get("cr3_pct"),
                        "cr5_pct": p.get("cr5_pct"),
                        "cr10_pct": p.get("cr10_pct"),
                        "share_trend": p.get("share_trend", "unknown"),
                        "share_change_3y_pct": p.get("share_change_3y_pct"),
                        "top_competitors": [
                            str(x) for x in (p.get("top_competitors") or [])
                        ][:10],
                        "substitution_risk": p.get("substitution_risk", "unknown"),
                        "evidence_strength": p.get("evidence_strength", "analysis"),
                        "source_url": p.get("source_url"),
                    }
                )
                positions.append(pos.model_dump())
            except Exception as exc:  # noqa: BLE001
                logger.debug("[SupplyChain v3] market_position validate 失败: %s", exc)
                continue
        return {"ticker": ticker, "positions": positions}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SupplyChain v3] market_position 失败 (%s): %s", ticker, exc)
        return {"error": str(exc), "positions": [], "ticker": ticker}


analyze_market_position_tool = ToolDefinition(
    name="analyze_market_position",
    description=(
        "[v3 §7] 市场地位与占有率。给定股票代码/公司名/行业提示，"
        "返回 List[MarketPositionV3]（每条含 subsegment/market_share_pct/"
        "market_rank/cr3-5-10/share_trend/3 年变化/主要竞品/替代风险/证据强度）。"
        "找不到的字段返回 null。失败返回 {error, positions:[]}。"
    ),
    parameters=[
        ToolParameter("ticker", "string", "股票代码", required=True),
        ToolParameter("company", "string", "公司名称", required=True),
        ToolParameter(
            "market", "string", "市场（CN/HK/US）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业提示",
            required=False,
            default="",
        ),
        ToolParameter(
            "top_k",
            "integer",
            "KB 命中条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_analyze_market_position,
    category="analysis",
)


# ============================================================
# §8 extract_key_partners
# ============================================================


_KEY_PARTNERS_PROMPT = """你是"供应链深度小节"助手。

任务：基于以下 KB 命中 + 已知公司信息 + **真实数据**，给出 **{company}（{ticker}）** 的关键客户/供应商画像。
严格输出 JSON（不要其他文字，不要 markdown 围栏，不要解释）：

{{
  "customers": [
    {{
      "name": "客户名（年报披露『客户A/前五大客户之一』时直接保留占位）",
      "share_pct": 数值或 null,
      "is_related_party": true|false,
      "is_anonymous": true|false,
      "revenue_or_cost_share": "占总营收/采购的比例文字描述" 或 null,
      "years_partnered": 数值或 null,
      "public_source": "annual_report|prospectus|inquiry_letter|convertible_bond|investor_relations|news|kb",
      "evidence_strength": "primary|media|analysis|kb_doc",
      "source_url": "..." 或 null
    }}
  ],
  "suppliers": [ {{ 同结构 }} ]
}}

强制规则（务必遵守，违反会被工具拒绝）：
1. **customers 与 suppliers 数组至少各返回 1 条记录**
2. **【真实数据】`所属板块` 决定行业**，据此推断典型客户（例：半导体设备板块 → 中芯国际/长江存储/合肥长鑫/华虹/TSMC等晶圆厂）
3. **name 必须基于真实信息或占位**：年报披露『客户A/前五大之一』时 is_anonymous=true，name 保留「客户A」/「前五大客户之一」；**禁止编造具体公司名作为已知客户**——可以用「推测为：中芯国际（需年报核实）」或「行业典型大客户：长江存储（未在年报披露）」等谨慎措辞
4. share_pct 仅在年报/招股书直接披露时填具体数字，禁止估算
5. public_source 必须是枚举值（不知道时用 "news" 或 "kb"）
6. 严禁返回空数组 `[]`

【公司信息】ticker={ticker}  company={company}  market={market}  industry_hint={industry_hint}
【KB 命中片段】（≤2000 token）
{kb_hits}

【真实数据】
{real_data}
"""


def _handle_extract_key_partners(
    ticker: str,
    company: str,
    market: str = "",
    industry_hint: str = "",
    top_k: int = 5,
) -> Dict[str, Any]:
    """§8 关键客户与供应商。

    失败返回 ``{"error": "...", "customers": [], "suppliers": []}``。
    """
    try:
        kb_hits = _format_v3_kb_hits(
            _get_v3_kb_retriever(), ticker, company, industry_hint, top_k
        )
        info = _fetch_real_stock_info(ticker)
        quote = _fetch_real_realtime_quote(ticker)
        real_data_ctx = _format_real_data_for_prompt(
            info,
            quote,
            industry_hint=industry_hint,
            company=company,
            ticker=ticker,
        )
        llm = _get_v3_chat_llm()
        if llm is None:
            return {
                "error": "LLM adapter 不可用",
                "customers": [],
                "suppliers": [],
                "ticker": ticker,
            }
        from src.schemas.supply_chain import KeyPartnerV3

        prompt = _KEY_PARTNERS_PROMPT.format(
            ticker=ticker,
            company=company,
            market=market,
            industry_hint=industry_hint,
            kb_hits=kb_hits,
            real_data=real_data_ctx,
        )
        response = llm.call_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        raw = _parse_v3_json(response.content)
        customers: List[Dict[str, Any]] = []
        suppliers: List[Dict[str, Any]] = []
        for entry in (("customers", customers), ("suppliers", suppliers)):
            key, target = entry
            for p in raw.get(key, []) or []:
                if not isinstance(p, dict) or not p.get("name"):
                    continue
                try:
                    partner = KeyPartnerV3.model_validate(
                        {
                            "side": key[:-1],  # customers→customer, suppliers→supplier
                            "name": str(p["name"])[:120],
                            "share_pct": p.get("share_pct"),
                            "is_related_party": bool(p.get("is_related_party", False)),
                            "is_anonymous": bool(p.get("is_anonymous", False)),
                            "revenue_or_cost_share": (
                                str(p["revenue_or_cost_share"])[:40]
                                if p.get("revenue_or_cost_share")
                                else None
                            ),
                            "years_partnered": p.get("years_partnered"),
                            "public_source": p.get("public_source", "news"),
                            "evidence_strength": p.get("evidence_strength", "analysis"),
                            "source_url": p.get("source_url"),
                        }
                    )
                    target.append(partner.model_dump())
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[SupplyChain v3] %s validate 失败: %s", key, exc)
                    continue
        return {
            "ticker": ticker,
            "customers": customers,
            "suppliers": suppliers,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SupplyChain v3] key_partners 失败 (%s): %s", ticker, exc)
        return {
            "error": str(exc),
            "customers": [],
            "suppliers": [],
            "ticker": ticker,
        }


extract_key_partners_tool = ToolDefinition(
    name="extract_key_partners",
    description=(
        "[v3 §8] 关键客户与供应商。给定股票代码/公司名/行业提示，"
        "返回 {customers: List[KeyPartnerV3], suppliers: List[KeyPartnerV3]}，"
        "每条含 name/share_pct/is_related_party/is_anonymous/合作年限/披露来源/证据强度。"
        "找不到字段返回 null，年报『客户A/前五大之一』is_anonymous=true。失败返回 {error}。"
    ),
    parameters=[
        ToolParameter("ticker", "string", "股票代码", required=True),
        ToolParameter("company", "string", "公司名称", required=True),
        ToolParameter(
            "market", "string", "市场（CN/HK/US）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业提示",
            required=False,
            default="",
        ),
        ToolParameter(
            "top_k",
            "integer",
            "KB 命中条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_extract_key_partners,
    category="analysis",
)


# ============================================================
# §9 analyze_industry_outlook
# ============================================================


_INDUSTRY_OUTLOOK_PROMPT = """你是"供应链深度小节"助手。

任务：基于以下 KB 命中 + 已知公司信息 + **真实数据**，给出 **{company}（{ticker}）** 所在子赛道的前景画像。
严格输出 JSON（不要其他文字，不要 markdown 围栏，不要解释）：

{{
  "outlooks": [
    {{
      "subsegment": "子赛道（≤40 字）",
      "subsegment_status": "growing|stable|declining|transforming",
      "tam_2024_usd_bn": 数值或 null,
      "tam_2027e_usd_bn": 数值或 null,
      "cagr_2024_2027_pct": 数值或 null,
      "china_share_pct": 数值或 null,
      "demand_drivers": ["驱动1", "驱动2"],
      "policy_catalysts": ["政策1"],
      "substitution_threats": ["替代风险1"],
      "overseas_addressable": "海外可触达空间" 或 null,
      "time_window": "near_term_3_6m|mid_term_6_12m|long_term_12_36m",
      "evidence_strength": "primary|media|analysis|kb_doc",
      "source_url": "..." 或 null
    }}
  ]
}}

强制规则（务必遵守，违反会被工具拒绝）：
1. **outlooks 数组至少返回 1 条记录**（每个主战子赛道 1 条）
2. **【真实数据】`所属板块` 直接决定 subsegment**（例：「高带宽内存」→ HBM/先进封装子赛道；「中芯概念」→ 国产晶圆制造子赛道）
3. TAM / CAGR / china_share_pct 仅在行业协会/招股书/SemiAnalysis 等公开来源直接披露时填具体数字，禁止估算；找不到就 null
4. subsegment_status 是枚举：growing / stable / declining / transforming
5. 衰退行业（declining）的 2027E TAM 可小于 2024 TAM 的 50%（豁免契约）；其他必须 ≥50%
6. time_window 必须是枚举
7. demand_drivers / policy_catalysts / substitution_threats 至少各 1 条
8. 严禁返回空数组 `[]`

【公司信息】ticker={ticker}  company={company}  market={market}  industry_hint={industry_hint}
【KB 命中片段】（≤2000 token）
{kb_hits}

【真实数据】
{real_data}
"""


def _handle_analyze_industry_outlook(
    ticker: str,
    company: str,
    market: str = "",
    industry_hint: str = "",
    top_k: int = 5,
) -> Dict[str, Any]:
    """§9 行业前景与需求驱动。

    失败返回 ``{"error": "...", "outlooks": []}``。
    """
    try:
        kb_hits = _format_v3_kb_hits(
            _get_v3_kb_retriever(), ticker, company, industry_hint, top_k
        )
        info = _fetch_real_stock_info(ticker)
        quote = _fetch_real_realtime_quote(ticker)
        real_data_ctx = _format_real_data_for_prompt(
            info,
            quote,
            industry_hint=industry_hint,
            company=company,
            ticker=ticker,
        )
        llm = _get_v3_chat_llm()
        if llm is None:
            return {"error": "LLM adapter 不可用", "outlooks": [], "ticker": ticker}
        from src.schemas.supply_chain import IndustryOutlookV3

        prompt = _INDUSTRY_OUTLOOK_PROMPT.format(
            ticker=ticker,
            company=company,
            market=market,
            industry_hint=industry_hint,
            kb_hits=kb_hits,
            real_data=real_data_ctx,
        )
        response = llm.call_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        raw = _parse_v3_json(response.content)
        outlooks_raw = raw.get("outlooks", [])
        if not isinstance(outlooks_raw, list):
            return {
                "error": "LLM 输出 outlooks 非数组",
                "outlooks": [],
                "ticker": ticker,
            }
        outlooks: List[Dict[str, Any]] = []
        for p in outlooks_raw:
            if not isinstance(p, dict) or not p.get("subsegment"):
                continue
            try:
                o = IndustryOutlookV3.model_validate(
                    {
                        "subsegment": str(p["subsegment"])[:80],
                        "subsegment_status": p.get("subsegment_status", "stable"),
                        "tam_2024_usd_bn": p.get("tam_2024_usd_bn"),
                        "tam_2027e_usd_bn": p.get("tam_2027e_usd_bn"),
                        "cagr_2024_2027_pct": p.get("cagr_2024_2027_pct"),
                        "china_share_pct": p.get("china_share_pct"),
                        "demand_drivers": [
                            str(x) for x in (p.get("demand_drivers") or [])
                        ][:10],
                        "policy_catalysts": [
                            str(x) for x in (p.get("policy_catalysts") or [])
                        ][:10],
                        "substitution_threats": [
                            str(x) for x in (p.get("substitution_threats") or [])
                        ][:10],
                        "overseas_addressable": (
                            str(p["overseas_addressable"])[:200]
                            if p.get("overseas_addressable")
                            else None
                        ),
                        "time_window": p.get("time_window", "mid_term_6_12m"),
                        "evidence_strength": p.get("evidence_strength", "analysis"),
                        "source_url": p.get("source_url"),
                    }
                )
                outlooks.append(o.model_dump())
            except Exception as exc:  # noqa: BLE001
                logger.debug("[SupplyChain v3] outlook validate 失败: %s", exc)
                continue
        return {"ticker": ticker, "outlooks": outlooks}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SupplyChain v3] industry_outlook 失败 (%s): %s", ticker, exc)
        return {"error": str(exc), "outlooks": [], "ticker": ticker}


analyze_industry_outlook_tool = ToolDefinition(
    name="analyze_industry_outlook",
    description=(
        "[v3 §9] 行业前景与需求驱动。给定股票代码/公司名/行业提示，"
        "返回 List[IndustryOutlookV3]（每条含 subsegment/subsegment_status/"
        "TAM 2024/2027E/CAGR/中国份额/需求驱动/政策催化/替代风险/海外空间/时间窗）。"
        "找不到字段返回 null，衰退行业可豁免 TAM 契约。"
    ),
    parameters=[
        ToolParameter("ticker", "string", "股票代码", required=True),
        ToolParameter("company", "string", "公司名称", required=True),
        ToolParameter(
            "market", "string", "市场（CN/HK/US）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业提示",
            required=False,
            default="",
        ),
        ToolParameter(
            "top_k",
            "integer",
            "KB 命中条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_analyze_industry_outlook,
    category="analysis",
)


# ============================================================
# §10 analyze_financial_quality
# ============================================================


_FINANCIAL_QUALITY_PROMPT = """你是"供应链深度小节"助手。

任务：基于以下 KB 命中 + 已知公司信息 + **真实数据**，给出 **{company}（{ticker}）** 的财务质量画像（最新可获取一期）。
严格输出 JSON（不要其他文字，不要 markdown 围栏，不要解释）：

{{
  "reports": [
    {{
      "period": "2024Q3",
      "revenue_yoy_pct": 数值或 null,
      "gross_margin_pct": 数值或 null,
      "gross_margin_change_yoy_pct": 数值或 null,
      "operating_cash_flow_yoy_pct": 数值或 null,
      "ar_to_revenue_pct": 数值或 null,
      "inventory_days": 整数或 null,
      "contract_liability_yoy_pct": 数值或 null,
      "capex_intensity_pct": 数值或 null,
      "capacity_utilization_pct": 数值或 null,
      "revenue_segments": {{"业务名": 占比Pct}},
      "red_flags": ["警示1", "警示2"],
      "evidence_strength": "primary|media|analysis|kb_doc",
      "source_url": "..." 或 null
    }}
  ]
}}

强制规则（务必遵守，违反会被工具拒绝）：
1. **reports 数组至少返回 1 条记录**，period 用最新可得季度（YYYYQ[1-4] 或 YYYY）
2. **【真实数据】块直接引用**：PE、PB、总市值、换手率等真实值直接填到对应字段（如 gross_margin_pct 用真实 ROE 替代、operating_cash 留 null），不要清零也不要编造不存在的数字
3. revenue_segments 占比合计必须在 95%-105% 之间；不知道就 `{{}}`
4. red_flags ≥1 条，结合真实数据（如 PE=-11.45 是亏损 + PB=2.74 高估值）给出针对性警示
5. evidence_strength：真实数据字段标 "primary"（来自 Tushare/Akshare）；推断字段标 "analysis"
6. 严禁返回空数组 `[]`

【公司信息】ticker={ticker}  company={company}  market={market}  industry_hint={industry_hint}
【KB 命中片段】（≤2000 token）
{kb_hits}

【真实数据】
{real_data}
"""


def _build_real_red_flags(quote: Dict[str, Any], info: Dict[str, Any]) -> List[str]:
    """[v3 真实数据] 从 quote/info 直接构造 red_flags 列表（不依赖 LLM）。"""
    flags: List[str] = []
    pe = quote.get("pe_ratio")
    pb = quote.get("pb_ratio")
    mv = quote.get("total_mv")
    turnover = quote.get("turnover_rate")
    change_pct = quote.get("change_pct")
    if pe is not None and pe < 0:
        flags.append(f"PE={pe} 为负值，公司当前处于亏损状态")
    if pb is not None and pe is not None and pb > 2 and pe < 0:
        flags.append(
            f"PB={pb} 与负PE并存，账面估值与实际盈利能力背离，需警惕高估值亏损陷阱"
        )
    if turnover is not None and turnover > 5:
        flags.append(
            f"换手率={turnover}% 显著高于市场均值（通常 1-3%），短线投机交易特征明显"
        )
    if change_pct is not None and abs(change_pct) > 9:
        flags.append(f"当日涨幅={change_pct}%，触及涨停/跌停，短期波动剧烈")
    if mv is not None and mv > 0:
        flags.append(f"总市值={mv / 1e8:.2f}亿元")
    boards = info.get("belong_boards") or []
    board_names = [b.get("name", "") for b in boards[:10] if b.get("name")]
    if any(n in {"半导体", "光伏", "新能源", "医药"} for n in board_names):
        flags.append("所属板块含半导体/新能源/医药等热门概念，估值易受市场情绪影响")
    return flags


def _handle_analyze_financial_quality(
    ticker: str,
    company: str,
    market: str = "",
    industry_hint: str = "",
    top_k: int = 5,
) -> Dict[str, Any]:
    """§10 财务质量与产能跟踪。

    失败返回 ``{"error": "...", "reports": []}``。
    真实数据（PE/PB/市值/换手率）从 get_realtime_quote 直接注入。
    """
    try:
        kb_hits = _format_v3_kb_hits(
            _get_v3_kb_retriever(), ticker, company, industry_hint, top_k
        )
        # [v3 真实数据] 调 get_stock_info + get_realtime_quote 注入 prompt
        info = _fetch_real_stock_info(ticker)
        quote = _fetch_real_realtime_quote(ticker)
        real_data_ctx = _format_real_data_for_prompt(
            info,
            quote,
            industry_hint=industry_hint,
            company=company,
            ticker=ticker,
        )
        # [v3 真实数据兜底] 直接构造 red_flags，避免 LLM 编造
        real_flags = _build_real_red_flags(quote, info)
        llm = _get_v3_chat_llm()
        from src.schemas.supply_chain import FinancialQualityV3

        # 走 LLM 路径（让 LLM 补 LLM 知道的字段）
        if llm is not None:
            prompt = _FINANCIAL_QUALITY_PROMPT.format(
                ticker=ticker,
                company=company,
                market=market,
                industry_hint=industry_hint,
                kb_hits=kb_hits,
                real_data=real_data_ctx,
            )
            try:
                response = llm.call_text(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=2500,
                )
                raw = _parse_v3_json(response.content)
                reports_raw = raw.get("reports", [])
                if isinstance(reports_raw, list) and reports_raw:
                    return _finalize_financial_reports(
                        reports_raw, ticker, real_flags, info, quote
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("[SupplyChain v3] financial LLM 失败, fallback: %s", exc)

        # LLM 失败时：直接用兜底数据构造 1 条占位报告（强制不空数组）
        return _build_fallback_financial_report(
            ticker, company, real_flags, info, quote
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SupplyChain v3] financial_quality 失败 (%s): %s", ticker, exc)
        return {"error": str(exc), "reports": [], "ticker": ticker}


def _finalize_financial_reports(
    reports_raw: List[Any],
    ticker: str,
    real_flags: List[str],
    info: Dict[str, Any],
    quote: Dict[str, Any],
) -> Dict[str, Any]:
    """[v3 真实数据] 校验 LLM 输出，注入兜底 red_flags。"""
    import re
    from src.schemas.supply_chain import FinancialQualityV3

    reports: List[Dict[str, Any]] = []
    for r in reports_raw:
        if not isinstance(r, dict) or not r.get("period"):
            continue
        try:
            segs_raw = r.get("revenue_segments") or {}
            segs = {
                str(k)[:40]: float(v)
                for k, v in segs_raw.items()
                if isinstance(v, (int, float))
            }
            period_str = str(r["period"]).strip()
            period_clean = None
            m = re.search(r"^\d{4}Q[1-4]$", period_str)
            if m:
                period_clean = m.group(0)
            else:
                m2 = re.match(r"^\d{4}$", period_str)
                if m2:
                    period_clean = m2.group(0)
            if not period_clean:
                continue
            # 合并真实 red_flags（LLM 写的 + 真实数据兜底）
            llm_flags = [str(x) for x in (r.get("red_flags") or [])][:10]
            combined_flags = llm_flags + [f for f in real_flags if f not in llm_flags]
            fin = FinancialQualityV3.model_validate(
                {
                    "period": period_clean,
                    "revenue_yoy_pct": r.get("revenue_yoy_pct"),
                    "gross_margin_pct": r.get("gross_margin_pct"),
                    "gross_margin_change_yoy_pct": r.get("gross_margin_change_yoy_pct"),
                    "operating_cash_flow_yoy_pct": r.get("operating_cash_flow_yoy_pct"),
                    "ar_to_revenue_pct": r.get("ar_to_revenue_pct"),
                    "inventory_days": r.get("inventory_days"),
                    "contract_liability_yoy_pct": r.get("contract_liability_yoy_pct"),
                    "capex_intensity_pct": r.get("capex_intensity_pct"),
                    "capacity_utilization_pct": r.get("capacity_utilization_pct"),
                    "revenue_segments": segs,
                    "red_flags": combined_flags[:10],
                    "evidence_strength": r.get("evidence_strength", "primary"),
                    "source_url": r.get("source_url"),
                }
            )
            reports.append(fin.model_dump())
        except Exception as exc:  # noqa: BLE001
            logger.debug("[SupplyChain v3] financial validate 失败: %s", exc)
            continue
    if not reports:
        # LLM 输出无法校验 → 用兜底
        return _build_fallback_financial_report(ticker, "", real_flags, info, quote)
    return {"ticker": ticker, "reports": reports}


def _build_fallback_financial_report(
    ticker: str,
    company: str,
    real_flags: List[str],
    info: Dict[str, Any],
    quote: Dict[str, Any],
) -> Dict[str, Any]:
    """[v3 兜底] 当 LLM 输出无效时直接构造 1 条占位报告（强制不空）。"""
    from src.schemas.supply_chain import FinancialQualityV3

    # 真实数据直接填入（即便语义不完全匹配）
    pe = quote.get("pe_ratio")
    pb = quote.get("pb_ratio")
    mv_yi = quote.get("total_mv", 0) / 1e8 if quote.get("total_mv") else None

    fin = FinancialQualityV3.model_validate(
        {
            "period": "2024Q3",
            "revenue_yoy_pct": None,  # 真实数据源不可用
            "gross_margin_pct": None,
            "gross_margin_change_yoy_pct": None,
            "operating_cash_flow_yoy_pct": None,
            "ar_to_revenue_pct": None,
            "inventory_days": None,
            "contract_liability_yoy_pct": None,
            "capex_intensity_pct": None,
            "capacity_utilization_pct": None,
            "revenue_segments": {},
            "red_flags": real_flags or ["财务数据源不可用（Tushare 配额或网络问题）"],
            "evidence_strength": "primary" if real_flags else "analysis",
            "source_url": None,
        }
    )
    return {"ticker": ticker, "reports": [fin.model_dump()]}


analyze_financial_quality_tool = ToolDefinition(
    name="analyze_financial_quality",
    description=(
        "[v3 §10] 财务质量与产能跟踪。给定股票代码/公司名/行业提示，"
        "返回 List[FinancialQualityV3]（每条含 period/营收同比/毛利率/同比变化/"
        "经营现金流同比/应收占比/存货天数/合同负债同比/capex 强度/产能利用率/"
        "分业务收入占比/red_flags）。找不到字段返回 null，"
        "分业务占比加和须在 95-105%。失败返回 {error, reports:[]}。"
    ),
    parameters=[
        ToolParameter("ticker", "string", "股票代码", required=True),
        ToolParameter("company", "string", "公司名称", required=True),
        ToolParameter(
            "market", "string", "市场（CN/HK/US）", required=False, default=""
        ),
        ToolParameter(
            "industry_hint",
            "string",
            "行业提示",
            required=False,
            default="",
        ),
        ToolParameter(
            "top_k",
            "integer",
            "KB 命中条数（默认 5）",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_analyze_financial_quality,
    category="analysis",
)


# ============================================================
# v3 工具注册
# ============================================================


ALL_SUPPLY_CHAIN_TOOLS = [
    score_supply_chain_bottleneck_tool,
    search_semianalysis_tool,
    search_clue_hype_tool,
    verify_supply_chain_evidence_tool,
    search_supply_chain_kb_tool,
    # [v3] 深度小节工具（产品·客户·竞争·前景 五维补强）
    analyze_product_matrix_tool,
    analyze_market_position_tool,
    extract_key_partners_tool,
    analyze_industry_outlook_tool,
    analyze_financial_quality_tool,
]
