# -*- coding: utf-8 -*-
"""
Tests for normalization utilities.
"""

import pytest
from src.scoring.normalization import (
    clamp,
    normalize_score,
    map_to_percentile,
    z_score_to_percentile,
    DEFAULT_NEUTRAL_SCORE,
)


class TestClamp:
    """Test clamp function"""

    def test_clamp_within_range(self):
        assert clamp(50, 0, 100) == 50

    def test_clamp_below_min(self):
        assert clamp(-10, 0, 100) == 0

    def test_clamp_above_max(self):
        assert clamp(150, 0, 100) == 100

    def test_clamp_custom_range(self):
        assert clamp(5, 0, 10) == 5
        assert clamp(-5, 0, 10) == 0
        assert clamp(15, 0, 10) == 10

    def test_clamp_boundary(self):
        assert clamp(0, 0, 100) == 0
        assert clamp(100, 0, 100) == 100


class TestNormalizeScore:
    """Test normalize_score function"""

    def test_normal_score(self):
        assert normalize_score(75.0) == 75.0

    def test_none_score(self):
        assert normalize_score(None) == DEFAULT_NEUTRAL_SCORE

    def test_out_of_range_score(self):
        assert normalize_score(-10) == 0.0
        assert normalize_score(150) == 100.0

    def test_custom_default(self):
        assert normalize_score(None, default=60.0) == 60.0

    def test_boundary_scores(self):
        assert normalize_score(0.0) == 0.0
        assert normalize_score(100.0) == 100.0


class TestMapToPercentile:
    """Test map_to_percentile function"""

    def test_median(self):
        result = map_to_percentile(50, 0, 100)
        assert abs(result - 50) < 0.001

    def test_quarter(self):
        result = map_to_percentile(25, 0, 100)
        assert abs(result - 25) < 0.001

    def test_at_min(self):
        result = map_to_percentile(0, 0, 100)
        assert result == 0.0

    def test_at_max(self):
        result = map_to_percentile(100, 0, 100)
        assert result == 100.0

    def test_beyond_range(self):
        assert map_to_percentile(-10, 0, 100) == 0.0
        assert map_to_percentile(150, 0, 100) == 100.0

    def test_invalid_range(self):
        assert map_to_percentile(50, 100, 0) == DEFAULT_NEUTRAL_SCORE
        assert map_to_percentile(50, 100, 100) == DEFAULT_NEUTRAL_SCORE

    def test_custom_range(self):
        result = map_to_percentile(15, 10, 20)
        assert abs(result - 50) < 0.001


class TestZScoreToPercentile:
    """Test z_score_to_percentile function"""

    def test_zero_zscore(self):
        result = z_score_to_percentile(0)
        assert abs(result - 50) < 0.001

    def test_positive_zscore(self):
        result = z_score_to_percentile(1)
        assert abs(result - 84.1) < 0.1

    def test_negative_zscore(self):
        result = z_score_to_percentile(-1)
        assert abs(result - 15.9) < 0.1

    def test_extreme_positive(self):
        result = z_score_to_percentile(3)
        assert abs(result - 99.9) < 0.1

    def test_extreme_negative(self):
        result = z_score_to_percentile(-3)
        assert abs(result - 0.1) < 0.1

    def test_mapped_values(self):
        for z, expected in [(2, 97.7), (1.5, 93.3), (-1.5, 6.7), (-2, 2.3)]:
            result = z_score_to_percentile(z)
            assert abs(result - expected) < 0.1

    def test_interpolated_values(self):
        result = z_score_to_percentile(0.75)
        assert 50 < result < 84.1
