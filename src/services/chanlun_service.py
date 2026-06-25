# -*- coding: utf-8 -*-
"""缠论分析服务。

使用自实现 ChanLunEngine，与 openclaw-chanlun-skill 算法一致。
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from chanlun.chanlun_engine import ChanLunEngine, load_params
from chanlun.data_fetcher import ChanlunDataFetcher

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DEFAULT_DATA_DIR = os.path.join(_REPO_ROOT, "data", "chanlun_skill")


class ChanlunService:
    """缠论分析服务。"""

    def __init__(self, params_path: Optional[str] = None):
        data_dir = os.environ.get("CHANLUN_DATA_DIR") or _DEFAULT_DATA_DIR
        if params_path is None:
            params_path = os.path.join(data_dir, "params.json")
        self.params = load_params(params_path)
        self.fetcher = ChanlunDataFetcher()

    def analyze(
        self,
        symbol: str,
        market: str = "A",
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        """对股票进行缠论分析。"""
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")

        df = self.fetcher.fetch(symbol, market, "day", start_date, end_date)

        if df is None or df.empty:
            return {"error": f"数据获取失败: {symbol}", "symbol": symbol}

        if len(df) < 50:
            return {"error": f"数据不足（需要至少50根K线）: {symbol}", "symbol": symbol}

        try:
            engine = ChanLunEngine(df, self.params)
            result = engine.analyze()
            result["symbol"] = symbol
            result["market"] = market
            result["date_range"] = f"{start_date}~{end_date}"
            return result
        except Exception as e:
            logger.error(f"缠论分析失败 {symbol}: {e}")
            return {"error": f"缠论分析失败: {str(e)}", "symbol": symbol}
