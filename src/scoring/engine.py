# -*- coding: utf-8 -*-
"""
Six-dimension Scoring Engine - Pure functions, no external dependencies.

Responsibilities:
1. Weight validation: Ensure sum(weights) == 1.0
2. Null handling: Missing data defaults to neutral score 50
3. Weighted aggregation: Six dimensions → Total score
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

DEFAULT_NEUTRAL_SCORE = 50.0
DEFAULT_WEIGHT = 1.0 / 6.0
WEIGHT_EPSILON = 1e-6

DEFAULT_DIMENSION_WEIGHTS = {
    "产业链定位": 0.25,
    "基本面与价值": 0.25,
    "资金面": 0.15,
    "技术面": 0.10,
    "情绪与认知差": 0.15,
    "宏观与地缘": 0.10,
}


@dataclass(frozen=True)
class IndicatorScore:
    """Single indicator score"""

    name: str
    score: float
    weight: float
    basis: str = "rule"
    confidence: Optional[str] = None
    summary: Optional[str] = None


@dataclass(frozen=True)
class DimensionScore:
    """Single dimension score"""

    dimension: str
    weight: float
    score: float
    indicators: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FrameworkScore:
    """Six-dimension research framework total score"""

    dimension_total: float
    dimensions: tuple[Any, ...]
    version: str = "v1"
    warnings: tuple[Any, ...] = field(default_factory=tuple)


def validate_weights(weights: List[float]) -> None:
    """
    Validate that weights sum to 1.0

    Args:
        weights: List of weights

    Raises:
        ValueError: When weights don't sum to 1.0
    """
    weight_sum = sum(weights)
    if abs(weight_sum - 1.0) > WEIGHT_EPSILON:
        raise ValueError(
            f"Weights must sum to 1.0, got {weight_sum}. "
            f"Diff: {abs(weight_sum - 1.0):.6f}"
        )


def validate_weights_safe(weights: List[float]) -> tuple[bool, Optional[str]]:
    """
    Safe weight validation, returns result instead of raising exception

    Returns:
        (Pass validation, Error message)
    """
    weight_sum = sum(weights)
    if abs(weight_sum - 1.0) > WEIGHT_EPSILON:
        return False, (
            f"Weights must sum to 1.0, got {weight_sum:.6f}. "
            f"Difference: {abs(weight_sum - 1.0):.6f}"
        )
    return True, None


def fill_missing_score(
    score: Optional[float], default: float = DEFAULT_NEUTRAL_SCORE
) -> float:
    """
    Fill missing score

    Missing data → Neutral score 50, no exception

    Args:
        score: Raw score, None means missing
        default: Default score

    Returns:
        Filled score
    """
    if score is None or not (0 <= score <= 100):
        return default
    return score


def aggregate_dimension(
    indicators: List[Dict[str, Any]], default_score: float = DEFAULT_NEUTRAL_SCORE
) -> tuple[float, List[IndicatorScore]]:
    """
    Aggregate single dimension's indicator scores

    Args:
        indicators: List of indicators, each contains name, score, weight, basis, confidence, summary
        default_score: Default score for missing data

    Returns:
        (Dimension score, List of indicator scores)
    """
    if not indicators:
        return default_score, []

    parsed = []
    total_weight = 0.0

    for ind in indicators:
        score = fill_missing_score(ind.get("score"))
        weight = ind.get("weight", 1.0 / len(indicators))
        total_weight += weight

        parsed.append(
            IndicatorScore(
                name=ind.get("name", "unknown"),
                score=score,
                weight=weight,
                basis=ind.get("basis", "rule"),
                confidence=ind.get("confidence"),
                summary=ind.get("summary"),
            )
        )

    if total_weight > 0:
        for i, p in enumerate(parsed):
            parsed[i] = IndicatorScore(
                name=p.name,
                score=p.score,
                weight=p.weight / total_weight,
                basis=p.basis,
                confidence=p.confidence,
                summary=p.summary,
            )

    dimension_score = sum(p.score * p.weight for p in parsed)

    return dimension_score, parsed


def aggregate_framework(
    dimensions: List[Dict[str, Any]], version: str = "v1"
) -> FrameworkScore:
    """
    Aggregate six dimensions to total score

    Args:
        dimensions: Six dimensions list, each contains:
            - dimension: str Dimension name
            - weight: float Weight [0, 1]
            - score: float Dimension score [0, 100] (optional, missing uses 50)
            - indicators: List[Dict] Indicator list (optional)
        version: Scoring version

    Returns:
        FrameworkScore

    Raises:
        ValueError: Weight sum doesn't equal 1.0

    Examples:
        >>> result = aggregate_framework([
        ...     {"dimension": "产业链定位", "weight": 0.25, "score": 80},
        ...     {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
        ...     {"dimension": "资金面", "weight": 0.15, "score": 65},
        ...     {"dimension": "技术面", "weight": 0.10, "score": 75},
        ...     {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
        ...     {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
        ... ])
        >>> result.dimension_total
        70.75
    """
    weights = [d.get("weight", DEFAULT_WEIGHT) for d in dimensions]

    valid, error = validate_weights_safe(weights)
    if not valid:
        raise ValueError(error)

    parsed_dims = []
    total = 0.0
    warnings = []

    for dim in dimensions:
        dimension_name = dim.get("dimension", "unknown")
        weight = dim.get("weight", DEFAULT_WEIGHT)

        if "indicators" in dim and dim["indicators"]:
            dim_score, indicators = aggregate_dimension(dim["indicators"])
        else:
            dim_score = fill_missing_score(dim.get("score"))
            indicators = []

        total += dim_score * weight

        parsed_dims.append(
            DimensionScore(
                dimension=dimension_name,
                weight=weight,
                score=dim_score,
                indicators=tuple(indicators),
            )
        )

        if dim.get("score") is None and not dim.get("indicators"):
            warnings.append(
                f"Dimension '{dimension_name}' data missing, using neutral score {DEFAULT_NEUTRAL_SCORE}"
            )

    return FrameworkScore(
        dimension_total=total,
        dimensions=tuple(parsed_dims),
        version=version,
        warnings=tuple(warnings),
    )


def get_default_weights() -> Dict[str, float]:
    """Get six-dimension default weights"""
    return dict(DEFAULT_DIMENSION_WEIGHTS)


def get_weight_sum() -> float:
    """Get weight sum (should be 1.0)"""
    return sum(DEFAULT_DIMENSION_WEIGHTS.values())
