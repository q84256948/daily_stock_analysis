# -*- coding: utf-8 -*-
"""
Fundamentals and Value Scoring (Valuation=rule, Moat=LLM).

This dimension evaluates:
1. Valuation (PE, PB, PS percentiles)
2. Profitability (ROE, ROA, gross margin)
3. Growth (revenue/earnings growth rate)
4. Moat and competitive position
"""

from typing import Optional, Dict, Any

DEFAULT_NEUTRAL_SCORE = 50.0


def score_fundamental(
    pe_percentile: Optional[float] = None,
    pb_percentile: Optional[float] = None,
    roe: Optional[float] = None,
    revenue_growth: Optional[float] = None,
    earnings_growth: Optional[float] = None,
    gross_margin: Optional[float] = None,
    moat_assessment: Optional[str] = None,
    evidence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score fundamentals and value dimension.

    Args:
        pe_percentile: PE percentile (0-100), lower = cheaper
        pb_percentile: PB percentile (0-100), lower = cheaper
        roe: Return on equity (%), higher is better
        revenue_growth: Revenue growth rate (%), higher is better
        earnings_growth: Earnings growth rate (%), higher is better
        gross_margin: Gross margin (%), higher is better
        moat_assessment: LLM assessment of competitive moat
        evidence: LLM-provided evidence summary

    Returns:
        Dict with score, indicators, and details
    """
    indicators = []
    total_score = 0.0
    total_weight = 0.0

    if pe_percentile is not None and pb_percentile is not None:
        valuation_score = _score_valuation(pe_percentile, pb_percentile)
        indicators.append(
            {
                "name": "估值分位",
                "score": valuation_score,
                "weight": 0.30,
                "basis": "rule",
                "summary": f"PE分位{pe_percentile:.0f}%, PB分位{pb_percentile:.0f}%",
            }
        )
        total_score += valuation_score * 0.30
        total_weight += 0.30

    if roe is not None:
        roe_score = _score_roe(roe)
        indicators.append(
            {
                "name": "ROE",
                "score": roe_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"ROE={roe:.1f}%",
            }
        )
        total_score += roe_score * 0.20
        total_weight += 0.20

    if revenue_growth is not None or earnings_growth is not None:
        growth = revenue_growth or earnings_growth or 0
        growth_score = _score_growth(growth)
        rev_str = f"{revenue_growth:.1f}%" if revenue_growth is not None else "N/A"
        earn_str = f"{earnings_growth:.1f}%" if earnings_growth is not None else "N/A"
        indicators.append(
            {
                "name": "成长性",
                "score": growth_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"营收增长{rev_str}, 利润增长{earn_str}",
            }
        )
        total_score += growth_score * 0.20
        total_weight += 0.20

    if gross_margin is not None:
        margin_score = _score_gross_margin(gross_margin)
        indicators.append(
            {
                "name": "毛利率",
                "score": margin_score,
                "weight": 0.15,
                "basis": "rule",
                "summary": f"毛利率={gross_margin:.1f}%",
            }
        )
        total_score += margin_score * 0.15
        total_weight += 0.15

    if moat_assessment:
        moat_score = _score_moat_llm(moat_assessment)
        indicators.append(
            {
                "name": "护城河评估",
                "score": moat_score,
                "weight": 0.15,
                "basis": "llm",
                "summary": moat_assessment[:50],
            }
        )
        total_score += moat_score * 0.15
        total_weight += 0.15

    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = DEFAULT_NEUTRAL_SCORE
        indicators.append(
            {
                "name": "基本面与价值",
                "score": DEFAULT_NEUTRAL_SCORE,
                "weight": 1.0,
                "basis": "rule",
                "summary": "数据缺失，使用中性分",
            }
        )

    return {
        "dimension": "基本面与价值",
        "score": final_score,
        "weight": 0.25,
        "indicators": indicators,
        "evidence": evidence,
    }


def _score_valuation(pe_pct: float, pb_pct: float) -> float:
    """Score valuation. Lower percentile = higher score."""
    avg_pct = (pe_pct + pb_pct) / 2

    if avg_pct < 20:
        return 95
    elif avg_pct < 40:
        return 80
    elif avg_pct < 60:
        return 60
    elif avg_pct < 80:
        return 40
    else:
        return 20


def _score_roe(roe: float) -> float:
    """Score ROE. Industry-dependent, general thresholds."""
    if roe > 25:
        return 95
    elif roe > 18:
        return 80
    elif roe > 12:
        return 60
    elif roe > 6:
        return 40
    else:
        return 20


def _score_growth(growth: float) -> float:
    """Score growth rate."""
    if growth > 30:
        return 95
    elif growth > 15:
        return 80
    elif growth > 5:
        return 60
    elif growth > 0:
        return 40
    elif growth > -10:
        return 25
    else:
        return 10


def _score_gross_margin(margin: float) -> float:
    """Score gross margin."""
    if margin > 60:
        return 95
    elif margin > 45:
        return 80
    elif margin > 30:
        return 60
    elif margin > 15:
        return 40
    else:
        return 20


def _score_moat_llm(assessment: str) -> float:
    """Score moat based on LLM assessment text."""
    positive = ["strong", "wide", "durable", "核心", "强大", "深厚", "稀缺"]
    negative = ["weak", "narrow", "none", "薄弱", "脆弱", "无"]

    assessment_lower = assessment.lower()

    if any(kw in assessment_lower for kw in positive):
        return 85
    elif any(kw in assessment_lower for kw in negative):
        return 35
    else:
        return 50
