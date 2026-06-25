# -*- coding: utf-8 -*-
"""
Technical Analysis Scoring (Rule-based, long-term focus).

This dimension evaluates:
1. Long-term trend (MA alignment)
2. Price momentum (relative to MA)
3. Volume trend
4. Key support/resistance levels
"""

from typing import Optional, Dict, Any

DEFAULT_NEUTRAL_SCORE = 50.0


def score_technical(
    ma_alignment: Optional[str] = None,
    price_vs_ma250: Optional[float] = None,
    volume_trend: Optional[str] = None,
    distance_from_high: Optional[float] = None,
    trend_duration_months: Optional[int] = None,
    evidence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score technical analysis dimension.

    Args:
        ma_alignment: bullish/neutral/bearish (MA5/10/20/60/120/250 alignment)
        price_vs_ma250: Price vs 250-day MA (%), positive = above MA
        volume_trend: increasing/stable/decreasing
        distance_from_high: Distance from 52-week high (%), lower = closer to high
        trend_duration_months: Duration of current trend in months
        evidence: Additional evidence summary

    Returns:
        Dict with score, indicators, and details
    """
    indicators = []
    total_score = 0.0
    total_weight = 0.0

    if ma_alignment:
        ma_score = _score_ma_alignment(ma_alignment)
        indicators.append(
            {
                "name": "均线排列",
                "score": ma_score,
                "weight": 0.35,
                "basis": "rule",
                "summary": f"均线排列:{ma_alignment}",
            }
        )
        total_score += ma_score * 0.35
        total_weight += 0.35

    if price_vs_ma250 is not None:
        ma_distance_score = _score_price_vs_ma(price_vs_ma250)
        indicators.append(
            {
                "name": "价格相对年线",
                "score": ma_distance_score,
                "weight": 0.25,
                "basis": "rule",
                "summary": f"价格相对年线{price_vs_ma250:+.1f}%",
            }
        )
        total_score += ma_distance_score * 0.25
        total_weight += 0.25

    if volume_trend:
        volume_score = _score_volume_trend(volume_trend)
        indicators.append(
            {
                "name": "成交量趋势",
                "score": volume_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"量能趋势:{volume_trend}",
            }
        )
        total_score += volume_score * 0.20
        total_weight += 0.20

    if distance_from_high is not None:
        high_score = _score_distance_from_high(distance_from_high)
        indicators.append(
            {
                "name": "距高点距离",
                "score": high_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"距52周高点{distance_from_high:.1f}%",
            }
        )
        total_score += high_score * 0.20
        total_weight += 0.20

    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = DEFAULT_NEUTRAL_SCORE
        indicators.append(
            {
                "name": "技术面",
                "score": DEFAULT_NEUTRAL_SCORE,
                "weight": 1.0,
                "basis": "rule",
                "summary": "数据缺失，使用中性分",
            }
        )

    return {
        "dimension": "技术面",
        "score": final_score,
        "weight": 0.10,
        "indicators": indicators,
        "evidence": evidence,
    }


def _score_ma_alignment(alignment: str) -> float:
    """Score MA alignment."""
    alignment_map = {
        "bullish": 85,
        "neutral": 50,
        "bearish": 25,
    }
    return float(alignment_map.get(alignment.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_price_vs_ma(distance: float) -> float:
    """Score price vs 250-day MA. Positive = above MA."""
    if distance > 30:
        return 90
    elif distance > 15:
        return 75
    elif distance > 5:
        return 65
    elif distance > -5:
        return 50
    elif distance > -15:
        return 35
    elif distance > -30:
        return 25
    else:
        return 15


def _score_volume_trend(trend: str) -> float:
    """Score volume trend."""
    trend_map = {
        "increasing": 70,
        "stable": 50,
        "decreasing": 35,
    }
    return float(trend_map.get(trend.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_distance_from_high(distance: float) -> float:
    """Score distance from 52-week high. Lower = closer to high."""
    if distance < 5:
        return 90
    elif distance < 15:
        return 75
    elif distance < 25:
        return 60
    elif distance < 40:
        return 45
    elif distance < 55:
        return 30
    else:
        return 20
