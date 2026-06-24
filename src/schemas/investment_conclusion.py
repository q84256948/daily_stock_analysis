# -*- coding: utf-8 -*-
"""
Investment Conclusion Schema.

Defines data structures for investment conclusion.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class InvestmentConclusion(BaseModel):
    """Investment conclusion"""

    prior_p: Optional[float] = Field(None, ge=0, le=1, description="Prior probability")
    market_implied_p: Optional[float] = Field(
        None, ge=0, le=1, description="Market implied probability"
    )
    edge: Optional[float] = Field(None, ge=-1, le=1, description="Edge")
    position: str = Field("观察", description="Position suggestion")
    value_range_1y: Optional[str] = Field(None, description="1-year value range")
    value_range_3y: Optional[str] = Field(None, description="3-year value range")
    value_range_5y: Optional[str] = Field(None, description="5-year value range")
    rationale: Optional[str] = Field(None, description="Investment rationale")
    action: Literal["建仓", "加仓", "持有", "减仓", "止损", "观察"] = Field("观察")
