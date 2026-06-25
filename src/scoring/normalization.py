# -*- coding: utf-8 -*-
"""
Score normalization and clamping utilities.

Pure functions with no external dependencies.
"""

from typing import Optional

DEFAULT_NEUTRAL_SCORE = 50.0


def clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """
    Clamp value to range with floating point tolerance.

    Args:
        value: Input value
        min_val: Minimum value (default 0.0)
        max_val: Maximum value (default 100.0)

    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def normalize_score(
    score: Optional[float], default: float = DEFAULT_NEUTRAL_SCORE
) -> float:
    """
    Normalize score to [0, 100] range, handling None/missing values.

    Args:
        score: Raw score (None means missing data)
        default: Default score for missing data (default 50.0)

    Returns:
        Normalized score in [0, 100]
    """
    if score is None:
        return default
    return clamp(score, 0.0, 100.0)


def map_to_percentile(value: float, min_val: float, max_val: float) -> float:
    """
    Map value to percentile [0, 100] based on min/max range.

    Args:
        value: Input value
        min_val: Minimum of range
        max_val: Maximum of range

    Returns:
        Percentile value [0, 100]
    """
    if max_val <= min_val:
        return DEFAULT_NEUTRAL_SCORE

    raw_percentile = (value - min_val) / (max_val - min_val) * 100
    return clamp(raw_percentile, 0.0, 100.0)


def z_score_to_percentile(z: float) -> float:
    """
    Convert z-score to percentile [0, 100].

    Uses approximation for common z-scores.

    Args:
        z: Z-score

    Returns:
        Percentile [0, 100]
    """
    z_percentile_map = {
        -3.0: 0.1,
        -2.5: 0.6,
        -2.0: 2.3,
        -1.5: 6.7,
        -1.0: 15.9,
        -0.5: 30.9,
        0.0: 50.0,
        0.5: 69.1,
        1.0: 84.1,
        1.5: 93.3,
        2.0: 97.7,
        2.5: 99.4,
        3.0: 99.9,
    }

    if z in z_percentile_map:
        return z_percentile_map[z]

    if z < -3:
        return 0.1
    if z > 3:
        return 99.9

    lower = max(k for k in z_percentile_map if k <= z)
    upper = min(k for k in z_percentile_map if k >= z)

    if lower == upper:
        return z_percentile_map[lower]

    lower_p = z_percentile_map[lower]
    upper_p = z_percentile_map[upper]
    ratio = (z - lower) / (upper - lower)

    return clamp(lower_p + ratio * (upper_p - lower_p), 0.0, 100.0)
