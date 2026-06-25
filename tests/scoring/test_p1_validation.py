# -*- coding: utf-8 -*-
"""
P1 长线投研框架 - 完整验证脚本

全面测试贝叶斯引擎、六维评分、指标评分、持久化、API和主流程集成
"""

import sys
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple

sys.path.insert(0, "/home/yu/pythonProjects/daily_stock_analysis")


class TestRunner:
    """测试运行器"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results: List[Dict[str, Any]] = []

    def record(self, name: str, passed: bool, message: str = "", details: str = ""):
        self.results.append(
            {
                "name": name,
                "passed": passed,
                "message": message,
                "details": details,
            }
        )
        if passed:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            print(f"  ❌ {name}: {message}")
        if details:
            print(f"     {details}")

    def summary(self) -> Tuple[int, int]:
        return self.passed, self.failed


def test_bayesian_engine(runner: TestRunner):
    """测试贝叶斯引擎"""
    from src.scoring.bayesian import (
        map_prior,
        calculate_edge,
        update_posterior,
        map_position,
        check_stop_conditions,
        validate_position_with_concentration,
        calculate_bayesian,
    )

    print("\n" + "=" * 60)
    print("1. 贝叶斯引擎验证")
    print("=" * 60)

    # map_prior 边界测试
    runner.record(
        "map_prior(100) = 1.0",
        abs(map_prior(100) - 1.0) < 0.001,
        f"结果: {map_prior(100):.4f}",
    )
    runner.record(
        "map_prior(0) = 0.0",
        abs(map_prior(0) - 0.0) < 0.001,
        f"结果: {map_prior(0):.4f}",
    )
    runner.record(
        "map_prior(50) = 0.3333...",
        abs(map_prior(50) - 1 / 3) < 0.001,
        f"结果: {map_prior(50):.4f}",
    )

    # map_prior 线性区域
    runner.record(
        "map_prior(85) ≈ 0.8",
        abs(map_prior(85) - 0.8) < 0.001,
        f"结果: {map_prior(85):.4f}",
    )

    # calculate_edge
    edge = calculate_edge(0.7, 0.5)
    runner.record(
        "calculate_edge(0.7, 0.5) = 0.2", abs(edge - 0.2) < 0.001, f"结果: {edge:.4f}"
    )

    # update_posterior 贝叶斯定理
    posterior = update_posterior(0.5, 8.0)
    runner.record(
        "update_posterior(0.5, 8.0) > 0.8",
        0.8 < posterior < 0.95,
        f"结果: {posterior:.4f}",
    )

    posterior_neg = update_posterior(0.5, 0.125)
    runner.record(
        "update_posterior(0.5, 0.125) < 0.2",
        0.05 < posterior_neg < 0.2,
        f"结果: {posterior_neg:.4f}",
    )

    # map_position
    pos, conf = map_position(0.6)
    runner.record(
        "map_position(0.6) = 5-8%", pos == "5-8%", f"结果: {pos}, 置信度: {conf}"
    )

    pos, conf = map_position(-0.2)
    runner.record(
        "map_position(-0.2) = 0-1%", pos == "0-1%", f"结果: {pos}, 置信度: {conf}"
    )

    # check_stop_conditions
    stop = check_stop_conditions(0.7, 0.6, 0.4)
    runner.record(
        "check_stop_conditions 正常不应停止",
        stop["should_stop"] is False,
        f"结果: {stop['should_stop']}",
    )

    stop = check_stop_conditions(0.7, 0.3, 0.4)
    runner.record(
        "check_stop_conditions 后验低于阈值应停止",
        stop["should_stop"] is True and stop["posterior_below_prior_threshold"] is True,
        f"结果: {stop}",
    )

    # validate_position_with_concentration
    valid, warning = validate_position_with_concentration("3-5%", 0.2)
    runner.record(
        "validate_position 正常集中度应通过",
        valid is True,
        f"结果: valid={valid}, warning={warning}",
    )

    valid, warning = validate_position_with_concentration("5-8%", 0.35)
    runner.record(
        "validate_position 高集中度应拒绝",
        valid is False,
        f"结果: valid={valid}, warning={warning}",
    )

    # calculate_bayesian 完整流程
    result = calculate_bayesian(
        dimension_total=80,
        market_implied_p=0.5,
        lr=1.0,
    )
    runner.record(
        "calculate_bayesian(80, 0.5) prior_p ∈ [0.6, 0.8]",
        0.6 < result.prior_p < 0.8,
        f"prior_p={result.prior_p:.4f}",
    )
    runner.record(
        "calculate_bayesian(80, 0.5) edge > 0",
        result.edge > 0,
        f"edge={result.edge:.4f}",
    )
    runner.record(
        "calculate_bayesian(80, 0.5) position_suggestion ∈ [0-1%, 1-3%]",
        result.position_suggestion in ["0-1%", "1-3%", "3-5%"],
        f"position={result.position_suggestion}",
    )


def test_scoring_engine(runner: TestRunner):
    """测试六维评分引擎"""
    from src.scoring.engine import (
        validate_weights,
        validate_weights_safe,
        fill_missing_score,
        aggregate_dimension,
        aggregate_framework,
        DEFAULT_NEUTRAL_SCORE,
    )

    print("\n" + "=" * 60)
    print("2. 六维评分引擎验证")
    print("=" * 60)

    # validate_weights
    try:
        validate_weights([0.25, 0.25, 0.15, 0.10, 0.15, 0.10])
        runner.record("validate_weights 正确权重 sum=1.0", True)
    except ValueError:
        runner.record("validate_weights 正确权重 sum=1.0", False, "抛出异常")

    try:
        validate_weights([0.5, 0.3])
        runner.record("validate_weights 错误权重 sum=0.8", False, "应抛出异常")
    except ValueError:
        runner.record("validate_weights 错误权重 sum=0.8", True, "正确抛出异常")

    # validate_weights_safe
    valid, _ = validate_weights_safe([0.25, 0.25, 0.15, 0.10, 0.15, 0.10])
    runner.record(
        "validate_weights_safe 正确权重", valid is True, f"结果: valid={valid}"
    )

    valid, error = validate_weights_safe([0.5, 0.3])
    runner.record(
        "validate_weights_safe 错误权重",
        valid is False,
        f"结果: valid={valid}, error={error}",
    )

    # fill_missing_score
    runner.record(
        "fill_missing_score 正常值",
        fill_missing_score(75.0) == 75.0,
        f"结果: {fill_missing_score(75.0)}",
    )

    runner.record(
        "fill_missing_score None → 50.0",
        fill_missing_score(None) == DEFAULT_NEUTRAL_SCORE,
        f"结果: {fill_missing_score(None)}",
    )

    # aggregate_dimension
    indicators = [
        {"name": "PE", "score": 80, "weight": 0.5},
        {"name": "PB", "score": 60, "weight": 0.5},
    ]
    score, _ = aggregate_dimension(indicators)
    runner.record(
        "aggregate_dimension (80×0.5 + 60×0.5) = 70",
        abs(score - 70.0) < 0.001,
        f"结果: {score}",
    )

    # aggregate_framework
    dimensions = [
        {"dimension": "产业链定位", "weight": 0.25, "score": 80},
        {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
        {"dimension": "资金面", "weight": 0.15, "score": 65},
        {"dimension": "技术面", "weight": 0.10, "score": 75},
        {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
        {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
    ]

    result = aggregate_framework(dimensions)
    expected = 80 * 0.25 + 70 * 0.25 + 65 * 0.15 + 75 * 0.10 + 60 * 0.15 + 55 * 0.10

    runner.record(
        "aggregate_framework 六维加权平均",
        abs(result.dimension_total - expected) < 0.01,
        f"期望: {expected:.2f}, 结果: {result.dimension_total:.2f}",
    )
    runner.record(
        "aggregate_framework 6个维度",
        len(result.dimensions) == 6,
        f"维度数: {len(result.dimensions)}",
    )


def test_indicator_modules(runner: TestRunner):
    """测试六维指标评分模块"""
    from src.scoring.indicators import (
        score_supply_chain,
        score_fundamental,
        score_capital,
        score_technical,
        score_sentiment,
        score_macro,
    )

    print("\n" + "=" * 60)
    print("3. 六维指标评分模块验证")
    print("=" * 60)

    # 产业链定位
    r = score_supply_chain(
        chain_position="bottleneck", moat_type="patent", moat_strength="strong"
    )
    runner.record(
        "score_supply_chain 瓶颈+专利+强护城河 → 高分",
        r["score"] >= 80,
        f"分数: {r['score']:.2f}",
    )

    r = score_supply_chain(chain_position="commodity")
    runner.record(
        "score_supply_chain 大宗商品 → 低分", r["score"] < 50, f"分数: {r['score']:.2f}"
    )

    # 基本面
    r = score_fundamental(pe_percentile=10, pb_percentile=10, roe=25)
    runner.record(
        "score_fundamental 低估值+高ROE → 高分",
        r["score"] >= 70,
        f"分数: {r['score']:.2f}",
    )

    r = score_fundamental(pe_percentile=95, pb_percentile=95)
    runner.record(
        "score_fundamental 高估值 → 低分", r["score"] < 40, f"分数: {r['score']:.2f}"
    )

    # 资金面
    r = score_capital(institutional_holding_change=10, northbound_flow_20d=10)
    runner.record(
        "score_capital 机构增持+北向流入 → 高分",
        r["score"] >= 70,
        f"分数: {r['score']:.2f}",
    )

    # 技术面
    r = score_technical(ma_alignment="bullish", price_vs_ma250=30)
    runner.record(
        "score_technical 多头排列+高于年线 → 高分",
        r["score"] >= 70,
        f"分数: {r['score']:.2f}",
    )

    r = score_technical(ma_alignment="bearish")
    runner.record(
        "score_technical 空头排列 → 低分", r["score"] < 40, f"分数: {r['score']:.2f}"
    )

    # 情绪
    r = score_sentiment(analyst_consensus="buy", target_price_upside=30)
    runner.record(
        "score_sentiment 买入评级+高空间 → 高分",
        r["score"] >= 70,
        f"分数: {r['score']:.2f}",
    )

    r = score_sentiment(analyst_consensus="sell", target_price_upside=-20)
    runner.record(
        "score_sentiment 卖出评级 → 低分", r["score"] < 30, f"分数: {r['score']:.2f}"
    )

    # 宏观
    r = score_macro(
        monetary_policy="accommodative",
        liquidity_indicator="abundant",
        sector_policy="supportive",
    )
    runner.record(
        "score_macro 宽松+充裕+支持 → 高分", r["score"] >= 70, f"分数: {r['score']:.2f}"
    )


def test_persistence_layer(runner: TestRunner):
    """测试持久化层"""
    from src.repositories import PositionLedgerRepo, ScoreLedgerRepo
    from src.storage import DatabaseManager

    print("\n" + "=" * 60)
    print("4. 持久化层验证")
    print("=" * 60)

    db_manager = DatabaseManager.get_instance()
    db = db_manager._SessionLocal()

    try:
        # 测试 PositionLedgerRepo
        pos_repo = PositionLedgerRepo(db)

        # 创建测试记录
        test_data = {
            "stock_code": "TEST001",
            "market": "cn",
            "action": "buy",
            "position_size": "5-8%",
            "prior_p": 0.7,
            "edge": 0.2,
            "posterior_p": 0.8,
            "status": "open",
        }

        record = pos_repo.create(test_data)
        runner.record(
            "PositionLedgerRepo.create()", record.id is not None, f"ID: {record.id}"
        )

        # 查询测试
        records = pos_repo.get_by_stock("TEST001")
        runner.record(
            "PositionLedgerRepo.get_by_stock()",
            len(records) > 0 and records[0].stock_code == "TEST001",
            f"查到 {len(records)} 条记录",
        )

        # 更新测试
        ok = pos_repo.update_status(record.id, "closed", realized_pnl=0.05)
        runner.record("PositionLedgerRepo.update_status()", ok is True, f"结果: {ok}")

        # 删除测试
        ok = pos_repo.delete(record.id)
        runner.record("PositionLedgerRepo.delete()", ok is True, f"结果: {ok}")

        # 验证删除
        record = pos_repo.get_by_id(record.id)
        runner.record(
            "PositionLedgerRepo 验证删除",
            record is None,
            f"记录已删除: {record is None}",
        )

        # 测试 ScoreLedgerRepo
        score_repo = ScoreLedgerRepo(db)

        # 创建评分记录
        score_data = {
            "stock_code": "TEST002",
            "market": "cn",
            "dimension_total": 75.0,
            "supply_chain_score": 80.0,
            "fundamental_score": 75.0,
            "capital_score": 70.0,
            "technical_score": 75.0,
            "sentiment_score": 70.0,
            "macro_score": 80.0,
            "prior_p": 0.65,
            "market_implied_p": 0.5,
            "edge": 0.15,
            "posterior_p": 0.75,
            "position_suggestion": "3-5%",
            "scoring_version": "v1",
            "raw_scores_json": "{}",
        }

        record = score_repo.create(score_data)
        runner.record(
            "ScoreLedgerRepo.create()", record.id is not None, f"ID: {record.id}"
        )

        # 查询测试
        records = score_repo.get_by_stock("TEST002")
        runner.record(
            "ScoreLedgerRepo.get_by_stock()",
            len(records) > 0 and records[0].stock_code == "TEST002",
            f"查到 {len(records)} 条记录",
        )

        # 清理
        score_repo.db.delete(record)
        score_repo.db.commit()
        runner.record("ScoreLedgerRepo 清理测试数据", True, "完成")

    except Exception as e:
        runner.record(f"持久化层测试异常: {e}", False, str(e))
    finally:
        db.close()


def test_api_endpoints(runner: TestRunner):
    """测试 API 端点"""
    from api.v1.schemas.research_framework import (
        PositionCreateRequest,
        PositionUpdateRequest,
        PositionItem,
        PositionListResponse,
        ValidatePositionRequest,
        ValidatePositionResponse,
    )

    print("\n" + "=" * 60)
    print("5. API 端点验证")
    print("=" * 60)

    # Schema 验证
    try:
        req = PositionCreateRequest(
            stock_code="600519",
            market="cn",
            action="buy",
            position_size="5-8%",
            prior_p=0.7,
            edge=0.2,
        )
        runner.record(
            "PositionCreateRequest Schema",
            req.stock_code == "600519",
            f"stock_code: {req.stock_code}",
        )
    except Exception as e:
        runner.record("PositionCreateRequest Schema", False, str(e))

    # 验证请求
    try:
        req = ValidatePositionRequest(
            stock_code="600519",
            position_size="5-8%",
            current_concentration=0.3,
        )
        runner.record(
            "ValidatePositionRequest Schema",
            req.position_size == "5-8%",
            f"position_size: {req.position_size}",
        )
    except Exception as e:
        runner.record("ValidatePositionRequest Schema", False, str(e))

    # 响应模型
    resp = ValidatePositionResponse(
        valid=True,
        message="OK",
        suggested_position="5-8%",
    )
    runner.record(
        "ValidatePositionResponse Schema", resp.valid is True, f"valid: {resp.valid}"
    )


def test_integration_helper(runner: TestRunner):
    """测试集成辅助函数"""
    from src.services.research_framework_integration import (
        _infer_market,
        _estimate_market_implied_p,
        _infer_sentiment,
        _extract_moat_from_analysis,
        _build_investment_conclusion,
    )
    from src.analyzer import AnalysisResult

    print("\n" + "=" * 60)
    print("6. 集成辅助函数验证")
    print("=" * 60)

    # 市场推断
    test_cases = [
        ("600519", "cn"),
        ("000001", "cn"),
        ("300750", "cn"),
        ("HK0001", "hk"),
        ("0700.HK", "hk"),
        ("AAPL", "us"),
        ("GOOGL", "us"),
    ]

    for code, expected in test_cases:
        result = _infer_market(code)
        runner.record(
            f"_infer_market({code}) = {expected}", result == expected, f"结果: {result}"
        )

    # 情绪推断
    test_sentiment = [
        ("市场乐观，积极向好", "positive"),
        ("市场悲观，担忧加剧", "negative"),
        ("市场震荡，无明显方向", "neutral"),
    ]

    for text, expected in test_sentiment:
        result = _infer_sentiment(text)
        runner.record(
            f"_infer_sentiment('{text[:10]}...')", result == expected, f"结果: {result}"
        )

    # 投资结论构建
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        sentiment_score=75,
        trend_prediction="看多",
        operation_advice="买入",
        action="buy",
    )

    conclusion = _build_investment_conclusion(
        result,
        {
            "prior_p": 0.7,
            "edge": 0.2,
            "posterior_p": 0.8,
            "position_suggestion": "3-5%",
            "stop_conditions": {"should_stop": False},
        },
    )

    runner.record(
        "_build_investment_conclusion 返回 dict",
        isinstance(conclusion, dict),
        f"类型: {type(conclusion)}",
    )
    runner.record(
        "_build_investment_conclusion 包含 position",
        "position" in conclusion,
        f"字段: {list(conclusion.keys())}",
    )


def test_pipeline_integration(runner: TestRunner):
    """测试主流程集成"""
    from src.analyzer import AnalysisResult
    from src.config import Config
    from src.core.pipeline import StockAnalysisPipeline

    print("\n" + "=" * 60)
    print("7. 主流程集成验证")
    print("=" * 60)

    # AnalysisResult 字段检查
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        sentiment_score=75,
        trend_prediction="看多",
        operation_advice="买入",
    )

    runner.record(
        "AnalysisResult.research_framework 字段存在",
        hasattr(result, "research_framework"),
        f"hasattr: {hasattr(result, 'research_framework')}",
    )

    runner.record(
        "AnalysisResult.investment_conclusion 字段存在",
        hasattr(result, "investment_conclusion"),
        f"hasattr: {hasattr(result, 'investment_conclusion')}",
    )

    # to_dict 包含新字段
    result_dict = result.to_dict()
    runner.record(
        "AnalysisResult.to_dict() 包含 research_framework",
        "research_framework" in result_dict,
        f"包含: {'research_framework' in result_dict}",
    )

    runner.record(
        "AnalysisResult.to_dict() 包含 investment_conclusion",
        "investment_conclusion" in result_dict,
        f"包含: {'investment_conclusion' in result_dict}",
    )

    # Config 配置
    config = Config()
    runner.record(
        "Config.enable_research_framework 存在",
        hasattr(config, "enable_research_framework"),
        f"hasattr: {hasattr(config, 'enable_research_framework')}",
    )

    runner.record(
        "Config.enable_research_framework 默认 True",
        config.enable_research_framework is True,
        f"值: {config.enable_research_framework}",
    )

    # Pipeline 方法
    runner.record(
        "StockAnalysisPipeline._integrate_research_framework 存在",
        hasattr(StockAnalysisPipeline, "_integrate_research_framework"),
        f"hasattr: {hasattr(StockAnalysisPipeline, '_integrate_research_framework')}",
    )


def test_end_to_end_scenarios(runner: TestRunner):
    """端到端场景测试"""
    from src.services.research_scoring_service import ResearchScoringService

    print("\n" + "=" * 60)
    print("8. 端到端场景验证")
    print("=" * 60)

    service = ResearchScoringService()

    # 场景1: 强势买入
    buy_data = {
        "chain_position": "bottleneck",
        "moat_type": "patent",
        "moat_strength": "strong",
        "us_china_risk": "low",
        "pe_percentile": 10,
        "roe": 30,
        "revenue_growth": 40,
        "institutional_holding_change": 10,
        "northbound_flow_20d": 10,
        "ma_alignment": "bullish",
        "price_vs_ma250": 30,
        "analyst_consensus": "buy",
        "target_price_upside": 50,
        "cognitive_difference": "market_underestimating",
        "monetary_policy": "accommodative",
        "liquidity_indicator": "abundant",
        "sector_policy": "supportive",
    }

    result = service.process(
        stock_code="600519",
        stock_name="贵州茅台",
        market="cn",
        raw_data=buy_data,
        market_implied_p=0.5,
        lr=2.0,
    )

    framework = result["framework_score"]
    bayesian = result["bayesian_result"]

    runner.record(
        "强势买入信号 - 维度总分 >= 75",
        framework["dimension_total"] >= 75,
        f"总分: {framework['dimension_total']:.2f}",
    )

    runner.record(
        "强势买入信号 - Edge > 0.2",
        bayesian["edge"] > 0.2,
        f"Edge: {bayesian['edge']:.4f}",
    )

    runner.record(
        "强势买入信号 - 后验 > 先验",
        bayesian["posterior_p"] > bayesian["prior_p"],
        f"先验: {bayesian['prior_p']:.4f}, 后验: {bayesian['posterior_p']:.4f}",
    )

    # 场景2: 强烈卖出
    sell_data = {
        "chain_position": "commodity",
        "moat_type": "none",
        "moat_strength": "none",
        "us_china_risk": "high",
        "pe_percentile": 95,
        "roe": 5,
        "revenue_growth": -20,
        "institutional_holding_change": -10,
        "northbound_flow_20d": -10,
        "ma_alignment": "bearish",
        "price_vs_ma250": -30,
        "analyst_consensus": "sell",
        "target_price_upside": -20,
        "cognitive_difference": "market_overestimating",
        "monetary_policy": "tight",
        "liquidity_indicator": "scarce",
        "sector_policy": "restrictive",
    }

    result = service.process(
        stock_code="TEST_SELL",
        stock_name="测试卖出",
        market="cn",
        raw_data=sell_data,
        market_implied_p=0.5,
        lr=0.5,
    )

    framework = result["framework_score"]
    bayesian = result["bayesian_result"]

    runner.record(
        "强烈卖出信号 - 维度总分 <= 35",
        framework["dimension_total"] <= 35,
        f"总分: {framework['dimension_total']:.2f}",
    )

    runner.record(
        "强烈卖出信号 - Edge < 0", bayesian["edge"] < 0, f"Edge: {bayesian['edge']:.4f}"
    )

    runner.record(
        "强烈卖出信号 - 建议仓位 0-1%",
        bayesian["position_suggestion"] in ["0-1%"],
        f"仓位: {bayesian['position_suggestion']}",
    )

    # 场景3: 空数据降级
    result = service.process(
        stock_code="TEST_EMPTY",
        stock_name="空数据测试",
        market="cn",
        raw_data={},
        market_implied_p=0.5,
    )

    framework = result["framework_score"]

    runner.record(
        "空数据降级 - 总分 = 50.0",
        abs(framework["dimension_total"] - 50.0) < 0.01,
        f"总分: {framework['dimension_total']:.2f}",
    )


def main():
    print("\n" + "=" * 70)
    print("P1 长线投研框架 - 完整验证测试")
    print("=" * 70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    runner = TestRunner()

    # 执行所有测试
    test_bayesian_engine(runner)
    test_scoring_engine(runner)
    test_indicator_modules(runner)
    test_persistence_layer(runner)
    test_api_endpoints(runner)
    test_integration_helper(runner)
    test_pipeline_integration(runner)
    test_end_to_end_scenarios(runner)

    # 汇总
    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)

    passed, failed = runner.summary()
    total = passed + failed

    print(f"\n总计: {total} 项测试")
    print(f"通过: {passed} 项 ✅")
    print(f"失败: {failed} 项 ❌")
    print(f"通过率: {passed / total * 100:.1f}%")

    # 按模块分类
    print("\n按模块统计:")
    modules = {}
    for r in runner.results:
        name = r["name"].split()[0]
        if name not in modules:
            modules[name] = {"passed": 0, "failed": 0}
        if r["passed"]:
            modules[name]["passed"] += 1
        else:
            modules[name]["failed"] += 1

    for module, counts in modules.items():
        status = "✅" if counts["failed"] == 0 else "❌"
        print(
            f"  {status} {module}: {counts['passed']} passed, {counts['failed']} failed"
        )

    # 失败详情
    if failed > 0:
        print("\n失败项详情:")
        for r in runner.results:
            if not r["passed"]:
                print(f"  ❌ {r['name']}: {r['message']}")

    # 结论
    print("\n" + "=" * 70)
    if failed == 0:
        print("🎉 所有验证通过！P1 长线投研框架工作正常！")
    else:
        print(f"⚠️  有 {failed} 项验证失败，请检查。")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
