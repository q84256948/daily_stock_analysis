# -*- coding: utf-8 -*-
"""
Tests for Bayesian probability engine.
"""

import pytest
from src.scoring.bayesian import (
    BayesianResult,
    _clamp,
    odds,
    probability,
    map_prior,
    calculate_edge,
    update_posterior,
    map_position,
    check_stop_conditions,
    validate_position_with_concentration,
    calculate_bayesian,
)


class TestClamp:
    """Test _clamp function"""

    def test_clamp_within_range(self):
        assert _clamp(50, 0, 100) == 50

    def test_clamp_below_min(self):
        assert _clamp(-10, 0, 100) == 0

    def test_clamp_above_max(self):
        assert _clamp(150, 0, 100) == 100

    def test_clamp_edge_cases(self):
        assert _clamp(0, 0, 100) == 0
        assert _clamp(100, 0, 100) == 100


class TestOdds:
    """Test odds function"""

    def test_odds_zero(self):
        assert odds(0) == 0.0

    def test_odds_half(self):
        assert odds(0.5) == 1.0

    def test_odds_one_third(self):
        assert abs(odds(1 / 3) - 0.5) < 0.001

    def test_odds_invalid_p(self):
        with pytest.raises(ValueError):
            odds(1)

        assert odds(-0.5) == 0.0


class TestProbability:
    """Test probability function"""

    def test_probability_zero(self):
        assert probability(0) == 0.0

    def test_probability_one(self):
        assert probability(float("inf")) == 1.0

    def test_probability_one_odd(self):
        assert probability(1) == 0.5

    def test_probability_invalid(self):
        with pytest.raises(ValueError):
            probability(-1)


class TestMapPrior:
    """Test map_prior function"""

    def test_map_prior_extreme_high(self):
        assert abs(map_prior(100) - 1.0) < 0.001

    def test_map_prior_very_high(self):
        result = map_prior(90)
        assert 0.8 < result < 0.9

    def test_map_prior_high(self):
        result = map_prior(80)
        assert 0.7 < result < 0.8

    def test_map_prior_medium_high(self):
        result = map_prior(70)
        assert 0.55 < result <= 0.7

    def test_map_prior_medium(self):
        result = map_prior(60)
        assert 0.4 < result < 0.6

    def test_map_prior_low(self):
        result = map_prior(50)
        assert 0.2 < result < 0.4

    def test_map_prior_very_low(self):
        result = map_prior(30)
        assert 0.0 < result < 0.2

    def test_map_prior_zero(self):
        assert map_prior(0) == 0.0

    def test_map_prior_boundary_85(self):
        assert abs(map_prior(85) - 0.8) < 0.001

    def test_map_prior_boundary_70(self):
        assert abs(map_prior(70) - 0.6) < 0.001

    def test_map_prior_boundary_55(self):
        assert abs(map_prior(55) - 0.4) < 0.001

    def test_map_prior_boundary_40(self):
        assert abs(map_prior(40) - 0.2) < 0.001


class TestCalculateEdge:
    """Test calculate_edge function"""

    def test_edge_positive(self):
        assert abs(calculate_edge(0.7, 0.5) - 0.2) < 0.001

    def test_edge_negative(self):
        assert abs(calculate_edge(0.3, 0.6) + 0.3) < 0.001

    def test_edge_zero(self):
        assert calculate_edge(0.5, 0.5) == 0.0

    def test_edge_extreme_positive(self):
        assert abs(calculate_edge(1.0, 0.0) - 1.0) < 0.001

    def test_edge_extreme_negative(self):
        assert abs(calculate_edge(0.0, 1.0) + 1.0) < 0.001


class TestUpdatePosterior:
    """Test update_posterior function"""

    def test_posterior_no_change(self):
        result = update_posterior(0.5, 1.0)
        assert abs(result - 0.5) < 0.001

    def test_posterior_strong_positive(self):
        result = update_posterior(0.5, 8.0)
        assert result > 0.8

    def test_posterior_strong_negative(self):
        result = update_posterior(0.5, 0.125)
        assert result < 0.2

    def test_posterior_weak_positive(self):
        result = update_posterior(0.5, 2.5)
        assert 0.6 < result < 0.8

    def test_posterior_invalid_lr(self):
        with pytest.raises(ValueError):
            update_posterior(0.5, 0)

        with pytest.raises(ValueError):
            update_posterior(0.5, -1)

    def test_posterior_boundary_priors(self):
        assert update_posterior(0.0, 2.0) == 0.0

        result = update_posterior(0.99, 2.0)
        assert 0.99 < result < 1.0


class TestMapPosition:
    """Test map_position function"""

    def test_position_high_edge(self):
        pos, conf = map_position(0.6)
        assert pos == "5-8%"
        assert conf == "高"

    def test_position_medium_edge(self):
        pos, conf = map_position(0.4)
        assert pos == "3-5%"
        assert conf == "中"

    def test_position_low_edge(self):
        pos, conf = map_position(0.2)
        assert pos == "1-3%"
        assert conf == "低"

    def test_position_very_low_edge(self):
        pos, conf = map_position(0.05)
        assert pos == "0-1%"
        assert conf == "观察"

    def test_position_negative_edge(self):
        pos, conf = map_position(-0.2)
        assert pos == "0-1%"
        assert conf == "观察"

    def test_position_boundary(self):
        pos, _ = map_position(0.51)
        assert pos == "5-8%"

        pos, _ = map_position(0.5)
        assert pos == "3-5%"

        pos, _ = map_position(0.31)
        assert pos == "3-5%"

        pos, _ = map_position(0.3)
        assert pos == "1-3%"

        pos, _ = map_position(0.11)
        assert pos == "1-3%"

        pos, _ = map_position(0.101)
        assert pos == "1-3%"

        pos, _ = map_position(0.1)
        assert pos == "0-1%"

        pos, _ = map_position(0.099)
        assert pos == "0-1%"


class TestCheckStopConditions:
    """Test check_stop_conditions function"""

    def test_no_stop_conditions(self):
        result = check_stop_conditions(0.7, 0.6, 0.4)
        assert result["should_stop"] is False
        assert result["posterior_below_prior_threshold"] is False
        assert result["edge_disappeared"] is False

    def test_posterior_below_threshold(self):
        result = check_stop_conditions(0.7, 0.4, 0.4)
        assert result["should_stop"] is True
        assert result["posterior_below_prior_threshold"] is True

    def test_strong_negative_evidence(self):
        result = check_stop_conditions(0.7, 0.6, 0.4, strong_negative_evidence=True)
        assert result["should_stop"] is True
        assert result["strong_negative_evidence"] is True

    def test_edge_disappeared(self):
        result = check_stop_conditions(0.5, 0.6, 0.6)
        assert result["should_stop"] is True
        assert result["edge_disappeared"] is True


class TestValidatePositionWithConcentration:
    """Test validate_position_with_concentration function"""

    def test_concentration_ok(self):
        valid, warning = validate_position_with_concentration("3-5%", 0.2)
        assert valid is True
        assert warning is None

    def test_concentration_exceeds(self):
        valid, warning = validate_position_with_concentration("5-8%", 0.35)
        assert valid is False
        assert warning is not None
        assert "集中度" in warning or "concentration" in warning.lower()

    def test_concentration_at_limit(self):
        valid, warning = validate_position_with_concentration("1-3%", 0.38)
        assert valid is True

    def test_unknown_position(self):
        valid, warning = validate_position_with_concentration("unknown", 0.2)
        assert valid is True


class TestCalculateBayesian:
    """Test calculate_bayesian function (full pipeline)"""

    def test_full_pipeline_high_score(self):
        result = calculate_bayesian(
            dimension_total=80,
            market_implied_p=0.5,
            lr=1.0,
        )

        assert isinstance(result, BayesianResult)
        assert 0.6 < result.prior_p < 0.8
        assert result.edge > 0
        assert result.position_suggestion in ["3-5%", "5-8%", "1-3%"]

    def test_full_pipeline_medium_score(self):
        result = calculate_bayesian(
            dimension_total=60,
            market_implied_p=0.5,
            lr=1.0,
        )

        assert 0.4 < result.prior_p < 0.6
        assert abs(result.edge) < 0.2

    def test_full_pipeline_low_score(self):
        result = calculate_bayesian(
            dimension_total=30,
            market_implied_p=0.5,
            lr=1.0,
        )

        assert result.prior_p < 0.2
        assert result.edge < 0

    def test_full_pipeline_with_evidence(self):
        result = calculate_bayesian(
            dimension_total=60,
            market_implied_p=0.5,
            lr=8.0,
        )

        assert result.posterior_p > result.prior_p

    def test_full_pipeline_with_concentration(self):
        result = calculate_bayesian(
            dimension_total=80,
            market_implied_p=0.3,
            current_concentration=0.35,
        )

        assert (
            "concentration_warning" in result.stop_conditions
            or result.stop_conditions.get("should_stop") is not None
        )

    def test_result_dataclass_fields(self):
        result = calculate_bayesian(dimension_total=70, market_implied_p=0.5)

        assert hasattr(result, "prior_p")
        assert hasattr(result, "market_implied_p")
        assert hasattr(result, "edge")
        assert hasattr(result, "posterior_p")
        assert hasattr(result, "position_suggestion")
        assert hasattr(result, "stop_conditions")
