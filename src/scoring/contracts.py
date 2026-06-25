# -*- coding: utf-8 -*-
"""
Data contracts for scoring module.

Defines input/output structures for the scoring pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal


@dataclass(frozen=True)
class IndicatorInput:
    """Input for a single indicator."""

    name: str
    raw_value: float
    weight: float = 1.0
    basis: Literal["rule", "llm"] = "rule"
    confidence: Optional[Literal["high", "medium", "low"]] = None
    evidence: Optional[str] = None


@dataclass(frozen=True)
class DimensionInput:
    """Input for a single dimension."""

    dimension: str
    score: Optional[float] = None
    indicators: tuple[IndicatorInput, ...] = field(default_factory=tuple)
    weight: float = 1.0 / 6.0


@dataclass(frozen=True)
class FrameworkInput:
    """Input for the six-dimension framework."""

    supply_chain: Optional[DimensionInput] = None
    fundamental: Optional[DimensionInput] = None
    capital: Optional[DimensionInput] = None
    technical: Optional[DimensionInput] = None
    sentiment: Optional[DimensionInput] = None
    macro: Optional[DimensionInput] = None


@dataclass(frozen=True)
class ScoringContext:
    """Context for scoring execution."""

    stock_code: str
    stock_name: str
    market: Literal["cn", "hk", "us"] = "cn"
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    report_date: str = ""


@dataclass(frozen=True)
class LikelihoodRatioInput:
    """Input for likelihood ratio calculation."""

    evidence_type: Literal[
        "strong_positive",
        "weak_positive",
        "neutral",
        "weak_negative",
        "strong_negative",
    ]
    description: str
    lr_override: Optional[float] = None

    @property
    def lr(self) -> float:
        """Get likelihood ratio for evidence type."""
        if self.lr_override is not None:
            return self.lr_override
        lr_map = {
            "strong_positive": 8.0,
            "weak_positive": 2.5,
            "neutral": 1.0,
            "weak_negative": 0.4,
            "strong_negative": 0.15,
        }
        return lr_map.get(self.evidence_type, 1.0)
