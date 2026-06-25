# -*- coding: utf-8 -*-
"""
Sentiment and Cognitive Difference Scoring (Research reports=rule, Social=LLM).

This dimension evaluates:
1. Analyst recommendations and target prices
2. Sentiment from news and social media
3. Market consensus vs our view (cognitive difference)
4. Recent catalysts and risks
"""

from typing import Optional, Dict, Any, List

DEFAULT_NEUTRAL_SCORE = 50.0


def score_sentiment(
    analyst_consensus: Optional[str] = None,
    target_price_upside: Optional[float] = None,
    news_sentiment: Optional[str] = None,
    short_interest_ratio: Optional[float] = None,
    cognitive_difference: Optional[str] = None,
    recent_catalysts: Optional[List[str]] = None,
    evidence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score sentiment and cognitive difference dimension.

    Args:
        analyst_consensus: buy/outperform/neutral/underperform/sell
        target_price_upside: Target price upside vs current (%), positive = buy
        news_sentiment: positive/neutral/negative
        short_interest_ratio: Short interest as % of float
        cognitive_difference: market_underestimating/market_fair/market_overestimating
        recent_catalysts: List of recent positive catalysts
        evidence: Additional evidence summary

    Returns:
        Dict with score, indicators, and details
    """
    indicators = []
    total_score = 0.0
    total_weight = 0.0

    if analyst_consensus and target_price_upside is not None:
        analyst_score = _score_analyst(analyst_consensus, target_price_upside)
        indicators.append(
            {
                "name": "分析师共识",
                "score": analyst_score,
                "weight": 0.35,
                "basis": "rule",
                "summary": f"评级:{analyst_consensus}, 目标价空间{target_price_upside:+.1f}%",
            }
        )
        total_score += analyst_score * 0.35
        total_weight += 0.35

    if news_sentiment:
        news_score = _score_news_sentiment(news_sentiment)
        indicators.append(
            {
                "name": "新闻情绪",
                "score": news_score,
                "weight": 0.20,
                "basis": "rule",
                "summary": f"新闻情绪:{news_sentiment}",
            }
        )
        total_score += news_score * 0.20
        total_weight += 0.20

    if short_interest_ratio is not None:
        short_score = _score_short_interest(short_interest_ratio)
        indicators.append(
            {
                "name": "做空比例",
                "score": short_score,
                "weight": 0.15,
                "basis": "rule",
                "summary": f"做空比例{short_interest_ratio:.2f}%",
            }
        )
        total_score += short_score * 0.15
        total_weight += 0.15

    if cognitive_difference:
        cognitive_score = _score_cognitive_difference(cognitive_difference)
        indicators.append(
            {
                "name": "认知差",
                "score": cognitive_score,
                "weight": 0.30,
                "basis": "llm",
                "summary": f"市场认知:{cognitive_difference}",
            }
        )
        total_score += cognitive_score * 0.30
        total_weight += 0.30

    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = DEFAULT_NEUTRAL_SCORE
        indicators.append(
            {
                "name": "情绪与认知差",
                "score": DEFAULT_NEUTRAL_SCORE,
                "weight": 1.0,
                "basis": "rule",
                "summary": "数据缺失，使用中性分",
            }
        )

    return {
        "dimension": "情绪与认知差",
        "score": final_score,
        "weight": 0.15,
        "indicators": indicators,
        "evidence": evidence,
    }


def _score_analyst(consensus: str, upside: float) -> float:
    """Score analyst consensus and target price upside."""
    consensus_score_map = {
        "buy": 90,
        "outperform": 80,
        "neutral": 50,
        "underperform": 30,
        "sell": 15,
    }

    base_score = consensus_score_map.get(consensus.lower(), 50)

    if upside > 50:
        return min(100, base_score + 10)
    elif upside > 30:
        return base_score
    elif upside > 10:
        return max(30, base_score - 10)
    elif upside > 0:
        return max(20, base_score - 20)
    else:
        return max(10, base_score - 30)


def _score_news_sentiment(sentiment: str) -> float:
    """Score news sentiment."""
    sentiment_map = {
        "positive": 75,
        "neutral": 50,
        "negative": 30,
    }
    return float(sentiment_map.get(sentiment.lower(), DEFAULT_NEUTRAL_SCORE))


def _score_short_interest(ratio: float) -> float:
    """Score short interest. High short interest = potential short squeeze."""
    if ratio < 3:
        return 70
    elif ratio < 8:
        return 55
    elif ratio < 15:
        return 40
    else:
        return 25


def _score_cognitive_difference(difference: str) -> float:
    """Score cognitive difference. Market underestimating = higher score."""
    difference_map = {
        "market_underestimating": 85,
        "market_fair": 50,
        "market_overestimating": 25,
    }
    return float(difference_map.get(difference.lower(), DEFAULT_NEUTRAL_SCORE))
