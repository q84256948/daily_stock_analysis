# -*- coding: utf-8 -*-
"""
Macro and Geopolitics Scoring (Liquidity=rule, China-US chain=LLM).

This dimension evaluates:
1. Domestic monetary policy and liquidity
2. Sector-specific policy support
3. US-China trade tensions impact
4. Regulatory environment changes
"""

from typing import Optional, Dict, Any

DEFAULT_NEUTRAL_SCORE = 50.0


def score_macro(
    monetary_policy: Optional[str] = None,
    liquidity_indicator: Optional[str] = None,
    sector_policy: Optional[str] = None,
    us_china_impact: Optional[str] = None,
    regulatory_risk: Optional[str] = None,
    evidence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score macro and geopolitics dimension.

    Args:
        monetary_policy: accommodative/neutral/tight
        liquidity_indicator: abundant/moderate/ scarce
        sector_policy: supportive/neutral/restrictive
        us_china_impact: minimal/limited/significant/severe
        regulatory_risk: low/medium/high
        evidence: Additional evidence summary

    Returns:
        Dict with score, indicators, and details
    """
    indicators = []
    total_score = 0.0
    total_weight = 0.0

    if monetary_policy:
        mp_score = _score_monetary_policy(monetary_policy)
        indicators.append(
            {
                "name": "货币政策",
                "score": mp_score,
                "weight": 0.25,
                "basis": "rule",
                "summary": f"货币政策立场:{monetary_policy}",
            }
        )
        total_score += mp_score * 0.25
        total_weight += 0.25

    if liquidity_indicator:
        liquidity_score = _score_liquidity(liquidity_indicator)
        indicators.append(
            {
                "name": "流动性",
                "score": liquidity_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"市场流动性:{liquidity_indicator}",
            }
        )
        total_score += liquidity_score * 0.20
        total_weight += 0.20

    if sector_policy:
        policy_score = _score_sector_policy(sector_policy)
        indicators.append(
            {
                "name": "行业政策",
                "score": policy_score,
                "weight": 0.25,
                "basis": "rule",
                "summary": f"行业政策:{sector_policy}",
            }
        )
        total_score += policy_score * 0.25
        total_weight += 0.25

    if us_china_impact:
        impact_score = _score_us_china_impact(us_china_impact)
        indicators.append(
            {
                "name": "中美影响",
                "score": impact_score,
                "weight": 0.30,
                "basis": "llm",
                "summary": f"中美关系影响:{us_china_impact}",
            }
        )
        total_score += impact_score * 0.30
        total_weight += 0.30

    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = DEFAULT_NEUTRAL_SCORE
        indicators.append(
            {
                "name": "宏观与地缘",
                "score": DEFAULT_NEUTRAL_SCORE,
                "weight": 1.0,
                "basis": "rule",
                "summary": "数据缺失，使用中性分",
            }
        )

    return {
        "dimension": "宏观与地缘",
        "score": final_score,
        "weight": 0.10,
        "indicators": indicators,
        "evidence": evidence,
    }


def _score_monetary_policy(policy: str) -> float:
    """Score monetary policy stance."""
    policy_map = {
        "accommodative": 80,
        "neutral": 50,
        "tight": 30,
    }
    return float(policy_map.get(policy.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_liquidity(liquidity: str) -> float:
    """Score liquidity indicator."""
    liquidity_map = {
        "abundant": 80,
        "moderate": 55,
        "scarce": 30,
    }
    return float(liquidity_map.get(liquidity.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_sector_policy(policy: str) -> float:
    """Score sector-specific policy."""
    policy_map = {
        "supportive": 85,
        "neutral": 50,
        "restrictive": 25,
    }
    return float(policy_map.get(policy.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_us_china_impact(impact: str) -> float:
    """Score US-China trade tensions impact."""
    impact_map = {
        "minimal": 90,
        "limited": 70,
        "significant": 45,
        "severe": 20,
    }
    return float(impact_map.get(impact.lower(), DEFAULT_NEUTRAL_SCORE))
