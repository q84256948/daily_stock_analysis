# -*- coding: utf-8 -*-
"""
Tests for indicator scoring modules.
"""

import pytest
from src.scoring.indicators import (
    score_supply_chain,
    score_fundamental,
    score_capital,
    score_technical,
    score_sentiment,
    score_macro,
)


class TestSupplyChain:
    """Test supply chain scoring"""

    def test_bottleneck_position(self):
        result = score_supply_chain(chain_position="bottleneck")
        assert result["score"] >= 90
        assert result["dimension"] == "产业链定位"

    def test_commodity_position(self):
        result = score_supply_chain(chain_position="commodity")
        assert result["score"] < 50

    def test_strong_moat(self):
        result = score_supply_chain(moat_type="patent", moat_strength="strong")
        assert result["score"] >= 80

    def test_no_moat(self):
        result = score_supply_chain(moat_type="brand", moat_strength="none")
        assert result["score"] < 50

    def test_low_us_china_risk(self):
        result = score_supply_chain(us_china_risk="low")
        assert result["score"] >= 70

    def test_high_us_china_risk(self):
        result = score_supply_chain(us_china_risk="high")
        assert result["score"] < 50

    def test_missing_data(self):
        result = score_supply_chain()
        assert result["score"] == 50.0
        assert "warnings" in result or len(result["indicators"]) > 0

    def test_indicators_returned(self):
        result = score_supply_chain(
            chain_position="bottleneck",
            moat_type="patent",
            moat_strength="strong",
        )
        assert len(result["indicators"]) >= 2


class TestFundamental:
    """Test fundamental scoring"""

    def test_low_valuation(self):
        result = score_fundamental(pe_percentile=10, pb_percentile=10)
        assert result["score"] > 70

    def test_high_valuation(self):
        result = score_fundamental(pe_percentile=90, pb_percentile=90)
        assert result["score"] < 50

    def test_high_roe(self):
        result = score_fundamental(roe=25)
        assert result["score"] >= 80

    def test_low_roe(self):
        result = score_fundamental(roe=5)
        assert result["score"] < 50

    def test_high_growth(self):
        result = score_fundamental(revenue_growth=30, earnings_growth=30)
        assert result["score"] >= 80

    def test_negative_growth(self):
        result = score_fundamental(revenue_growth=-20)
        assert result["score"] < 30

    def test_missing_data(self):
        result = score_fundamental()
        assert result["score"] == 50.0

    def test_dimensions(self):
        result = score_fundamental(pe_percentile=20, roe=20)
        assert "indicators" in result


class TestCapital:
    """Test capital flow scoring"""

    def test_positive_institutional_change(self):
        result = score_capital(institutional_holding_change=10)
        assert result["score"] >= 80

    def test_negative_institutional_change(self):
        result = score_capital(institutional_holding_change=-10)
        assert result["score"] < 30

    def test_positive_northbound_flow(self):
        result = score_capital(northbound_flow_20d=10)
        assert result["score"] >= 80

    def test_negative_northbound_flow(self):
        result = score_capital(northbound_flow_20d=-10)
        assert result["score"] < 30

    def test_missing_data(self):
        result = score_capital()
        assert result["score"] == 50.0

    def test_dimensions(self):
        result = score_capital(
            institutional_holding_change=5,
            northbound_flow_20d=2,
        )
        assert "indicators" in result
        assert len(result["indicators"]) >= 2


class TestTechnical:
    """Test technical analysis scoring"""

    def test_bullish_alignment(self):
        result = score_technical(ma_alignment="bullish")
        assert result["score"] >= 70

    def test_bearish_alignment(self):
        result = score_technical(ma_alignment="bearish")
        assert result["score"] < 50

    def test_price_above_ma250(self):
        result = score_technical(price_vs_ma250=30)
        assert result["score"] >= 70

    def test_price_below_ma250(self):
        result = score_technical(price_vs_ma250=-30)
        assert result["score"] < 50

    def test_near_high(self):
        result = score_technical(distance_from_high=5)
        assert result["score"] >= 70

    def test_far_from_high(self):
        result = score_technical(distance_from_high=60)
        assert result["score"] < 30

    def test_missing_data(self):
        result = score_technical()
        assert result["score"] == 50.0


class TestSentiment:
    """Test sentiment scoring"""

    def test_buy_consensus(self):
        result = score_sentiment(analyst_consensus="buy", target_price_upside=30)
        assert result["score"] >= 80

    def test_sell_consensus(self):
        result = score_sentiment(analyst_consensus="sell", target_price_upside=-10)
        assert result["score"] < 30

    def test_positive_news(self):
        result = score_sentiment(news_sentiment="positive")
        assert result["score"] >= 60

    def test_negative_news(self):
        result = score_sentiment(news_sentiment="negative")
        assert result["score"] < 50

    def test_market_underestimating(self):
        result = score_sentiment(cognitive_difference="market_underestimating")
        assert result["score"] >= 70

    def test_market_overestimating(self):
        result = score_sentiment(cognitive_difference="market_overestimating")
        assert result["score"] < 50

    def test_missing_data(self):
        result = score_sentiment()
        assert result["score"] == 50.0


class TestMacro:
    """Test macro scoring"""

    def test_accommodative_policy(self):
        result = score_macro(monetary_policy="accommodative")
        assert result["score"] >= 70

    def test_tight_policy(self):
        result = score_macro(monetary_policy="tight")
        assert result["score"] < 50

    def test_abundant_liquidity(self):
        result = score_macro(liquidity_indicator="abundant")
        assert result["score"] >= 70

    def test_scarce_liquidity(self):
        result = score_macro(liquidity_indicator="scarce")
        assert result["score"] < 50

    def test_supportive_sector_policy(self):
        result = score_macro(sector_policy="supportive")
        assert result["score"] >= 70

    def test_restrictive_sector_policy(self):
        result = score_macro(sector_policy="restrictive")
        assert result["score"] < 50

    def test_minimal_us_china_impact(self):
        result = score_macro(us_china_impact="minimal")
        assert result["score"] >= 70

    def test_severe_us_china_impact(self):
        result = score_macro(us_china_impact="severe")
        assert result["score"] < 40

    def test_missing_data(self):
        result = score_macro()
        assert result["score"] == 50.0
