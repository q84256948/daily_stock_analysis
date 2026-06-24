# -*- coding: utf-8 -*-
"""
Research Framework Integration Helper.

提供将长线投研框架集成到现有分析流水线的工具函数。
"""

import logging
from typing import Dict, Any, Optional, List

from src.analyzer import AnalysisResult

logger = logging.getLogger(__name__)


def integrate_research_framework(
    result: AnalysisResult,
    context: Dict[str, Any],
    enable_research_framework: bool = True,
) -> AnalysisResult:
    """
    将长线投研框架集成到分析结果中。

    此函数作为后处理步骤，在主分析完成后调用。
    它从分析结果和上下文中提取数据，调用 ResearchScoringService，
    并将结果注入到 AnalysisResult 的五段式长线投研字段。

    Args:
        result: 主分析产生的 AnalysisResult
        context: 分析上下文（包含技术指标、基本面数据等）
        enable_research_framework: 是否启用长线投研框架

    Returns:
        带有五段式长线投研框架数据的 AnalysisResult
    """
    if not enable_research_framework:
        logger.debug("Research framework disabled, skipping")
        return result

    try:
        from src.services.research_scoring_service import ResearchScoringService

        raw_data = _extract_raw_data_from_context(result, context)

        scoring_service = ResearchScoringService()
        scoring_result = scoring_service.process(
            stock_code=result.code,
            stock_name=result.name,
            market=_infer_market(result.code),
            raw_data=raw_data,
            market_implied_p=_estimate_market_implied_p(result),
        )

        result.research_framework = scoring_result.get("framework_score")
        result.bayesian_framework = scoring_result.get("bayesian_result")
        result.supply_chain = _build_supply_chain_from_analysis(
            result, context, raw_data
        )
        result.value_scenarios = _build_value_scenarios_from_analysis(
            result, context, scoring_result
        )
        result.investment_conclusion = _build_investment_conclusion(
            result,
            scoring_result.get("bayesian_result"),
            scoring_result.get("framework_score"),
        )

        logger.info(
            f"[ResearchFramework] Stock {result.code} processed: "
            f"dimension_total={scoring_result.get('framework_score', {}).get('dimension_total', 'N/A')}, "
            f"edge={scoring_result.get('bayesian_result', {}).get('edge', 'N/A')}"
        )

    except ImportError as e:
        logger.warning(f"[ResearchFramework] Module not available: {e}")
    except Exception as e:
        logger.warning(f"[ResearchFramework] Integration failed: {e}")

    return result


def _build_supply_chain_from_analysis(
    result: AnalysisResult,
    context: Dict[str, Any],
    raw_data: Dict[str, Any],
) -> Dict[str, Any]:
    """从分析结果构建产业链解读数据

    使用 SupplyChainDataService 获取数据：
    - 知识库: 常见股票的供应链信息
    - LLM推断: 从基本面分析文本中提取
    - Serenity: 瓶颈评分卡 (可选，需 enable_serenity=True)
    """
    try:
        from src.services.supply_chain_data_service import SupplyChainDataService

        market = _infer_market(result.code)
        fundamental_text = result.fundamental_analysis or ""

        sc_service = SupplyChainDataService()
        sc_data = sc_service.fetch_all(
            stock_code=result.code,
            stock_name=result.name,
            fundamental_analysis=fundamental_text,
            market=market,
            enable_serenity=False,
        )

        supply_chain_data = {
            "data_sources": sc_data.get("data_sources", []),
            "company_position": sc_data.get("company_position")
            or _extract_company_position(result),
            "upstream": sc_data.get("upstream")
            or _extract_upstream_from_analysis(result),
            "downstream": sc_data.get("downstream")
            or _extract_downstream_from_analysis(result),
            "chokepoints": sc_data.get("chokepoints")
            or _extract_chokepoints(result, raw_data),
            "us_china_chain": sc_data.get("us_china_chain")
            or _extract_us_china_chain(result),
            "industry_drivers": sc_data.get("industry_drivers")
            or _extract_industry_drivers(result, context),
            "chain_map": _build_chain_map_from_context(context),
            "serenity_score": sc_data.get("serenity_score"),
            "serenity_verdict": sc_data.get("serenity_verdict"),
        }

        logger.info(
            f"[ResearchFramework] Supply chain for {result.code}: "
            f"sources={sc_data.get('data_sources', [])}, "
            f"upstream={len(supply_chain_data['upstream'])}, "
            f"downstream={len(supply_chain_data['downstream'])}"
        )

        return supply_chain_data

    except ImportError as e:
        logger.warning(f"[ResearchFramework] SupplyChainDataService not available: {e}")
    except Exception as e:
        logger.warning(f"[ResearchFramework] Supply chain fetch failed: {e}")

    supply_chain_data = {
        "company_position": _extract_company_position(result),
        "upstream": _extract_upstream_from_analysis(result),
        "downstream": _extract_downstream_from_analysis(result),
        "chokepoints": _extract_chokepoints(result, raw_data),
        "us_china_chain": _extract_us_china_chain(result),
        "industry_drivers": _extract_industry_drivers(result, context),
        "chain_map": _build_chain_map_from_context(context),
    }

    if result.fundamental_analysis and len(result.fundamental_analysis) > 50:
        has_placeholders = _has_supply_chain_placeholders(supply_chain_data)
        if has_placeholders:
            llm_enriched = _enrich_supply_chain_with_llm(
                result.code, result.name, result.fundamental_analysis, supply_chain_data
            )
            if llm_enriched:
                supply_chain_data = llm_enriched

    return supply_chain_data


def _has_supply_chain_placeholders(supply_chain_data: Dict[str, Any]) -> bool:
    """检查产业链数据是否包含占位符值"""
    placeholder_keywords = ["待分析", "待详细", "待评估", "待挖掘"]

    if supply_chain_data.get("company_position") in placeholder_keywords:
        return True

    for key in ["upstream", "downstream"]:
        values = supply_chain_data.get(key, [])
        if isinstance(values, list):
            for v in values:
                if any(pk in str(v) for pk in placeholder_keywords):
                    return True

    chokepoints = supply_chain_data.get("chokepoints", [])
    for cp in chokepoints:
        if isinstance(cp, dict):
            desc = cp.get("description", "")
            if any(pk in str(desc) for pk in placeholder_keywords):
                return True

    us_china = supply_chain_data.get("us_china_chain", {})
    for v in us_china.values():
        if any(pk in str(v) for pk in placeholder_keywords):
            return True

    drivers = supply_chain_data.get("industry_drivers", [])
    for d in drivers:
        if any(pk in str(d) for pk in placeholder_keywords):
            return True

    return False


def _enrich_supply_chain_with_llm(
    stock_code: str,
    stock_name: str,
    fundamental_text: str,
    supply_chain_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """使用LLM从基本面分析文本中提取产业链信息来丰富数据"""
    try:
        from src.services.research_scoring_service import ResearchScoringService

        scoring_service = ResearchScoringService()
        llm_result = scoring_service.extract_supply_chain_from_llm(
            stock_code, stock_name, fundamental_text
        )

        if not llm_result:
            return None

        enriched = supply_chain_data.copy()

        if llm_result.get("chain_position"):
            enriched["company_position"] = llm_result.get("chain_position")

        if llm_result.get("upstream"):
            upstream_list = llm_result.get("upstream", [])
            if isinstance(upstream_list, list) and upstream_list:
                current_upstream = enriched.get("upstream", [])
                if not any(
                    pk in str(v)
                    for v in current_upstream
                    for pk in ["待分析", "待详细"]
                ):
                    pass
                else:
                    enriched["upstream"] = upstream_list[:3]

        if llm_result.get("downstream"):
            downstream_list = llm_result.get("downstream", [])
            if isinstance(downstream_list, list) and downstream_list:
                current_downstream = enriched.get("downstream", [])
                if not any(
                    pk in str(v)
                    for v in current_downstream
                    for pk in ["待分析", "待详细"]
                ):
                    pass
                else:
                    enriched["downstream"] = downstream_list[:3]

        if llm_result.get("chokepoint_type"):
            chokepoints = enriched.get("chokepoints", [])
            has_placeholder = False
            for cp in chokepoints:
                if isinstance(cp, dict) and any(
                    pk in str(cp.get("description", "")) for pk in ["待详细", "unknown"]
                ):
                    has_placeholder = True
                    break
            if has_placeholder:
                enriched["chokepoints"] = [
                    {
                        "type": llm_result.get("chokepoint_type", "tech"),
                        "description": llm_result.get(
                            "chokepoint_desc", "基于LLM分析提取的瓶颈点"
                        ),
                        "confidence": "medium",
                    }
                ]

        if llm_result.get("us_business_ratio") or llm_result.get("sanction_risk"):
            current_us = enriched.get("us_china_chain", {})
            if any(
                pk in str(v) for v in current_us.values() for pk in ["待分析", "待评估"]
            ):
                enriched["us_china_chain"] = {
                    "role": llm_result.get("us_business_ratio", "待分析"),
                    "substitution_progress": llm_result.get(
                        "substitution_progress", "待分析"
                    ),
                    "sanction_risk": llm_result.get("sanction_risk", "待观察"),
                    "dual_chain_impact": llm_result.get("dual_chain_impact", "待分析"),
                }

        if llm_result.get("industry_drivers"):
            drivers = llm_result.get("industry_drivers", [])
            if isinstance(drivers, list) and drivers:
                current_drivers = enriched.get("industry_drivers", [])
                if any(
                    pk in str(d) for d in current_drivers for pk in ["待详细", "待分析"]
                ):
                    enriched["industry_drivers"] = drivers[:3]

        logger.info(f"[ResearchFramework] LLM enrichment applied for {stock_code}")
        return enriched

    except Exception as e:
        logger.warning(f"[ResearchFramework] LLM enrichment failed: {e}")
        return None


def _build_value_scenarios_from_analysis(
    result: AnalysisResult,
    context: Dict[str, Any],
    scoring_result: Dict[str, Any],
) -> Dict[str, Any]:
    """从分析结果构建长期价值与情景数据"""
    fundamental = context.get("fundamental", {})
    current_price = context.get("current_price") or fundamental.get("current_price")

    scenarios = []
    if current_price:
        upside = fundamental.get("upside_potential", 30)
        scenarios = [
            {
                "type": "optimistic",
                "probability": 0.25,
                "value_anchor": round(current_price * (1 + upside / 100 * 1.5), 2),
                "description": "乐观情景：产业高速增长，产能利用率提升",
            },
            {
                "type": "neutral",
                "probability": 0.50,
                "value_anchor": round(current_price * (1 + upside / 100), 2),
                "description": "中性情景：稳定增长，份额保持",
            },
            {
                "type": "pessimistic",
                "probability": 0.25,
                "value_anchor": round(current_price * (1 - upside / 100 * 0.5), 2),
                "description": "悲观情景：竞争加剧，盈利承压",
            },
        ]

    horizons = {}
    if current_price:
        upside = fundamental.get("upside_potential", 30)
        range_factor = 0.15
        for years, multiplier in [(1, 1), (3, 1.5), (5, 2)]:
            base_value = current_price * (1 + upside / 100 * multiplier)
            low = round(base_value * (1 - range_factor), 2)
            high = round(base_value * (1 + range_factor), 2)
            horizons[f"horizon_{years}y"] = f"{low}~{high} 元"

    value_scenarios_data = {
        "industry_space": _extract_industry_space(result, context),
        "competitive_evolution": _extract_competitive_evolution(result),
        "scenarios": scenarios,
        "horizons": horizons,
        "catalysts": _extract_catalysts(result),
        "risks": _extract_risks(result),
    }
    return value_scenarios_data


def _extract_company_position(result: AnalysisResult) -> str:
    """提取公司在产业链中的定位"""
    if result.fundamental_analysis:
        analysis = result.fundamental_analysis[:200]
        return f"基于基本面分析：{analysis}"
    return "产业链定位待详细分析"


def _extract_upstream_from_analysis(result: AnalysisResult) -> List[str]:
    """提取上游供应商信息"""
    if not result.fundamental_analysis:
        return []

    upstream_keywords = ["上游", "供应商", "原材料", "采购"]
    upstream = []
    text = result.fundamental_analysis
    for kw in upstream_keywords:
        if kw in text:
            idx = text.find(kw)
            start = max(0, idx - 20)
            end = min(len(text), idx + 50)
            snippet = text[start:end]
            upstream.append(snippet.strip())
            break
    return upstream if upstream else ["上游信息待详细分析"]


def _extract_downstream_from_analysis(result: AnalysisResult) -> List[str]:
    """提取下游客户信息"""
    if not result.fundamental_analysis:
        return []

    downstream_keywords = ["下游", "客户", "应用", "终端"]
    downstream = []
    text = result.fundamental_analysis
    for kw in downstream_keywords:
        if kw in text:
            idx = text.find(kw)
            start = max(0, idx - 20)
            end = min(len(text), idx + 50)
            snippet = text[start:end]
            downstream.append(snippet.strip())
            break
    return downstream if downstream else ["下游信息待详细分析"]


def _extract_chokepoints(
    result: AnalysisResult, raw_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """提取瓶颈点信息"""
    chokepoints = []

    if raw_data.get("chokepoint_type"):
        chokepoints.append(
            {
                "type": raw_data.get("chokepoint_type", "unknown"),
                "description": raw_data.get(
                    "supply_chain_evidence", "基于分析提取的瓶颈点"
                ),
                "confidence": "medium",
            }
        )

    moat = raw_data.get("moat_assessment", "")
    if "strong" in moat.lower() or "强" in moat:
        chokepoints.append(
            {
                "type": "patent",
                "description": "护城河较强，专利壁垒明显",
                "confidence": "medium",
            }
        )

    return (
        chokepoints
        if chokepoints
        else [
            {
                "type": "unknown",
                "description": "瓶颈点待详细产业链分析",
                "confidence": "low",
            }
        ]
    )


def _extract_us_china_chain(result: AnalysisResult) -> Dict[str, str]:
    """提取中美双链位置"""
    if result.fundamental_analysis:
        text = result.fundamental_analysis.lower()
        if any(kw in text for kw in ["国产", "替代", "自主"]):
            return {
                "role": "中国链",
                "substitution_progress": "国产替代进行中",
                "sanction_risk": "低",
                "dual_chain_impact": "受益",
            }
        if any(kw in text for kw in ["出口", "海外", "美国"]):
            return {
                "role": "双链节点",
                "substitution_progress": "国际化布局",
                "sanction_risk": "中",
                "dual_chain_impact": "中性",
            }

    return {
        "role": "待分析",
        "substitution_progress": "待分析",
        "sanction_risk": "待评估",
        "dual_chain_impact": "待评估",
    }


def _extract_industry_drivers(
    result: AnalysisResult, context: Dict[str, Any]
) -> List[str]:
    """提取产业驱动根因"""
    drivers = []

    if result.fundamental_analysis:
        text = result.fundamental_analysis
        driver_keywords = ["增长", "需求", "政策", "技术", "创新", "扩产"]
        for kw in driver_keywords:
            if kw in text:
                drivers.append(f"驱动因素：{kw}")

    trend = context.get("trend", {})
    if trend.get("trend_direction") == "up":
        drivers.append("趋势驱动：长期上升通道")

    return drivers if drivers else ["产业驱动因素待详细分析"]


def _build_chain_map_from_context(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从上下文构建供应链地图"""
    fundamental = context.get("fundamental", {})
    sector = fundamental.get("industry", "")

    return [
        {
            "level": "下游应用",
            "companies": [f"{sector}相关应用领域"] if sector else ["下游应用"],
            "concentration": None,
        },
        {
            "level": "中游制造",
            "companies": [],
            "concentration": None,
        },
        {
            "level": "上游组件",
            "companies": [],
            "concentration": None,
        },
    ]


def _extract_industry_space(result: AnalysisResult, context: Dict[str, Any]) -> str:
    """提取产业长期空间"""
    if result.fundamental_analysis:
        return result.fundamental_analysis[:200]
    return "产业空间待详细分析"


def _extract_competitive_evolution(result: AnalysisResult) -> str:
    """提取竞争格局演变"""
    if result.fundamental_analysis:
        return f"基于基本面分析，竞争格局分析：{result.fundamental_analysis[:150]}..."
    return "竞争格局演变待详细分析"


def _extract_catalysts(result: AnalysisResult) -> List[str]:
    """提取潜在催化事件"""
    catalysts = []

    if result.market_sentiment:
        catalysts.append("消息面：存在正面催化剂")

    if result.sentiment_score and result.sentiment_score >= 70:
        catalysts.append("情绪面：市场情绪偏乐观")

    return catalysts if catalysts else ["潜在催化事件待详细分析"]


def _extract_risks(result: AnalysisResult) -> List[str]:
    """提取主要风险"""
    risks = []

    if result.operation_advice == "观望":
        risks.append("操作建议观望，注意短期风险")

    if result.sentiment_score and result.sentiment_score < 50:
        risks.append("情绪评分偏低，市场信心不足")

    return risks if risks else ["风险因素待详细分析"]


def _extract_raw_data_from_context(
    result: AnalysisResult,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """从分析结果和上下文中提取评分所需的数据"""
    raw_data = {}

    if context.get("fundamental"):
        fund = context["fundamental"]
        raw_data["pe_percentile"] = fund.get("pe_percentile")
        raw_data["pb_percentile"] = fund.get("pb_percentile")
        raw_data["roe"] = fund.get("roe")
        raw_data["revenue_growth"] = fund.get("revenue_growth")
        raw_data["earnings_growth"] = fund.get("earnings_growth")
        raw_data["gross_margin"] = fund.get("gross_margin")

    if context.get("trend"):
        trend = context["trend"]
        raw_data["price_vs_ma250"] = trend.get("price_vs_ma250")
        raw_data["distance_from_high"] = trend.get("distance_from_high")
        ma_status = trend.get("ma_alignment", "").lower()
        if "多头" in ma_status or "bullish" in ma_status:
            raw_data["ma_alignment"] = "bullish"
        elif "空头" in ma_status or "bearish" in ma_status:
            raw_data["ma_alignment"] = "bearish"
        else:
            raw_data["ma_alignment"] = "neutral"

    if context.get("capital_flow"):
        cap = context["capital_flow"]
        raw_data["northbound_flow_20d"] = cap.get("northbound_flow_20d")
        raw_data["margin_balance_change"] = cap.get("margin_balance_change")
        raw_data["foreign_ratio"] = cap.get("foreign_ratio")

    if result.fundamental_analysis:
        raw_data["moat_assessment"] = _extract_moat_from_analysis(
            result.fundamental_analysis
        )
        raw_data["supply_chain_evidence"] = _extract_supply_chain_from_analysis(
            result.fundamental_analysis
        )

    if result.market_sentiment:
        raw_data["news_sentiment"] = _infer_sentiment(result.market_sentiment)

    sentiment = result.sentiment_score
    if sentiment is not None:
        if sentiment >= 70:
            raw_data["analyst_consensus"] = "buy"
            raw_data["target_price_upside"] = 20.0
        elif sentiment >= 60:
            raw_data["analyst_consensus"] = "outperform"
            raw_data["target_price_upside"] = 15.0
        elif sentiment >= 40:
            raw_data["analyst_consensus"] = "neutral"
            raw_data["target_price_upside"] = 5.0
        else:
            raw_data["analyst_consensus"] = "underperform"
            raw_data["target_price_upside"] = -10.0

    return raw_data


def _extract_moat_from_analysis(text: str) -> str:
    """从基本面分析文本中提取护城河评估"""
    moat_keywords = ["护城河", "壁垒", "专利", "技术", "品牌", "垄断", "稀缺", "独占"]
    text_lower = text.lower()

    strong_keywords = ["强护城河", "深厚", "强大", "核心", "不可替代", "wide moat"]
    weak_keywords = ["护城河弱", "竞争激烈", "壁垒低", "易被复制"]

    for kw in strong_keywords:
        if kw.lower() in text_lower:
            return "Strong moat, leading position in industry"
    for kw in weak_keywords:
        if kw.lower() in text_lower:
            return "Weak moat, facing competitive pressure"

    for kw in moat_keywords:
        if kw in text:
            return "Moderate moat based on patent/technology advantage"

    return "Moat assessment pending detailed analysis"


def _extract_supply_chain_from_analysis(text: str) -> str:
    """从基本面分析文本中提取产业链信息"""
    chain_keywords = ["上游", "下游", "供应链", "产业链", "供应商", "客户", "议价"]

    for kw in chain_keywords:
        if kw in text:
            idx = text.find(kw)
            start = max(0, idx - 50)
            end = min(len(text), idx + 100)
            return f"...{text[start:end]}..."

    return ""


def _infer_sentiment(text: str) -> str:
    """从市场情绪文本推断情绪分类"""
    text_lower = text.lower()

    positive_keywords = ["乐观", "积极", "向好", "看好", "乐观", "bullish", "positive"]
    negative_keywords = ["悲观", "消极", "悲观", "看空", "担忧", "bearish", "negative"]

    positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
    negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    return "neutral"


def _estimate_market_implied_p(result: AnalysisResult) -> float:
    """从分析结果估算市场隐含概率"""
    sentiment = result.sentiment_score if result.sentiment_score is not None else 50

    sentiment_p = sentiment / 100.0

    decision_type = getattr(result, "decision_type", "hold")
    if decision_type == "buy":
        return min(1.0, sentiment_p + 0.1)
    elif decision_type == "sell":
        return max(0.0, sentiment_p - 0.1)
    return sentiment_p


def _infer_market(stock_code: str) -> str:
    """从股票代码推断市场"""
    if not stock_code:
        return "cn"

    code_upper = stock_code.upper()

    if code_upper.startswith("HK"):
        return "hk"

    if ".HK" in code_upper:
        return "hk"

    if (
        code_upper.startswith("AAPL")
        or code_upper.startswith("GOOG")
        or code_upper.startswith("MSFT")
    ):
        return "us"

    if code_upper.startswith("00") and len(stock_code) <= 4:
        return "hk"

    if len(stock_code) == 5:
        return "hk"

    return "cn"


def _build_investment_conclusion(
    result: AnalysisResult,
    bayesian_result: Optional[Dict[str, Any]],
    framework_score: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """从贝叶斯结果构建投资结论"""
    if not bayesian_result:
        return {
            "action": "观察",
            "position": "观察",
            "rationale": "暂无长线投研数据",
        }

    edge = bayesian_result.get("edge", 0)
    prior_p = bayesian_result.get("prior_p", 0.5)
    posterior_p = bayesian_result.get("posterior_p", prior_p)
    position = bayesian_result.get("position_suggestion", "0-1%")

    if edge > 0.3:
        action = "加仓" if getattr(result, "decision_type", "") == "buy" else "建仓"
    elif edge > 0.1:
        action = "持有"
    elif edge < -0.1:
        action = "减仓" if edge < -0.3 else "观察"
    else:
        action = "观察"

    chain_summary = ""
    if framework_score:
        dimensions = framework_score.get("dimensions", [])
        for dim in dimensions:
            if dim.get("dimension") == "产业链定位":
                score = dim.get("score", 0)
                chain_summary = f"产业链定位评分 {score:.1f}"
                break

    return {
        "prior_p": prior_p,
        "market_implied_p": bayesian_result.get("market_implied_p"),
        "edge": edge,
        "posterior_p": posterior_p,
        "position": position,
        "action": action,
        "chain_position_summary": chain_summary,
        "stop_conditions": bayesian_result.get("stop_conditions"),
        "rationale": _generate_rationale(result, edge, posterior_p),
    }


def _generate_rationale(result: AnalysisResult, edge: float, posterior_p: float) -> str:
    """生成投资理由"""
    parts = []

    if result.analysis_summary:
        summary = result.analysis_summary[:100]
        parts.append(f"分析摘要: {summary}...")

    if edge > 0.2:
        parts.append(f"认知差显著 ({edge * 100:.1f}%)，市场可能低估了公司价值")
    elif edge > 0.1:
        parts.append(f"存在一定认知差 ({edge * 100:.1f}%)")
    elif edge < -0.1:
        parts.append(f"认知差为负 ({edge * 100:.1f}%)，市场可能高估")

    if posterior_p > 0.7:
        parts.append("长期胜率较高 (>70%)")
    elif posterior_p > 0.5:
        parts.append("长期胜率中等")

    return "；".join(parts) if parts else "综合分析后建议观察为主"
