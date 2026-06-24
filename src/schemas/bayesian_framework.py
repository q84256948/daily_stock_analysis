# -*- coding: utf-8 -*-
"""
Bayesian Framework Schema.

Defines data structures for Bayesian probability calculations.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class EvidenceItem(BaseModel):
    """Evidence item for posterior update"""

    evidence: str = Field(..., description="Evidence content")
    strength: Literal[
        "strong_positive",
        "weak_positive",
        "neutral",
        "weak_negative",
        "strong_negative",
    ] = Field(..., description="Evidence strength")
    lr: float = Field(..., ge=0, description="Likelihood ratio")
    posterior_p: float = Field(
        ..., ge=0, le=1, description="Updated posterior probability"
    )
    date: str = Field(..., description="Evidence date (ISO format)")

    @field_validator("lr")
    @classmethod
    def validate_lr(cls, v):
        if v <= 0:
            raise ValueError(f"LR must be > 0, got {v}")
        return v


class StopConditions(BaseModel):
    """Stop loss conditions"""

    posterior_below_prior_threshold: bool = Field(
        False, description="Posterior dropped below prior × 60% threshold"
    )
    strong_negative_evidence: bool = Field(
        False, description="Strong negative evidence appeared"
    )
    edge_disappeared: bool = Field(
        False, description="Cognitive difference disappeared"
    )
    concentration_warning: Optional[str] = Field(
        None, description="Concentration warning message"
    )
    should_stop: bool = Field(
        False, description="Comprehensive stop loss recommendation"
    )


class BayesianFramework(BaseModel):
    """Bayesian probability framework"""

    prior_p: float = Field(..., ge=0, le=1, description="Prior probability P(H)")
    market_implied_p: float = Field(
        ..., ge=0, le=1, description="Market implied probability"
    )
    edge: float = Field(..., ge=-1, le=1, description="Edge = Prior - Market implied")
    posterior_p: float = Field(
        ..., ge=0, le=1, description="Posterior probability P(H|E)"
    )
    position_suggestion: str = Field(
        ..., description="Position suggestion (e.g., '3-5%')"
    )
    confidence: Literal["高", "中", "低", "观察"] = Field(
        "观察", description="Confidence level"
    )
    evidence_log: List[EvidenceItem] = Field(
        default_factory=list, description="Evidence log"
    )
    stop_conditions: Optional[StopConditions] = Field(
        None, description="Stop loss conditions"
    )

    @field_validator("edge")
    @classmethod
    def validate_edge(cls, v):
        return round(v, 6)
