# -*- coding: utf-8 -*-
"""
Tests for scoring engine.
"""

import pytest
from src.scoring.engine import (
    FrameworkScore,
    DimensionScore,
    IndicatorScore,
    validate_weights,
    validate_weights_safe,
    fill_missing_score,
    aggregate_dimension,
    aggregate_framework,
    DEFAULT_NEUTRAL_SCORE,
)


class TestValidateWeights:
    """Test weight validation functions"""

    def test_valid_weights(self):
        weights = [0.25, 0.25, 0.15, 0.10, 0.15, 0.10]
        validate_weights(weights)

    def test_weights_sum_to_one(self):
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]
        validate_weights(weights)

    def test_weights_invalid_sum(self):
        weights = [0.3, 0.3, 0.3]
        with pytest.raises(ValueError):
            validate_weights(weights)

    def test_weights_safe_valid(self):
        valid, error = validate_weights_safe([0.25, 0.25, 0.25, 0.25])
        assert valid is True
        assert error is None

    def test_weights_safe_invalid(self):
        valid, error = validate_weights_safe([0.5, 0.3])
        assert valid is False
        assert error is not None


class TestFillMissingScore:
    """Test fill_missing_score function"""

    def test_normal_score(self):
        assert fill_missing_score(75.0) == 75.0

    def test_none_score(self):
        assert fill_missing_score(None) == DEFAULT_NEUTRAL_SCORE

    def test_below_range(self):
        assert fill_missing_score(-10.0) == DEFAULT_NEUTRAL_SCORE

    def test_above_range(self):
        assert fill_missing_score(150.0) == DEFAULT_NEUTRAL_SCORE

    def test_custom_default(self):
        assert fill_missing_score(None, default=60.0) == 60.0

    def test_boundary_values(self):
        assert fill_missing_score(0.0) == 0.0
        assert fill_missing_score(100.0) == 100.0


class TestAggregateDimension:
    """Test aggregate_dimension function"""

    def test_empty_indicators(self):
        score, indicators = aggregate_dimension([])
        assert score == DEFAULT_NEUTRAL_SCORE
        assert indicators == []

    def test_single_indicator(self):
        indicators = [{"name": "PE", "score": 80, "weight": 1.0}]
        score, result = aggregate_dimension(indicators)
        assert score == 80
        assert len(result) == 1

    def test_multiple_indicators(self):
        indicators = [
            {"name": "PE", "score": 80, "weight": 0.5},
            {"name": "PB", "score": 60, "weight": 0.5},
        ]
        score, result = aggregate_dimension(indicators)
        assert score == 70.0
        assert len(result) == 2

    def test_missing_score_uses_default(self):
        indicators = [
            {"name": "PE", "weight": 1.0},
        ]
        score, result = aggregate_dimension(indicators)
        assert score == DEFAULT_NEUTRAL_SCORE

    def test_indicator_with_basis(self):
        indicators = [
            {"name": "PE", "score": 80, "weight": 1.0, "basis": "rule"},
        ]
        score, result = aggregate_dimension(indicators)
        assert result[0].basis == "rule"

    def test_weight_normalization(self):
        indicators = [
            {"name": "A", "score": 80, "weight": 1.0},
            {"name": "B", "score": 60, "weight": 2.0},
        ]
        score, result = aggregate_dimension(indicators)
        expected = (80 * 1 / 3) + (60 * 2 / 3)
        assert abs(score - expected) < 0.001


class TestAggregateFramework:
    """Test aggregate_framework function"""

    def test_valid_six_dimensions(self):
        dimensions = [
            {"dimension": "产业链定位", "weight": 0.25, "score": 80},
            {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
            {"dimension": "资金面", "weight": 0.15, "score": 65},
            {"dimension": "技术面", "weight": 0.10, "score": 75},
            {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
            {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
        ]
        result = aggregate_framework(dimensions)

        assert isinstance(result, FrameworkScore)
        assert result.dimension_total > 0
        assert len(result.dimensions) == 6

    def test_missing_score_uses_neutral(self):
        dimensions = [
            {"dimension": "产业链定位", "weight": 0.25, "score": 80},
            {"dimension": "基本面与价值", "weight": 0.25},
            {"dimension": "资金面", "weight": 0.15, "score": 65},
            {"dimension": "技术面", "weight": 0.10, "score": 75},
            {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
            {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
        ]
        result = aggregate_framework(dimensions)

        assert len(result.warnings) > 0
        assert DEFAULT_NEUTRAL_SCORE in [d.score for d in result.dimensions]

    def test_invalid_weights(self):
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.3, "score": 70},
        ]
        with pytest.raises(ValueError):
            aggregate_framework(dimensions)

    def test_with_indicators(self):
        dimensions = [
            {
                "dimension": "产业链定位",
                "weight": 0.25,
                "indicators": [{"name": "位置", "score": 80, "weight": 1.0}],
            },
            {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
            {"dimension": "资金面", "weight": 0.15, "score": 65},
            {"dimension": "技术面", "weight": 0.10, "score": 75},
            {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
            {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
        ]
        result = aggregate_framework(dimensions)

        supply_chain_dim = next(
            d for d in result.dimensions if d.dimension == "产业链定位"
        )
        assert len(supply_chain_dim.indicators) == 1

    def test_dimension_total_calculation(self):
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)
        assert abs(result.dimension_total - 70.0) < 0.001

    def test_version(self):
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions, version="v2")
        assert result.version == "v2"

    def test_default_weight(self):
        dimensions = [
            {"dimension": "A", "score": 80},
            {"dimension": "B", "score": 60},
            {"dimension": "C", "score": 70},
            {"dimension": "D", "score": 80},
            {"dimension": "E", "score": 60},
            {"dimension": "F", "score": 70},
        ]
        result = aggregate_framework(dimensions)

        for dim in result.dimensions:
            assert abs(dim.weight - 1 / 6) < 0.001


class TestDataStructures:
    """Test data structures"""

    def test_framework_score_immutable(self):
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)

        with pytest.raises(Exception):
            result.dimension_total = 100

    def test_dimension_score_immutable(self):
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)

        with pytest.raises(Exception):
            result.dimensions[0].score = 100

    def test_indicator_score_fields(self):
        dimensions = [
            {
                "dimension": "A",
                "weight": 0.5,
                "indicators": [
                    {"name": "test", "score": 80, "weight": 1.0, "basis": "rule"}
                ],
            },
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)

        indicator = result.dimensions[0].indicators[0]
        assert indicator.name == "test"
        assert indicator.score == 80
        assert indicator.weight == 1.0
        assert indicator.basis == "rule"
