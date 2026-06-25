# -*- coding: utf-8 -*-
"""
Six-dimension indicator scoring implementations.

Each dimension has its own module:
- supply_chain: Supply chain positioning (LLM-driven)
- fundamental: Fundamentals and value (valuation=rule, moat=LLM)
- capital: Capital flow (rule: institutional/Northbound/margin/chips)
- technical: Technical analysis (rule: long-term trends)
- sentiment: Sentiment (research reports=rule aggregation, social=LLM)
- macro: Macro and geopolitics (liquidity=rule, China-US chain=LLM)
"""

from src.scoring.indicators.supply_chain import score_supply_chain
from src.scoring.indicators.fundamental import score_fundamental
from src.scoring.indicators.capital import score_capital
from src.scoring.indicators.technical import score_technical
from src.scoring.indicators.sentiment import score_sentiment
from src.scoring.indicators.macro import score_macro

__all__ = [
    "score_supply_chain",
    "score_fundamental",
    "score_capital",
    "score_technical",
    "score_sentiment",
    "score_macro",
]
