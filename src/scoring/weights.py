# -*- coding: utf-8 -*-
"""
Six-dimension weight configuration.

Default weights based on long-term investment research framework:
| 维度             | 权重  | 说明                    |
|------------------|-------|-------------------------|
| 产业链定位        | 25%   | 核心瓶颈/护城河          |
| 基本面与价值      | 25%   | 估值/盈利能力/成长性     |
| 资金面           | 15%   | 机构持仓/北向/融资       |
| 技术面           | 10%   | 长期趋势（降权）         |
| 情绪与认知差      | 15%   | 市场预期差               |
| 宏观与地缘       | 10%   | 政策/中美链影响          |
"""

from typing import Dict, List

DEFAULT_DIMENSION_WEIGHTS: Dict[str, float] = {
    "产业链定位": 0.25,
    "基本面与价值": 0.25,
    "资金面": 0.15,
    "技术面": 0.10,
    "情绪与认知差": 0.15,
    "宏观与地缘": 0.10,
}

DEFAULT_VERSION = "v1.0"

WEIGHT_EPSILON = 1e-6


def get_default_weights() -> Dict[str, float]:
    """Get six-dimension default weights."""
    return dict(DEFAULT_DIMENSION_WEIGHTS)


def get_weight_values() -> List[float]:
    """Get weight values as list in standard order."""
    standard_order = [
        "产业链定位",
        "基本面与价值",
        "资金面",
        "技术面",
        "情绪与认知差",
        "宏观与地缘",
    ]
    return [DEFAULT_DIMENSION_WEIGHTS[k] for k in standard_order]


def get_weight_sum() -> float:
    """Get sum of all weights (should be 1.0)."""
    return sum(DEFAULT_DIMENSION_WEIGHTS.values())


def validate_weight_config(weights: Dict[str, float]) -> None:
    """
    Validate weight configuration.

    Args:
        weights: Dimension weights dictionary

    Raises:
        ValueError: If weights don't sum to 1.0 or missing dimensions
    """
    missing = set(DEFAULT_DIMENSION_WEIGHTS.keys()) - set(weights.keys())
    if missing:
        raise ValueError(f"Missing dimensions: {missing}")

    extra = set(weights.keys()) - set(DEFAULT_DIMENSION_WEIGHTS.keys())
    if extra:
        raise ValueError(f"Unknown dimensions: {extra}")

    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > WEIGHT_EPSILON:
        raise ValueError(
            f"Weights must sum to 1.0, got {weight_sum}. "
            f"Difference: {abs(weight_sum - 1.0):.6f}"
        )


def get_dimension_order() -> List[str]:
    """Get standard dimension order."""
    return list(DEFAULT_DIMENSION_WEIGHTS.keys())
