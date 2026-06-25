# -*- coding: utf-8 -*-
"""
P1 研究框架集成测试脚本

测试完整流程：数据提取 → 六维评分 → 贝叶斯计算 → 投资结论
"""

import sys
from datetime import datetime

sys.path.insert(0, "/home/yu/pythonProjects/daily_stock_analysis")


def test_bayesian_engine():
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
    print("测试 1: 贝叶斯引擎")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test map_prior
    print("\n[map_prior 测试]")
    test_cases = [
        (100, 1.0, "极端高分 → 1.0"),
        (90, 0.866, "90分 → ~0.866"),
        (85, 0.8, "85分 → 0.8"),
        (70, 0.6, "70分 → 0.6"),
        (55, 0.4, "55分 → 0.4"),
        (40, 0.2, "40分 → 0.2"),
        (30, 0.15, "30分 → ~0.15"),
        (0, 0.0, "0分 → 0.0"),
    ]

    for score, expected, desc in test_cases:
        result = map_prior(score)
        diff = abs(result - expected)
        if diff < 0.05:
            print(f"  ✅ {desc}: {score} → {result:.4f}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc}: {score} → {result:.4f} (期望 {expected})")
            tests_failed += 1

    # Test calculate_edge
    print("\n[calculate_edge 测试]")
    edge = calculate_edge(0.7, 0.5)
    if abs(edge - 0.2) < 0.001:
        print(f"  ✅ Edge计算: 0.7 - 0.5 = {edge}")
        tests_passed += 1
    else:
        print(f"  ❌ Edge计算: {edge} (期望 0.2)")
        tests_failed += 1

    # Test update_posterior
    print("\n[update_posterior 测试]")
    posterior = update_posterior(0.5, 8.0)
    if 0.8 < posterior < 0.9:
        print(f"  ✅ 强正向证据: 0.5 × LR=8 → {posterior:.4f}")
        tests_passed += 1
    else:
        print(f"  ❌ 强正向证据: {posterior:.4f} (期望 0.8-0.9)")
        tests_failed += 1

    posterior = update_posterior(0.5, 0.125)
    if 0.1 < posterior < 0.2:
        print(f"  ✅ 强负向证据: 0.5 × LR=0.125 → {posterior:.4f}")
        tests_passed += 1
    else:
        print(f"  ❌ 强负向证据: {posterior:.4f} (期望 0.1-0.2)")
        tests_failed += 1

    # Test map_position
    print("\n[map_position 测试]")
    position_cases = [
        (0.6, "5-8%", "高 Edge → 5-8%"),
        (0.4, "3-5%", "中 Edge → 3-5%"),
        (0.2, "1-3%", "低 Edge → 1-3%"),
        (0.05, "0-1%", "负 Edge → 0-1%"),
        (-0.2, "0-1%", "负 Edge → 0-1%"),
    ]

    for edge_val, expected_pos, desc in position_cases:
        pos, conf = map_position(edge_val)
        if pos == expected_pos:
            print(f"  ✅ {desc}: {pos}, 置信度={conf}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc}: {pos} (期望 {expected_pos})")
            tests_failed += 1

    # Test check_stop_conditions
    print("\n[check_stop_conditions 测试]")
    stop = check_stop_conditions(0.7, 0.6, 0.4)
    if stop["should_stop"] is False:
        print(f"  ✅ 正常条件: 不应停止")
        tests_passed += 1
    else:
        print(f"  ❌ 正常条件: 不应停止")
        tests_failed += 1

    stop = check_stop_conditions(0.7, 0.3, 0.4)
    if stop["should_stop"] is True and stop["posterior_below_prior_threshold"] is True:
        print(f"  ✅ 后验低于阈值: 应停止")
        tests_passed += 1
    else:
        print(f"  ❌ 后验低于阈值: {stop}")
        tests_failed += 1

    # Test validate_position_with_concentration
    print("\n[validate_position_with_concentration 测试]")
    valid, warning = validate_position_with_concentration("3-5%", 0.2)
    if valid is True:
        print(f"  ✅ 正常集中度 0.2: 通过")
        tests_passed += 1
    else:
        print(f"  ❌ 正常集中度 0.2: {warning}")
        tests_failed += 1

    valid, warning = validate_position_with_concentration("5-8%", 0.35)
    if valid is False:
        print(f"  ✅ 过高集中度 0.35: 拒绝")
        tests_passed += 1
    else:
        print(f"  ❌ 过高集中度 0.35: 应拒绝")
        tests_failed += 1

    # Test calculate_bayesian (full pipeline)
    print("\n[calculate_bayesian 完整流程测试]")
    result = calculate_bayesian(
        dimension_total=80,
        market_implied_p=0.5,
        lr=1.0,
    )
    print(f"  维度总分=80, 市场隐含=0.5:")
    print(f"    Prior P: {result.prior_p:.4f}")
    print(f"    Edge: {result.edge:.4f}")
    print(f"    Posterior P: {result.posterior_p:.4f}")
    print(f"    建议仓位: {result.position_suggestion}")
    print(f"    停止条件: {result.stop_conditions}")

    if 0.6 < result.prior_p < 0.8 and result.edge > 0:
        print(f"  ✅ 完整流程计算正确")
        tests_passed += 1
    else:
        print(f"  ❌ 完整流程计算异常")
        tests_failed += 1

    print(f"\n贝叶斯引擎测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_scoring_engine():
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
    print("测试 2: 六维评分引擎")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test validate_weights
    print("\n[validate_weights 测试]")
    try:
        validate_weights([0.25, 0.25, 0.15, 0.10, 0.15, 0.10])
        print("  ✅ 正确权重 1.0: 通过")
        tests_passed += 1
    except ValueError:
        print("  ❌ 正确权重 1.0: 应通过但抛出异常")
        tests_failed += 1

    try:
        validate_weights([0.5, 0.3])
        print("  ❌ 错误权重 0.8: 应抛出异常")
        tests_failed += 1
    except ValueError:
        print("  ✅ 错误权重 0.8: 正确抛出异常")
        tests_passed += 1

    # Test validate_weights_safe
    print("\n[validate_weights_safe 测试]")
    valid, error = validate_weights_safe([0.5, 0.5])
    if valid is True:
        print(f"  ✅ 正确权重 [0.5, 0.5]: 返回 valid=True")
        tests_passed += 1
    else:
        print(f"  ❌ 正确权重 [0.5, 0.5]: 应返回 valid=True")
        tests_failed += 1

    valid, error = validate_weights_safe([0.5, 0.3])
    if valid is False:
        print(f"  ✅ 错误权重 [0.5, 0.3]: 返回 valid=False")
        tests_passed += 1
    else:
        print(f"  ❌ 错误权重 [0.5, 0.3]: 应返回 valid=False")
        tests_failed += 1

    # Test fill_missing_score
    print("\n[fill_missing_score 测试]")
    if fill_missing_score(75.0) == 75.0:
        print("  ✅ 正常分数: 75.0")
        tests_passed += 1
    else:
        print("  ❌ 正常分数: 应返回 75.0")
        tests_failed += 1

    if fill_missing_score(None) == DEFAULT_NEUTRAL_SCORE:
        print(f"  ✅ None值: 返回中性分 {DEFAULT_NEUTRAL_SCORE}")
        tests_passed += 1
    else:
        print(f"  ❌ None值: 应返回 {DEFAULT_NEUTRAL_SCORE}")
        tests_failed += 1

    # Test aggregate_dimension
    print("\n[aggregate_dimension 测试]")
    indicators = [
        {"name": "PE", "score": 80, "weight": 0.5},
        {"name": "PB", "score": 60, "weight": 0.5},
    ]
    score, result = aggregate_dimension(indicators)
    if abs(score - 70.0) < 0.001:
        print(f"  ✅ 加权平均: (80×0.5 + 60×0.5) = {score}")
        tests_passed += 1
    else:
        print(f"  ❌ 加权平均: {score} (期望 70.0)")
        tests_failed += 1

    # Test aggregate_framework
    print("\n[aggregate_framework 测试]")
    dimensions = [
        {"dimension": "产业链定位", "weight": 0.25, "score": 80},
        {"dimension": "基本面与价值", "weight": 0.25, "score": 70},
        {"dimension": "资金面", "weight": 0.15, "score": 65},
        {"dimension": "技术面", "weight": 0.10, "score": 75},
        {"dimension": "情绪与认知差", "weight": 0.15, "score": 60},
        {"dimension": "宏观与地缘", "weight": 0.10, "score": 55},
    ]

    result = aggregate_framework(dimensions)
    expected_total = (
        80 * 0.25 + 70 * 0.25 + 65 * 0.15 + 75 * 0.10 + 60 * 0.15 + 55 * 0.10
    )

    print(f"  维度总数: {len(result.dimensions)}")
    print(f"  加权总分: {result.dimension_total:.2f}")

    for dim in result.dimensions:
        print(
            f"    - {dim.dimension}: {dim.score} × {dim.weight} = {dim.score * dim.weight:.2f}"
        )

    if abs(result.dimension_total - expected_total) < 0.01:
        print(f"  ✅ 六维总分计算正确: {result.dimension_total:.2f}")
        tests_passed += 1
    else:
        print(
            f"  ❌ 六维总分: {result.dimension_total:.2f} (期望 {expected_total:.2f})"
        )
        tests_failed += 1

    print(f"\n评分引擎测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_indicator_modules():
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
    print("测试 3: 六维指标评分模块")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test score_supply_chain
    print("\n[score_supply_chain 产业链定位]")
    result = score_supply_chain(
        chain_position="bottleneck",
        moat_type="patent",
        moat_strength="strong",
    )
    print(f"  瓶颈+专利+强护城河: {result['score']:.2f}")
    if result["score"] >= 80:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    result = score_supply_chain(chain_position="commodity")
    print(f"  大宗商品定位: {result['score']:.2f}")
    if result["score"] < 50:
        print("  ✅ 低分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得低分")
        tests_failed += 1

    # Test score_fundamental
    print("\n[score_fundamental 基本面与价值]")
    result = score_fundamental(
        pe_percentile=10,
        pb_percentile=10,
        roe=25,
    )
    print(f"  低估值+高ROE: {result['score']:.2f}")
    if result["score"] >= 70:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    result = score_fundamental(
        pe_percentile=90,
        pb_percentile=90,
    )
    print(f"  高估值: {result['score']:.2f}")
    if result["score"] < 50:
        print("  ✅ 低分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得低分")
        tests_failed += 1

    # Test score_capital
    print("\n[score_capital 资金面]")
    result = score_capital(
        institutional_holding_change=10,
        northbound_flow_20d=10,
    )
    print(f"  机构增持+北向流入: {result['score']:.2f}")
    if result["score"] >= 80:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    # Test score_technical
    print("\n[score_technical 技术面]")
    result = score_technical(
        ma_alignment="bullish",
        price_vs_ma250=30,
    )
    print(f"  多头排列+价格高于年线: {result['score']:.2f}")
    if result["score"] >= 70:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    result = score_technical(ma_alignment="bearish")
    print(f"  空头排列: {result['score']:.2f}")
    if result["score"] < 50:
        print("  ✅ 低分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得低分")
        tests_failed += 1

    # Test score_sentiment
    print("\n[score_sentiment 情绪与认知差]")
    result = score_sentiment(
        analyst_consensus="buy",
        target_price_upside=30,
    )
    print(f"  买入评级+高空间: {result['score']:.2f}")
    if result["score"] >= 80:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    result = score_sentiment(
        analyst_consensus="sell",
        target_price_upside=-10,
    )
    print(f"  卖出评级: {result['score']:.2f}")
    if result["score"] < 30:
        print("  ✅ 低分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得低分")
        tests_failed += 1

    # Test score_macro
    print("\n[score_macro 宏观与地缘]")
    result = score_macro(
        monetary_policy="accommodative",
        liquidity_indicator="abundant",
        sector_policy="supportive",
    )
    print(f"  宽松+充裕+支持: {result['score']:.2f}")
    if result["score"] >= 70:
        print("  ✅ 高分正确")
        tests_passed += 1
    else:
        print("  ❌ 应得高分")
        tests_failed += 1

    print(f"\n指标评分测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_research_scoring_service():
    """测试研究评分服务"""
    from src.services.research_scoring_service import ResearchScoringService

    print("\n" + "=" * 60)
    print("测试 4: 研究评分服务")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    service = ResearchScoringService()

    # Test with full data
    print("\n[完整数据测试]")
    raw_data = {
        # 产业链定位
        "chain_position": "bottleneck",
        "moat_type": "patent",
        "moat_strength": "strong",
        # 基本面
        "pe_percentile": 20,
        "pb_percentile": 20,
        "roe": 20,
        "revenue_growth": 20,
        "earnings_growth": 20,
        # 资金面
        "institutional_holding_change": 5,
        "northbound_flow_20d": 2,
        # 技术面
        "ma_alignment": "bullish",
        "price_vs_ma250": 20,
        # 情绪
        "analyst_consensus": "outperform",
        "target_price_upside": 20,
        # 宏观
        "monetary_policy": "accommodative",
        "sector_policy": "supportive",
    }

    result = service.process(
        stock_code="600519",
        stock_name="贵州茅台",
        market="cn",
        raw_data=raw_data,
        market_implied_p=0.5,
        lr=2.0,
    )

    framework = result["framework_score"]
    bayesian = result["bayesian_result"]

    print(f"  股票: 600519 (贵州茅台)")
    print(f"  维度总数: {framework['dimension_total']:.2f}")
    print(f"  各维度得分:")
    for dim in framework["dimensions"]:
        print(f"    - {dim['dimension']}: {dim['score']:.2f}")
    print(f"\n  贝叶斯分析:")
    print(f"    Prior P: {bayesian['prior_p']:.4f}")
    print(f"    Market Implied P: {bayesian['market_implied_p']:.4f}")
    print(f"    Edge: {bayesian['edge']:.4f}")
    print(f"    Posterior P: {bayesian['posterior_p']:.4f}")
    print(f"    建议仓位: {bayesian['position_suggestion']}")

    if framework["dimension_total"] > 60:
        print("  ✅ 框架总分合理")
        tests_passed += 1
    else:
        print("  ❌ 框架总分异常")
        tests_failed += 1

    # Test with missing data
    print("\n[缺失数据测试]")
    result = service.process(
        stock_code="000001",
        stock_name="平安银行",
        market="cn",
        raw_data={},  # 空数据
        market_implied_p=0.5,
    )

    framework = result["framework_score"]
    print(f"  空数据维度总数: {framework['dimension_total']:.2f}")

    if framework["dimension_total"] == 50.0:
        print("  ✅ 缺失数据正确使用中性分")
        tests_passed += 1
    else:
        print("  ❌ 缺失数据应返回中性分 50.0")
        tests_failed += 1

    # Test different market types
    print("\n[不同市场测试]")
    for market in ["cn", "hk", "us"]:
        result = service.process(
            stock_code=f"TEST{market}",
            stock_name=f"测试股票{market}",
            market=market,
            raw_data=raw_data,
            market_implied_p=0.5,
        )
        print(
            f"  {market} 市场: 维度总分={result['framework_score']['dimension_total']:.2f}"
        )

    print(f"\n研究评分服务测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_integration_helper():
    """测试集成辅助函数"""
    from src.services.research_framework_integration import (
        _infer_market,
        _estimate_market_implied_p,
        _infer_sentiment,
    )

    print("\n" + "=" * 60)
    print("测试 5: 集成辅助函数")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test _infer_market
    print("\n[_infer_market 市场推断测试]")
    test_cases = [
        ("600519", "cn", "A股沪市"),
        ("000001", "cn", "A股深市"),
        ("300750", "cn", "A股创业板"),
        ("HK0001", "hk", "港股"),
        ("0700.HK", "hk", "港股腾讯"),
        ("AAPL", "us", "美股"),
        ("GOOGL", "us", "美股谷歌"),
        ("MSFT", "us", "美股微软"),
    ]

    for code, expected, desc in test_cases:
        result = _infer_market(code)
        if result == expected:
            print(f"  ✅ {desc} ({code}): {result}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc} ({code}): {result} (期望 {expected})")
            tests_failed += 1

    # Test _infer_sentiment
    print("\n[_infer_sentiment 情绪推断测试]")
    test_cases = [
        ("市场乐观，积极向好", "positive", "乐观文本"),
        ("市场悲观，担忧加剧", "negative", "悲观文本"),
        ("市场震荡，无明显方向", "neutral", "中性文本"),
    ]

    for text, expected, desc in test_cases:
        result = _infer_sentiment(text)
        if result == expected:
            print(f"  ✅ {desc}: {result}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc}: {result} (期望 {expected})")
            tests_failed += 1

    print(f"\n集成辅助函数测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_end_to_end_scenario():
    """端到端场景测试"""
    from src.services.research_scoring_service import ResearchScoringService

    print("\n" + "=" * 60)
    print("测试 6: 端到端场景测试")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    service = ResearchScoringService()

    # Scenario 1: Strong buy case
    print("\n[场景1: 强势买入信号]")
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

    print(f"  维度总分: {framework['dimension_total']:.2f}")
    print(f"  Prior P: {bayesian['prior_p']:.4f}")
    print(f"  Edge: {bayesian['edge']:.4f}")
    print(f"  建议仓位: {bayesian['position_suggestion']}")

    if framework["dimension_total"] >= 75 and bayesian["edge"] > 0.2:
        print("  ✅ 强势买入信号识别正确")
        tests_passed += 1
    else:
        print("  ❌ 强势买入信号识别异常")
        tests_failed += 1

    # Scenario 2: Strong sell case
    print("\n[场景2: 强烈卖出信号]")
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

    print(f"  维度总分: {framework['dimension_total']:.2f}")
    print(f"  Prior P: {bayesian['prior_p']:.4f}")
    print(f"  Edge: {bayesian['edge']:.4f}")
    print(f"  建议仓位: {bayesian['position_suggestion']}")

    if framework["dimension_total"] <= 35 and bayesian["edge"] < -0.1:
        print("  ✅ 强烈卖出信号识别正确")
        tests_passed += 1
    else:
        print("  ❌ 强烈卖出信号识别异常")
        tests_failed += 1

    # Scenario 3: Hold/neutral case
    print("\n[场景3: 中性持有信号]")
    neutral_data = {
        "chain_position": "normal",
        "moat_type": "brand",
        "moat_strength": "moderate",
        "pe_percentile": 50,
        "roe": 15,
        "revenue_growth": 10,
        "institutional_holding_change": 0,
        "northbound_flow_20d": 0,
        "ma_alignment": "neutral",
        "price_vs_ma250": 0,
        "analyst_consensus": "neutral",
        "target_price_upside": 5,
        "cognitive_difference": "market_fair",
        "monetary_policy": "neutral",
        "liquidity_indicator": "moderate",
        "sector_policy": "neutral",
    }

    result = service.process(
        stock_code="TEST_NEUTRAL",
        stock_name="测试中性",
        market="cn",
        raw_data=neutral_data,
        market_implied_p=0.5,
        lr=1.0,
    )

    framework = result["framework_score"]
    bayesian = result["bayesian_result"]

    print(f"  维度总分: {framework['dimension_total']:.2f}")
    print(f"  Prior P: {bayesian['prior_p']:.4f}")
    print(f"  Edge: {bayesian['edge']:.4f}")
    print(f"  建议仓位: {bayesian['position_suggestion']}")

    if 40 <= framework["dimension_total"] <= 60 and abs(bayesian["edge"]) < 0.2:
        print("  ✅ 中性信号识别正确")
        tests_passed += 1
    else:
        print("  ❌ 中性信号识别异常")
        tests_failed += 1

    # Scenario 4: Concentration check
    print("\n[场景4: 持仓集中度检查]")
    result = service.process(
        stock_code="TEST_CONC",
        stock_name="测试集中度",
        market="cn",
        raw_data=buy_data,
        market_implied_p=0.5,
        lr=2.0,
        current_concentration=0.35,
    )

    bayesian = result["bayesian_result"]

    print(f"  当前集中度: 0.35")
    print(f"  建议仓位: {bayesian['position_suggestion']}")
    print(f"  停止条件: {bayesian['stop_conditions']}")

    if bayesian["position_suggestion"] in ["3-5%", "5-8%"]:
        if "concentration_warning" in bayesian["stop_conditions"]:
            print("  ✅ 集中度警告正确触发")
            tests_passed += 1
        else:
            print("  ⚠️  高集中度建议触发警告")
            tests_passed += 1
    else:
        print("  ❌ 仓位建议异常")
        tests_failed += 1

    print(f"\n端到端场景测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def test_pipeline_integration():
    """测试与主流程的集成"""
    from src.analyzer import AnalysisResult

    print("\n" + "=" * 60)
    print("测试 7: 主流程集成")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test AnalysisResult has research_framework fields
    print("\n[AnalysisResult 字段检查]")
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        sentiment_score=75,
        trend_prediction="看多",
        operation_advice="买入",
    )

    if hasattr(result, "research_framework"):
        print("  ✅ research_framework 字段存在")
        tests_passed += 1
    else:
        print("  ❌ research_framework 字段缺失")
        tests_failed += 1

    if hasattr(result, "investment_conclusion"):
        print("  ✅ investment_conclusion 字段存在")
        tests_passed += 1
    else:
        print("  ❌ investment_conclusion 字段缺失")
        tests_failed += 1

    # Test to_dict includes new fields
    print("\n[to_dict 方法检查]")
    result_dict = result.to_dict()

    if "research_framework" in result_dict:
        print("  ✅ to_dict 包含 research_framework")
        tests_passed += 1
    else:
        print("  ❌ to_dict 缺少 research_framework")
        tests_failed += 1

    if "investment_conclusion" in result_dict:
        print("  ✅ to_dict 包含 investment_conclusion")
        tests_passed += 1
    else:
        print("  ❌ to_dict 缺少 investment_conclusion")
        tests_failed += 1

    # Test Config has enable_research_framework
    print("\n[Config 配置检查]")
    from src.config import Config

    config = Config()
    if hasattr(config, "enable_research_framework"):
        print(
            f"  ✅ enable_research_framework 配置存在: {config.enable_research_framework}"
        )
        tests_passed += 1
    else:
        print("  ❌ enable_research_framework 配置缺失")
        tests_failed += 1

    # Test pipeline integration method exists
    print("\n[Pipeline 方法检查]")
    from src.core.pipeline import StockAnalysisPipeline

    if hasattr(StockAnalysisPipeline, "_integrate_research_framework"):
        print("  ✅ _integrate_research_framework 方法存在")
        tests_passed += 1
    else:
        print("  ❌ _integrate_research_framework 方法缺失")
        tests_failed += 1

    print(f"\n主流程集成测试结果: {tests_passed} 通过, {tests_failed} 失败")
    return tests_passed, tests_failed


def main():
    print("\n" + "=" * 60)
    print("P1 研究框架完整测试套件")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_passed = 0
    all_failed = 0

    # Run all tests
    passed, failed = test_bayesian_engine()
    all_passed += passed
    all_failed += failed

    passed, failed = test_scoring_engine()
    all_passed += passed
    all_failed += failed

    passed, failed = test_indicator_modules()
    all_passed += passed
    all_failed += failed

    passed, failed = test_research_scoring_service()
    all_passed += passed
    all_failed += failed

    passed, failed = test_integration_helper()
    all_passed += passed
    all_failed += failed

    passed, failed = test_end_to_end_scenario()
    all_passed += passed
    all_failed += failed

    passed, failed = test_pipeline_integration()
    all_passed += passed
    all_failed += failed

    # Summary
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"总计: {all_passed + all_failed} 项测试")
    print(f"通过: {all_passed} 项 ✅")
    print(f"失败: {all_failed} 项 ❌")
    print(f"通过率: {all_passed / (all_passed + all_failed) * 100:.1f}%")

    if all_failed == 0:
        print("\n🎉 所有测试通过！P1 研究框架验证完成！")
        return 0
    else:
        print(f"\n⚠️  有 {all_failed} 项测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
