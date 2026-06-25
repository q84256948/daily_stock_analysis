# -*- coding: utf-8 -*-
"""
Bayesian Probability Engine - Pure functions, no external dependencies.

Core functions:
- map_prior(): Six-dimension total → Prior probability
- calculate_edge(): Prior - Market implied
- update_posterior(): Posterior update (likelihood ratio)
- map_position(): Edge → Position suggestion
- check_stop_conditions(): Long-term stop loss checks
"""

from dataclasses import dataclass
from typing import Optional

DEFAULT_NEUTRAL_SCORE = 50.0


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to range with floating point tolerance."""
    return max(min_val, min(max_val, value))


def odds(p: float) -> float:
    """
    Probability → Odds
    O = P / (1 - P)

    Args:
        p: Probability [0, 1)

    Returns:
        Odds value

    Raises:
        ValueError: When P >= 1
    """
    if p >= 1:
        raise ValueError(f"Cannot compute odds for p >= 1, got {p}")
    if p < 0:
        return 0.0
    return p / (1 - p)


def probability(odds_val: float) -> float:
    """
    Odds → Probability
    P = O / (1 + O)

    Args:
        odds_val: Odds >= 0

    Returns:
        Probability [0, 1]
    """
    if odds_val < 0:
        raise ValueError(f"Odds must be >= 0, got {odds_val}")
    if odds_val == float("inf"):
        return 1.0
    return odds_val / (1 + odds_val)


def map_prior(dimension_total: float) -> float:
    """
    Six-dimension weighted total → Prior probability P(H)

    Mapping table:
    | Dimension Total | Prior P(H) | Meaning                    |
    |-----------------|------------|----------------------------|
    | ≥85             | 0.80–1.00  | Extreme bottleneck/long-term winner |
    | 70–85           | 0.60–0.80  | Strong bottleneck          |
    | 55–70           | 0.40–0.60  | Medium                     |
    | 40–55           | 0.20–0.40  | Weak                       |
    | <40             | 0.00–0.20  | Non-bottleneck/commoditized |

    Args:
        dimension_total: Six-dimension weighted total [0, 100]

    Returns:
        Prior probability P(H) [0, 1]
    """
    if dimension_total >= 85:
        ratio = (dimension_total - 85) / 15.0
        result = 0.80 + ratio * 0.20
    elif dimension_total >= 70:
        ratio = (dimension_total - 70) / 15.0
        result = 0.60 + ratio * 0.20
    elif dimension_total >= 55:
        ratio = (dimension_total - 55) / 15.0
        result = 0.40 + ratio * 0.20
    elif dimension_total >= 40:
        ratio = (dimension_total - 40) / 15.0
        result = 0.20 + ratio * 0.20
    else:
        result = dimension_total / 40.0 * 0.20

    return _clamp(result, 0.0, 1.0)


def calculate_edge(prior_p: float, market_implied_p: float) -> float:
    """
    Calculate cognitive difference Edge

    Edge = P(H) - P_market

    Args:
        prior_p: Prior probability [0, 1]
        market_implied_p: Market implied probability [0, 1]

    Returns:
        Edge (-1 to 1), positive means positive Edge
    """
    return prior_p - market_implied_p


def update_posterior(prior_p: float, lr: float) -> float:
    """
    Bayesian posterior update (odds form)

    O(H|E) = O(H) × LR
    P(H|E) = O(H|E) / (1 + O(H|E))

    Likelihood Ratio reference:
    | Evidence Strength | LR Range | Typical Evidence              |
    |-------------------|----------|--------------------------------|
    | Strong positive   | 5–10     | Exclusive large customer order, competitor exit |
    | Weak positive      | 2–3      | Industry demand improvement, small batch orders |
    | Neutral            | ~1       | No major news, technical fluctuation |
    | Weak negative      | 0.3–0.5  | Slightly below quarter expectations, new competitor |
    | Strong negative    | 0.1–0.2  | Tech route disruption, core patent invalidation |

    Args:
        prior_p: Prior probability (0, 1)
        lr: Likelihood Ratio > 0

    Returns:
        Posterior probability P(H|E) [0, 1]
    """
    if lr <= 0:
        raise ValueError(f"LR must be > 0, got {lr}")

    prior_odds = odds(prior_p)
    posterior_odds = prior_odds * lr
    posterior_p = probability(posterior_odds)

    return _clamp(posterior_p, 0.0, 1.0)


def map_position(edge: float) -> tuple[str, str]:
    """
    Edge → Position suggestion

    | Edge Range       | Position   | Confidence |
    |------------------|------------|-----------|
    | >50% (>0.5)      | 5-8%       | High      |
    | 30-50%           | 3-5%       | Medium    |
    | 10-30%           | 1-3%       | Low       |
    | <10% (<0.1)      | 0-1%       | Observe   |

    Args:
        edge: Edge value (-1 to 1)

    Returns:
        (Position suggestion, Confidence level)
    """
    if edge > 0.5:
        return "5-8%", "高"
    elif edge > 0.3:
        return "3-5%", "中"
    elif edge > 0.1:
        return "1-3%", "低"
    else:
        return "0-1%", "观察"


def check_stop_conditions(
    prior_p: float,
    posterior_p: float,
    market_implied_p: float,
    strong_negative_evidence: bool = False,
) -> dict:
    """
    Long-term stop loss condition check

    Trigger any condition → consider stop loss:
    1. Posterior drops below prior × 60% threshold
    2. Strong negative evidence appears
    3. Cognitive difference disappears (market implied ≥ prior)

    Note: Long-term stop loss uses posterior/cognitive difference logic, not short-term technical levels

    Args:
        prior_p: Prior probability
        posterior_p: Posterior probability
        market_implied_p: Market implied probability
        strong_negative_evidence: Whether strong negative evidence exists

    Returns:
        dict with stop conditions status
    """
    return {
        "posterior_below_prior_threshold": posterior_p < prior_p * 0.6,
        "strong_negative_evidence": strong_negative_evidence,
        "edge_disappeared": market_implied_p >= prior_p,
        "should_stop": (
            posterior_p < prior_p * 0.6
            or strong_negative_evidence
            or market_implied_p >= prior_p
        ),
    }


def validate_position_with_concentration(
    suggested_position: str, current_concentration: float, sector_limit: float = 0.4
) -> tuple[bool, Optional[str]]:
    """
    Validate position suggestion with sector concentration

    Single sector concentration ≤ 40% constraint

    Args:
        suggested_position: Suggested position (e.g., "5-8%")
        current_concentration: Current sector concentration [0, 1]
        sector_limit: Sector concentration limit (default 40%)

    Returns:
        (Pass validation, Warning message)
    """
    position_map = {
        "0-1%": 0.005,
        "1-3%": 0.02,
        "3-5%": 0.04,
        "5-8%": 0.065,
    }
    new_position = position_map.get(suggested_position, 0.01)

    if current_concentration + new_position > sector_limit:
        adjusted = sector_limit - current_concentration
        adjusted_str = f"{max(0, adjusted * 100):.1f}%"
        return False, (
            f"Exceeds sector concentration limit ({sector_limit * 100:.0f}%), "
            f"suggest adjusting position to {adjusted_str} or below"
        )

    return True, None


@dataclass(frozen=True)
class BayesianResult:
    """Bayesian calculation result"""

    prior_p: float
    market_implied_p: float
    edge: float
    posterior_p: float
    position_suggestion: str
    stop_conditions: dict

    def __post_init__(self):
        assert 0 <= self.prior_p <= 1, f"prior_p must be in [0,1], got {self.prior_p}"
        assert 0 <= self.market_implied_p <= 1, f"market_implied_p must be in [0,1]"
        assert 0 <= self.posterior_p <= 1, f"posterior_p must be in [0,1]"


def calculate_bayesian(
    dimension_total: float,
    market_implied_p: float,
    lr: float = 1.0,
    strong_negative_evidence: bool = False,
    current_concentration: float = 0.0,
) -> BayesianResult:
    """
    Complete Bayesian calculation entry point

    One-stop calculation: Prior → Edge → Posterior → Position → Stop loss

    Args:
        dimension_total: Six-dimension weighted total [0, 100]
        market_implied_p: Market implied probability [0, 1]
        lr: Likelihood ratio (default 1.0 = no new evidence)
        strong_negative_evidence: Whether strong negative evidence exists
        current_concentration: Current sector concentration [0, 1]

    Returns:
        BayesianResult
    """
    prior_p = map_prior(dimension_total)
    edge = calculate_edge(prior_p, market_implied_p)
    posterior_p = update_posterior(prior_p, lr)
    position_suggestion, _ = map_position(edge)

    stop_conditions = check_stop_conditions(
        prior_p, posterior_p, market_implied_p, strong_negative_evidence
    )

    valid, warning = validate_position_with_concentration(
        position_suggestion, current_concentration
    )
    if warning:
        stop_conditions["concentration_warning"] = warning

    return BayesianResult(
        prior_p=prior_p,
        market_implied_p=market_implied_p,
        edge=edge,
        posterior_p=posterior_p,
        position_suggestion=position_suggestion,
        stop_conditions=stop_conditions,
    )
