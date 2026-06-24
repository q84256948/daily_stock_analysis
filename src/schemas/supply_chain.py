# -*- coding: utf-8 -*-
"""
Supply Chain Schema.

Defines data structures for supply chain analysis.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChainNode(BaseModel):
    """Supply chain node"""

    level: str = Field(..., description="Level")
    companies: List[str] = Field(default_factory=list)
    concentration: Optional[str] = Field(None)


class Chokepoint(BaseModel):
    """Bottleneck/chokepoint"""

    type: Literal["patent", "capacity", "geo", "tech", "cert"] = Field(...)
    description: str = Field(...)
    confidence: Literal["high", "medium", "low"] = Field("medium")


class USChinaChain(BaseModel):
    """US-China dual chain"""

    role: str = Field(..., description="Role in dual chain")
    substitution_progress: Optional[str] = Field(None)
    sanction_risk: Optional[str] = Field(None)
    dual_chain_impact: Optional[str] = Field(None)


class SupplyChain(BaseModel):
    """Supply chain analysis"""

    chain_map: List[ChainNode] = Field(default_factory=list)
    chokepoints: List[Chokepoint] = Field(default_factory=list)
    company_position: str = Field(..., description="Company's position in chain")
    upstream: List[str] = Field(default_factory=list)
    downstream: List[str] = Field(default_factory=list)
    bargaining_power: Optional[str] = Field(None)
    us_china_chain: Optional[USChinaChain] = Field(None)
