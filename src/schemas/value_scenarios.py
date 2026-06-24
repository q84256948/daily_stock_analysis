# -*- coding: utf-8 -*-
"""
Value Scenarios Schema.

Defines data structures for long-term value scenarios.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Scenario(BaseModel):
    """Scenario"""

    type: Literal["optimistic", "neutral", "pessimistic"] = Field(...)
    probability: float = Field(..., ge=0, le=1)
    value_anchor: Optional[float] = Field(None, description="Value anchor price")
    description: Optional[str] = Field(None)


class ValueHorizons(BaseModel):
    """Value horizons"""

    horizon_1y: Optional[str] = Field(None, description="1-year value range")
    horizon_3y: Optional[str] = Field(None, description="3-year value range")
    horizon_5y: Optional[str] = Field(None, description="5-year value range")


class ValueScenarios(BaseModel):
    """Long-term value and scenarios"""

    industry_space: Optional[str] = Field(None, description="Industry space/size")
    competitive_evolution: Optional[str] = Field(
        None, description="Competitive landscape evolution"
    )
    scenarios: List[Scenario] = Field(default_factory=list)
    horizons: Optional[ValueHorizons] = Field(None)
    catalysts: List[str] = Field(default_factory=list, description="Future catalysts")
    risks: List[str] = Field(default_factory=list, description="Long-term risks")
