# -*- coding: utf-8 -*-
"""
Tests for research scoring service.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestResearchScoringService:
    """Test ResearchScoringService"""

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_process_basic(self, mock_db_manager):
        """Test basic processing with mock DB"""
        from src.services.research_scoring_service import ResearchScoringService

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        raw_data = {
            "pe_percentile": 20,
            "pb_percentile": 20,
            "roe": 20,
            "revenue_growth": 15,
            "ma_alignment": "bullish",
            "analyst_consensus": "buy",
            "target_price_upside": 30,
        }

        result = service.process(
            stock_code="600519",
            stock_name="贵州茅台",
            market="cn",
            raw_data=raw_data,
        )

        assert "framework_score" in result
        assert "bayesian_result" in result
        assert "ledger_record" in result or result["ledger_record"] is None

        framework = result["framework_score"]
        assert "dimension_total" in framework
        assert "dimensions" in framework

        bayesian = result["bayesian_result"]
        assert "prior_p" in bayesian
        assert "edge" in bayesian
        assert "position_suggestion" in bayesian

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_process_with_market_implied(self, mock_db_manager):
        """Test with custom market implied probability"""
        from src.services.research_scoring_service import ResearchScoringService

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        result = service.process(
            stock_code="600519",
            stock_name="贵州茅台",
            raw_data={"pe_percentile": 10, "roe": 25},
            market_implied_p=0.3,
        )

        bayesian = result["bayesian_result"]
        assert abs(bayesian["market_implied_p"] - 0.3) < 0.001

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_process_with_strong_negative_evidence(self, mock_db_manager):
        """Test with strong negative evidence"""
        from src.services.research_scoring_service import ResearchScoringService

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        result = service.process(
            stock_code="600519",
            stock_name="贵州茅台",
            raw_data={"pe_percentile": 30},
            strong_negative_evidence=True,
        )

        bayesian = result["bayesian_result"]
        assert "stop_conditions" in bayesian
        assert bayesian["stop_conditions"]["strong_negative_evidence"] is True

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_process_dimension_scores(self, mock_db_manager):
        """Test that dimension scores are correctly calculated"""
        from src.services.research_scoring_service import ResearchScoringService

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        result = service.process(
            stock_code="600519",
            stock_name="贵州茅台",
            raw_data={
                "chain_position": "bottleneck",
                "moat_type": "patent",
                "moat_strength": "strong",
                "pe_percentile": 15,
                "roe": 25,
                "institutional_holding_change": 5,
                "northbound_flow_20d": 3,
                "ma_alignment": "bullish",
                "price_vs_ma250": 20,
                "analyst_consensus": "buy",
                "target_price_upside": 25,
            },
        )

        framework = result["framework_score"]
        dimensions = {d["dimension"]: d["score"] for d in framework["dimensions"]}

        assert "产业链定位" in dimensions
        assert "基本面与价值" in dimensions
        assert "资金面" in dimensions
        assert "技术面" in dimensions
        assert "情绪与认知差" in dimensions
        assert "宏观与地缘" in dimensions

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_process_empty_data(self, mock_db_manager):
        """Test processing with empty data"""
        from src.services.research_scoring_service import ResearchScoringService

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        result = service.process(
            stock_code="600519",
            stock_name="贵州茅台",
            raw_data={},
        )

        framework = result["framework_score"]
        assert framework["dimension_total"] == 50.0

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_framework_to_dict(self, mock_db_manager):
        """Test framework conversion to dict"""
        from src.services.research_scoring_service import ResearchScoringService
        from src.scoring import aggregate_framework

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        dimensions = [
            {"dimension": "产业链定位", "weight": 0.25, "score": 80},
            {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
            {"dimension": "资金面", "weight": 0.15, "score": 65},
            {"dimension": "技术面", "weight": 0.10, "score": 75},
            {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
            {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
        ]
        framework = aggregate_framework(dimensions)
        framework_dict = service._framework_to_dict(framework)

        assert "dimension_total" in framework_dict
        assert "dimensions" in framework_dict
        assert len(framework_dict["dimensions"]) == 6

    @patch("src.services.research_scoring_service.DatabaseManager")
    def test_bayesian_to_dict(self, mock_db_manager):
        """Test Bayesian result conversion to dict"""
        from src.services.research_scoring_service import ResearchScoringService
        from src.scoring import calculate_bayesian

        mock_db = MagicMock()
        mock_db_manager.get_instance.return_value._SessionLocal.return_value = mock_db

        service = ResearchScoringService()

        bayesian = calculate_bayesian(dimension_total=70, market_implied_p=0.5)
        bayesian_dict = service._bayesian_to_dict(bayesian)

        assert "prior_p" in bayesian_dict
        assert "market_implied_p" in bayesian_dict
        assert "edge" in bayesian_dict
        assert "posterior_p" in bayesian_dict
        assert "position_suggestion" in bayesian_dict
        assert "stop_conditions" in bayesian_dict


class TestIntegrationHelper:
    """Test integration helper functions"""

    def test_infer_market_cn(self):
        from src.services.research_framework_integration import _infer_market

        assert _infer_market("600519") == "cn"
        assert _infer_market("000001") == "cn"
        assert _infer_market("688001") == "cn"

    def test_infer_market_hk(self):
        from src.services.research_framework_integration import _infer_market

        assert _infer_market("HK0001") == "hk"
        assert _infer_market("00700") == "hk"

    def test_infer_market_us(self):
        from src.services.research_framework_integration import _infer_market

        assert _infer_market("AAPL") == "us"
        assert _infer_market("GOOGL") == "us"

    def test_estimate_market_implied_p_buy(self):
        from src.services.research_framework_integration import (
            _estimate_market_implied_p,
        )
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=75,
            trend_prediction="看多",
            operation_advice="买入",
            decision_type="buy",
        )

        implied = _estimate_market_implied_p(result)
        assert implied > 0.75

    def test_estimate_market_implied_p_hold(self):
        from src.services.research_framework_integration import (
            _estimate_market_implied_p,
        )
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=50,
            trend_prediction="震荡",
            operation_advice="持有",
            decision_type="hold",
        )

        implied = _estimate_market_implied_p(result)
        assert abs(implied - 0.5) < 0.1

    def test_estimate_market_implied_p_sell(self):
        from src.services.research_framework_integration import (
            _estimate_market_implied_p,
        )
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=30,
            trend_prediction="看空",
            operation_advice="卖出",
            decision_type="sell",
        )

        implied = _estimate_market_implied_p(result)
        assert implied < 0.4

    def test_infer_sentiment_positive(self):
        from src.services.research_framework_integration import _infer_sentiment

        assert _infer_sentiment("市场情绪乐观") == "positive"
        assert _infer_sentiment("投资者看好后市") == "positive"

    def test_infer_sentiment_negative(self):
        from src.services.research_framework_integration import _infer_sentiment

        assert _infer_sentiment("市场情绪悲观") == "negative"
        assert _infer_sentiment("投资者担忧风险") == "negative"

    def test_infer_sentiment_neutral(self):
        from src.services.research_framework_integration import _infer_sentiment

        assert _infer_sentiment("市场情绪平稳") == "neutral"

    def test_extract_moat_from_analysis(self):
        from src.services.research_framework_integration import (
            _extract_moat_from_analysis,
        )

        text = "公司具有强大的技术壁垒和专利护城河"
        result = _extract_moat_from_analysis(text)
        assert "strong" in result.lower() or "专利" in result or "壁垒" in result

    def test_build_investment_conclusion(self):
        from src.services.research_framework_integration import (
            _build_investment_conclusion,
        )
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=75,
            trend_prediction="看多",
            operation_advice="买入",
            analysis_summary="公司基本面优秀",
            decision_type="buy",
        )

        bayesian = {
            "prior_p": 0.7,
            "market_implied_p": 0.5,
            "edge": 0.2,
            "posterior_p": 0.75,
            "position_suggestion": "3-5%",
        }

        conclusion = _build_investment_conclusion(result, bayesian)

        assert "action" in conclusion
        assert "position" in conclusion
        assert conclusion["edge"] == 0.2
        assert conclusion["prior_p"] == 0.7
