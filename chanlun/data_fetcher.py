# -*- coding: utf-8 -*-
"""缠论 K 线数据获取器。

使用项目统一 DataFetcherManager，支持多数据源自动切换（efinance -> akshare -> baostock -> yfinance）。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "DOT"}


class ChanlunDataFetcher:
    """缠论分析专用数据获取器，使用 DataFetcherManager 多源切换。"""

    _manager = None

    def __init__(self):
        self._manager = None

    @property
    def manager(self):
        """懒加载 DataFetcherManager。"""
        if self._manager is None:
            from data_provider import DataFetcherManager

            self._manager = DataFetcherManager()
        return self._manager

    def fetch(
        self,
        symbol: str,
        market: str = "A",
        period: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """获取 K 线数据。"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start = datetime.now() - timedelta(days=400)
            start_date = start.strftime("%Y%m%d")

        if market == "A":
            return self._fetch_a_stock(symbol, start_date, end_date)
        elif market == "HK":
            return self._fetch_hk_stock(symbol, start_date, end_date)
        elif market == "US":
            if symbol.upper() in CRYPTO_SYMBOLS:
                return self._fetch_crypto(symbol, start_date, end_date)
            return self._fetch_us_stock(symbol, start_date, end_date)
        elif market == "CRYPTO":
            return self._fetch_crypto(symbol, start_date, end_date)
        return None

    def _fetch_a_stock(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """获取 A 股数据，使用 DataFetcherManager 多源切换。"""
        try:
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
            df, source = self.manager.get_daily_data(
                stock_code=symbol,
                start_date=start_fmt,
                end_date=end_fmt,
                days=400,
            )
            if df is not None and not df.empty:
                logger.info(
                    f"[Chanlun] A股 {symbol} 获取成功 (来源: {source}), {len(df)} 条数据"
                )
                return self._normalize_manager_df(df)
        except Exception as e:
            logger.warning(f"[Chanlun] A股 {symbol} 获取失败: {e}")
        return None

    def _fetch_hk_stock(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """获取港股数据。"""
        try:
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
            df, source = self.manager.get_daily_data(
                stock_code=symbol,
                start_date=start_fmt,
                end_date=end_fmt,
                days=400,
            )
            if df is not None and not df.empty:
                logger.info(
                    f"[Chanlun] 港股 {symbol} 获取成功 (来源: {source}), {len(df)} 条数据"
                )
                return self._normalize_manager_df(df)
        except Exception as e:
            logger.warning(f"[Chanlun] 港股 {symbol} 获取失败: {e}")
        return None

    def _fetch_us_stock(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """获取美股数据。"""
        try:
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
            df, source = self.manager.get_daily_data(
                stock_code=symbol,
                start_date=start_fmt,
                end_date=end_fmt,
                days=400,
            )
            if df is not None and not df.empty:
                logger.info(
                    f"[Chanlun] 美股 {symbol} 获取成功 (来源: {source}), {len(df)} 条数据"
                )
                return self._normalize_manager_df(df)
        except Exception as e:
            logger.warning(f"[Chanlun] 美股 {symbol} 获取失败: {e}")
        return None

    def _fetch_crypto(
        self,
        symbol: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """获取加密货币数据。"""
        try:
            pair = f"{symbol.upper()}USDT"
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
            df, source = self.manager.get_daily_data(
                stock_code=pair,
                start_date=start_fmt,
                end_date=end_fmt,
                days=400,
            )
            if df is not None and not df.empty:
                logger.info(
                    f"[Chanlun] 加密 {symbol} 获取成功 (来源: {source}), {len(df)} 条数据"
                )
                return self._normalize_manager_df(df)
        except Exception as e:
            logger.warning(f"[Chanlun] 加密 {symbol} 获取失败: {e}")
        return None

    def _normalize_manager_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFetcherManager 返回的 DataFrame。"""
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        available = [c for c in required_cols if c in df.columns]
        if not available:
            return pd.DataFrame()
        df = df[available].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        return df.reset_index(drop=True)
