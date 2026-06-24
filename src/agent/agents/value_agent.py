# -*- coding: utf-8 -*-
"""
ValueAgent — long-term value scenario specialist.

Responsible for:
- Analyzing value horizons (1Y/3Y/5Y)
- Building bull/base/bear scenarios with probability
- Calculating investment edge
- Identifying catalysts and risks
- Producing a structured value investment opinion
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json

logger = logging.getLogger(__name__)


class ValueAgent(BaseAgent):
    agent_name = "value"
    max_steps = 4
    tool_names = [
        "get_stock_info",
        "get_realtime_quote",
        "get_financial_indicators",
        "get_sector_pe",
    ]

    def system_prompt(self, ctx: AgentContext) -> str:
        return """\
You are a **Long-Term Value Investment Analyst** specialising in A-shares, \
HK, and US equities.

Your task: analyze the stock's long-term investment value through scenario \
analysis and value horizon determination.

## Workflow
1. Call get_stock_info to get basic company information and industry context
2. Call get_realtime_quote to get current price and valuation metrics
3. Call get_financial_indicators to get fundamental data (PE, PB, ROE, growth rates)
4. Call get_sector_pe to compare against sector average valuations
5. Build value scenarios and calculate investment edge

## Value Score Classification (0-100)
- 90-100: Extremely undervalued, strongly recommended
- 75-89: Clearly undervalued, good opportunity
- 60-74: Slightly undervalued, worth watching
- 50-59: Fairly valued
- 40-49: Slightly overvalued
- 25-39: Clearly overvalued
- 0-24: Extremely overvalued

## Scenario Probability Guidelines
- Bull case probability: 0.10-0.30
- Base case probability: 0.40-0.60 (typically highest)
- Bear case probability: 0.10-0.30
- All three probabilities should sum to 1.0

## Edge Calculation
- edge = (bull_prob * bull_return) - (bear_prob * bear_loss) - risk_free_rate
- Positive edge (> 0.1) suggests favorable risk/reward
- Edge < 0 suggests unfavorable risk/reward

## Value Horizon Guidelines
- 1Y: Near-term value based on current catalysts and earnings trajectory
- 3Y: Medium-term value based on business growth and market cycles
- 5Y: Long-term value based on business model sustainability and industry trends

## Output Format
Return **only** a JSON object:
{
  "value_horizons": {
    "horizon_1y": "1-year value range (e.g., 150-180元)",
    "horizon_3y": "3-year value range",
    "horizon_5y": "5-year value range"
  },
  "scenarios": {
    "bull_case": {
      "probability": 0.0-0.5,
      "value_anchor": "Target price in bull case",
      "upside_pct": 0-500,
      "key_assumptions": ["assumption1", "assumption2"],
      "timeframe_years": 1-5
    },
    "base_case": {
      "probability": 0.3-0.6,
      "value_anchor": "Target price in base case",
      "upside_pct": 0-200,
      "key_assumptions": ["assumption1", "assumption2"],
      "timeframe_years": 1-5
    },
    "bear_case": {
      "probability": 0.1-0.3,
      "value_anchor": "Target price in bear case",
      "downside_pct": 0-50,
      "key_assumptions": ["assumption1", "assumption2"],
      "timeframe_years": 1-5
    }
  },
  "edge_calculation": {
    "prior_probability": 0.3-0.7,
    "market_implied_prob": 0.3-0.7,
    "edge": -1.0到1.0,
    "edge_rationale": "Edge calculation reasoning"
  },
  "catalysts": ["catalyst1", "catalyst2", "catalyst3", "catalyst4", "catalyst5"],
  "risks": ["risk1", "risk2", "risk3", "risk4", "risk5"],
  "value_score": 0-100,
  "signal": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.0-1.0,
  "reasoning": "Overall value analysis summary"
}

Note: All three scenario probabilities MUST sum to 1.0.
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        parts = [f"Analyze long-term value for stock **{ctx.stock_code}**"]
        if ctx.stock_name:
            parts[0] += f" ({ctx.stock_name})"
        parts.append(
            "Steps:\n"
            "1. Call get_stock_info to get industry and business context.\n"
            "2. Call get_realtime_quote to get current price and valuation.\n"
            "3. Call get_financial_indicators to get fundamental metrics.\n"
            "4. Call get_sector_pe to compare with sector averages.\n"
            "5. Output the JSON opinion including value horizons and scenario analysis.\n"
            "6. Ensure the three scenario probabilities sum to 1.0."
        )
        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_text: str) -> Optional[AgentOpinion]:
        parsed = try_parse_json(raw_text)
        if parsed is None:
            logger.warning("[ValueAgent] failed to parse opinion JSON")
            return None

        ctx.set_data("value_opinion", parsed)

        scenarios = parsed.get("scenarios", {})
        if isinstance(scenarios, dict):
            probs = [
                scenarios.get("bull_case", {}).get("probability", 0),
                scenarios.get("base_case", {}).get("probability", 0),
                scenarios.get("bear_case", {}).get("probability", 0),
            ]
            prob_sum = sum(probs)
            prob_sum = sum(probs)
            if prob_sum > 0 and abs(prob_sum - 1.0) > 0.05:
                logger.warning(
                    "[ValueAgent] scenario probabilities don't sum to 1.0: %s", probs
                )

        signal = parsed.get("signal", "hold")
        if signal not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
            signal = "hold"

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        reasoning = parsed.get("reasoning", "")
        catalysts = parsed.get("catalysts", [])
        if isinstance(catalysts, list) and reasoning:
            reasoning = (
                reasoning + "\n\n催化剂:\n" + "\n".join(f"- {c}" for c in catalysts[:3])
            )

        return AgentOpinion(
            agent_name=self.agent_name,
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            raw_data=parsed,
        )
