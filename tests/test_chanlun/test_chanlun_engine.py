# -*- coding: utf-8 -*-
"""缠论引擎单元测试。"""

import pytest
import pandas as pd
import numpy as np
from chanlun.chanlun_engine import ChanLunEngine, load_params, DEFAULT_PARAMS


def _generate_test_data(days: int = 200) -> pd.DataFrame:
    """生成测试用的K线数据。"""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=days, freq="D")

    prices = [100.0]
    for i in range(1, days):
        change = np.random.normal(0, 2)
        prices.append(prices[-1] * (1 + change / 100))

    df = pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": [p * (1 + abs(np.random.normal(0, 0.5) / 100)) for p in prices],
            "low": [p * (1 - abs(np.random.normal(0, 0.5) / 100)) for p in prices],
            "close": prices,
            "volume": [1000000 + np.random.randint(-100000, 100000) for _ in prices],
        }
    )
    return df


class TestChanLunEngine:
    """缠论引擎测试。"""

    def test_init_with_valid_dataframe(self):
        """测试用有效数据初始化引擎。"""
        df = _generate_test_data(100)
        engine = ChanLunEngine(df)
        assert engine.df is not None
        assert len(engine.df) == 100
        assert "macd" in engine.df.columns
        assert "macd_dif" in engine.df.columns
        assert "macd_dea" in engine.df.columns

    def test_init_with_invalid_columns(self):
        """测试用无效列名初始化应抛出异常。"""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10),
                "open": [100] * 10,
                "close": [100] * 10,
            }
        )
        with pytest.raises(ValueError, match="DataFrame must have columns"):
            ChanLunEngine(df)

    def test_ema_calculation(self):
        """测试EMA计算。"""
        df = _generate_test_data(50)
        engine = ChanLunEngine(df)

        expected_fast = 2.0 / 13
        assert abs(engine.df["ema_fast"].iloc[0] - df["close"].iloc[0]) < 0.01

    def test_macd_calculation(self):
        """测试MACD计算。"""
        df = _generate_test_data(100)
        engine = ChanLunEngine(df)

        assert "macd" in engine.df.columns
        assert "macd_dif" in engine.df.columns
        assert "macd_dea" in engine.df.columns
        assert len(engine.df) == 100

    def test_find_fractals(self):
        """测试分型识别。"""
        df = _generate_test_data(100)
        engine = ChanLunEngine(df)
        fractals = engine._find_fractals()

        assert isinstance(fractals, list)
        for f in fractals:
            assert f["type"] in ("ding", "di")
            assert "date" in f
            assert "val" in f
            assert "real" in f

    def test_find_pivots(self):
        """测试极值点识别。"""
        df = _generate_test_data(100)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        pivots = engine._find_pivots()

        assert isinstance(pivots, list)
        for p in pivots:
            assert "date" in p
            assert "price" in p
            assert "type" in p

    def test_build_strokes(self):
        """测试笔构建。"""
        df = _generate_test_data(200)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        engine.pivots = engine._find_pivots()
        strokes = engine._build_strokes()

        assert isinstance(strokes, list)
        for s in strokes:
            assert s["type"] in ("up", "down")
            assert "start_date" in s
            assert "end_date" in s
            assert "high" in s
            assert "low" in s
            assert "mmds" in s
            assert "mm_score" in s

    def test_find_zhongshus(self):
        """测试中枢识别。"""
        df = _generate_test_data(300)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        engine.pivots = engine._find_pivots()
        engine.strokes = engine._build_strokes()
        zhongshus = engine._find_zhongshus()

        assert isinstance(zhongshus, list)
        for zs in zhongshus:
            assert "zg" in zs
            assert "zd" in zs
            assert zs["zg"] >= zs["zd"]

    def test_determine_trend(self):
        """测试趋势判断。"""
        df = _generate_test_data(200)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        engine.pivots = engine._find_pivots()
        strokes = engine._build_strokes()
        engine.strokes = strokes

        trend = engine._determine_trend()
        assert trend in ("上涨", "下跌", "盘整")

    def test_compute_summary(self):
        """测试摘要计算。"""
        df = _generate_test_data(300)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        engine.pivots = engine._find_pivots()
        engine.strokes = engine._build_strokes()
        engine.zhongshus = engine._find_zhongshus()
        signals = engine._extract_signals()

        summary = engine._compute_summary()
        assert "divergence_count" in summary
        assert "buy_signals" in summary
        assert "sell_signals" in summary
        assert "signal_strength" in summary
        assert summary["signal_strength"] in ("strong", "medium", "weak")

    def test_full_analyze(self):
        """测试完整分析流程。"""
        df = _generate_test_data(300)
        engine = ChanLunEngine(df)
        result = engine.analyze()

        assert result["status"] == "OK"
        assert "klines_count" in result
        assert "fractals" in result
        assert "strokes" in result
        assert "zhongshus" in result
        assert "signals" in result
        assert "current_trend" in result
        assert "position" in result
        assert "summary" in result
        assert "current_price" in result

    def test_analyze_with_insufficient_data(self):
        """测试数据不足的情况。"""
        df = _generate_test_data(10)
        engine = ChanLunEngine(df)
        engine.fractals = engine._find_fractals()
        engine.pivots = engine._find_pivots()
        strokes = engine._build_strokes()

        assert len(strokes) == 0 or len(strokes) < 5

    def test_load_params_default(self):
        """测试默认参数加载。"""
        params = load_params(None)
        assert params is not None
        assert "macd" in params
        assert "fractal" in params
        assert "stroke" in params
        assert "beichi" in params
        assert "mm_score_weights" in params

    def test_params_macd(self):
        """测试MACD参数。"""
        df = _generate_test_data(100)
        custom_params = {"macd": {"fast": 5, "slow": 20, "signal": 5}, **DEFAULT_PARAMS}
        engine = ChanLunEngine(df, params=custom_params)
        assert "macd" in engine.df.columns


class TestChanLunEngineEdgeCases:
    """缠论引擎边界情况测试。"""

    def test_empty_dataframe(self):
        """测试空DataFrame。"""
        df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        engine = ChanLunEngine(df)
        result = engine.analyze()
        assert result["status"] == "OK"
        assert result["klines_count"] == 0

    def test_single_bar(self):
        """测试单根K线。"""
        df = _generate_test_data(1)
        engine = ChanLunEngine(df)
        result = engine.analyze()
        assert result["status"] == "OK"

    def test_flat_price_data(self):
        """测试价格持平的数据。"""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=100),
                "open": [100.0] * 100,
                "high": [100.5] * 100,
                "low": [99.5] * 100,
                "close": [100.0] * 100,
                "volume": [1000000] * 100,
            }
        )
        engine = ChanLunEngine(df)
        result = engine.analyze()
        assert result["status"] == "OK"

    def test_trending_up_data(self):
        """测试单边上涨数据。"""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=100),
                "open": [100 + i for i in range(100)],
                "high": [101 + i for i in range(100)],
                "low": [99 + i for i in range(100)],
                "close": [100 + i for i in range(100)],
                "volume": [1000000] * 100,
            }
        )
        engine = ChanLunEngine(df)
        result = engine.analyze()
        assert result["status"] == "OK"
        assert result["current_trend"] in ("上涨", "盘整")

    def test_trending_down_data(self):
        """测试单边下跌数据。"""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=100),
                "open": [100 - i for i in range(100)],
                "high": [101 - i for i in range(100)],
                "low": [99 - i for i in range(100)],
                "close": [100 - i for i in range(100)],
                "volume": [1000000] * 100,
            }
        )
        engine = ChanLunEngine(df)
        result = engine.analyze()
        assert result["status"] == "OK"
        assert result["current_trend"] in ("下跌", "盘整")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
