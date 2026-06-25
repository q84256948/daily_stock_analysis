# -*- coding: utf-8 -*-
"""
Scoring Module - Long-term Research Investment Framework

Core components:
- bayesian: Bayesian probability engine (prior, edge, posterior, position)
- engine: Six-dimension weighted aggregation engine
- normalization: Score normalization and clamping utilities
- contracts: Data contracts for inputs and outputs
- weights: Six-dimension weight configuration
- indicators/: Individual dimension scoring implementations
"""

from src.scoring.bayesian import (
    BayesianResult,
    calculate_bayesian,
    map_prior,
    calculate_edge,
    update_posterior,
    map_position,
    check_stop_conditions,
    validate_position_with_concentration,
)
from src.scoring.engine import (
    FrameworkScore,
    DimensionScore,
    IndicatorScore,
    aggregate_framework,
    aggregate_dimension,
    validate_weights,
    validate_weights_safe,
    fill_missing_score,
    get_default_weights,
    DEFAULT_NEUTRAL_SCORE,
)
from src.scoring.normalization import clamp, normalize_score, map_to_percentile

__all__ = [
    # Bayesian
    "BayesianResult",
    "calculate_bayesian",
    "map_prior",
    "calculate_edge",
    "update_posterior",
    "map_position",
    "check_stop_conditions",
    "validate_position_with_concentration",
    # Engine
    "FrameworkScore",
    "DimensionScore",
    "IndicatorScore",
    "aggregate_framework",
    "aggregate_dimension",
    "validate_weights",
    "validate_weights_safe",
    "fill_missing_score",
    "get_default_weights",
    "DEFAULT_NEUTRAL_SCORE",
    # Normalization
    "clamp",
    "normalize_score",
    "map_to_percentile",
]
