# -*- coding: utf-8 -*-
"""数据获取器单元测试。"""

import pytest
import pandas as pd
from chanlun.data_fetcher import ChanlunDataFetcher


class TestChanlunDataFetcher:
    """数据获取器测试。"""

    def test_init(self):
        """测试初始化。"""
        fetcher = ChanlunDataFetcher()
        assert fetcher is not None
        assert hasattr(fetcher, "CRYPTO_SYMBOLS")

    def test_crypto_symbols(self):
        """测试加密货币符号集合。"""
        fetcher = ChanlunDataFetcher()
        assert "BTC" in fetcher.CRYPTO_SYMBOLS
        assert "ETH" in fetcher.CRYPTO_SYMBOLS

    def test_normalize_yfinance_df(self):
        """测试yfinance数据标准化。"""
        fetcher = ChanlunDataFetcher()
        df = pd.DataFrame(
            {
                "Open": [100, 101, 102],
                "High": [105, 106, 107],
                "Low": [95, 96, 97],
                "Close": [102, 103, 104],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=pd.date_range("2024-01-01", periods=3),
        )

        result = fetcher._normalize_yfinance_df(df)

        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
        assert "date" in result.columns

    def test_fetch_with_invalid_market(self):
        """测试无效市场。"""
        fetcher = ChanlunDataFetcher()
        result = fetcher.fetch("000001", market="INVALID")
        assert result is None

    def test_fetch_crypto_with_btc(self):
        """测试BTC加密货币获取。"""
        fetcher = ChanlunDataFetcher()
        result = fetcher.fetch(
            "BTC", market="CRYPTO", start_date="20240101", end_date="20240110"
        )
        if result is not None:
            assert len(result) > 0
            assert "open" in result.columns
            assert "high" in result.columns
            assert "low" in result.columns
            assert "close" in result.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
