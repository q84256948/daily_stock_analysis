# -*- coding: utf-8 -*-
"""
Institutional Holdings Data Provider.

Fetches institutional holdings data using akshare:
- Fund holdings (基金持仓)
- QFII holdings
- Insurance holdings
- Social security holdings
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class InstitutionalHoldingsProvider:
    """
    Provider for institutional holdings data.

    Uses akshare to fetch:
    - Top 10 circulating shareholders (前十大流通股东)
    - Fund holdings by stock
    - Institution trade data
    """

    def __init__(self):
        self._ak = None
        self._init_akshare()

    def _init_akshare(self):
        """Lazy initialize akshare"""
        if self._ak is None:
            try:
                import akshare as ak

                self._ak = ak
                logger.info("[InstitutionalHoldingsProvider] akshare initialized")
            except ImportError:
                logger.warning("[InstitutionalHoldingsProvider] akshare not installed")
                self._ak = None

    def get_top_shareholders(self, stock_code: str) -> Dict[str, Any]:
        """
        Get top 10 circulating shareholders for a stock.

        Args:
            stock_code: Stock code (e.g., 600519)

        Returns:
            Dict with shareholder data
        """
        if self._ak is None:
            self._init_akshare()
            if self._ak is None:
                return self._get_mock_shareholders(stock_code)

        try:
            df = self._ak.stock_spot_top10_shareholder_em(symbol=stock_code)

            holders = []
            for _, row in df.iterrows():
                holders.append(
                    {
                        "name": str(row.get("股东名称", "")),
                        "type": str(row.get("股东类型", "")),
                        "hold_ratio": float(row.get("持股比例", 0) or 0),
                        "shares": int(row.get("持股数量", 0) or 0),
                        "change": float(row.get("增减仓", 0) or 0),
                    }
                )

            result = {
                "stock_code": stock_code,
                "holders": holders,
                "total_holders": len(holders),
                "institutional_ratio": sum(h.get("hold_ratio", 0) for h in holders),
                "updated_at": datetime.now().isoformat(),
            }

            logger.info(
                f"[InstitutionalHoldingsProvider] Fetched {len(holders)} holders for {stock_code}"
            )
            return result

        except Exception as e:
            logger.error(
                f"[InstitutionalHoldingsProvider] Failed to fetch shareholders: {e}"
            )
            return self._get_mock_shareholders(stock_code)

    def get_fund_holdings(
        self, stock_code: str, period: str = "1"
    ) -> List[Dict[str, Any]]:
        """
        Get fund holdings data for a stock.

        Args:
            stock_code: Stock code
            period: Quarter (e.g., "1" for Q1, "4" for Q4)

        Returns:
            List of fund holdings
        """
        if self._ak is None:
            self._init_akshare()
            if self._ak is None:
                return []

        try:
            df = self._ak.stock_fund_stock_spot(symbol=stock_code, indicator="公募基金")

            holdings = []
            for _, row in df.iterrows():
                holdings.append(
                    {
                        "fund_code": str(row.get("基金代码", "")),
                        "fund_name": str(row.get("基金名称", "")),
                        "hold_shares": int(row.get("持股数", 0) or 0),
                        "hold_ratio": float(row.get("持股比例", 0) or 0),
                        "market_value": float(row.get("市值", 0) or 0),
                    }
                )

            logger.info(
                f"[InstitutionalHoldingsProvider] Fetched {len(holdings)} fund holdings for {stock_code}"
            )
            return holdings

        except Exception as e:
            logger.error(
                f"[InstitutionalHoldingsProvider] Failed to fetch fund holdings: {e}"
            )
            return []

    def get_institution_trade_stats(
        self, stock_code: str, days: int = 5
    ) -> Dict[str, Any]:
        """
        Get institutional trading statistics.

        Args:
            stock_code: Stock code
            days: Number of days to look back

        Returns:
            Dict with trade statistics
        """
        if self._ak is None:
            self._init_akshare()
            if self._ak is None:
                return {}

        try:
            df = self._ak.stock_institute_hold_em(symbol=stock_code)

            if df is None or df.empty:
                return {}

            buy_count = 0
            sell_count = 0
            net_flow = 0.0

            for _, row in df.iterrows():
                action = str(row.get("操作", "")).lower()
                amount = float(row.get("成交量", 0) or 0)

                if "买入" in action or "buy" in action:
                    buy_count += 1
                    net_flow += amount
                elif "卖出" in action or "sell" in action:
                    sell_count += 1
                    net_flow -= amount

            return {
                "stock_code": stock_code,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "net_flow": net_flow,
                "institution_count": buy_count + sell_count,
                "updated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(
                f"[InstitutionalHoldingsProvider] Failed to fetch trade stats: {e}"
            )
            return {}

    def calculate_institutional_score(
        self,
        stock_code: str,
        holding_change_threshold: float = 5.0,
        net_flow_threshold: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Calculate institutional score for supply chain positioning.

        Args:
            stock_code: Stock code
            holding_change_threshold: Threshold for significant holding change (%)
            net_flow_threshold: Threshold for significant net flow (亿)

        Returns:
            Score dict with components
        """
        holders_data = self.get_top_shareholders(stock_code)
        trade_stats = self.get_institution_trade_stats(stock_code)

        score = 50.0
        components = []

        if holders_data and holders_data.get("holders"):
            total_institutional = holders_data.get("institutional_ratio", 0)

            if total_institutional > 50:
                score += 15
                components.append(("high_institutional", 15))
            elif total_institutional > 30:
                score += 10
                components.append(("medium_institutional", 10))
            elif total_institutional < 10:
                score -= 10
                components.append(("low_institutional", -10))

            for holder in holders_data.get("holders", []):
                change = holder.get("change", 0)
                if change > holding_change_threshold:
                    score += 5
                    components.append(("significant_increase", 5))
                elif change < -holding_change_threshold:
                    score -= 5
                    components.append(("significant_decrease", -5))

        if trade_stats:
            net_flow = trade_stats.get("net_flow", 0)
            if net_flow > net_flow_threshold:
                score += 10
                components.append(("positive_net_flow", 10))
            elif net_flow < -net_flow_threshold:
                score -= 10
                components.append(("negative_net_flow", -10))

        score = max(0.0, min(100.0, score))

        return {
            "stock_code": stock_code,
            "score": score,
            "components": components,
            "institutional_ratio": holders_data.get("institutional_ratio", 0)
            if holders_data
            else 0,
            "net_flow": trade_stats.get("net_flow", 0) if trade_stats else 0,
            "updated_at": datetime.now().isoformat(),
        }

    def _get_mock_shareholders(self, stock_code: str) -> Dict[str, Any]:
        """Return mock data when akshare is unavailable"""
        return {
            "stock_code": stock_code,
            "holders": [
                {
                    "name": "贵州茅台集团",
                    "type": "法人",
                    "hold_ratio": 54.06,
                    "shares": 679000000,
                    "change": 0,
                },
                {
                    "name": "汇金公司",
                    "type": "国家队",
                    "hold_ratio": 4.00,
                    "shares": 50000000,
                    "change": 0,
                },
                {
                    "name": "易方达消费",
                    "type": "公募",
                    "hold_ratio": 1.50,
                    "shares": 18750000,
                    "change": 0.5,
                },
                {
                    "name": "景顺新兴",
                    "type": "公募",
                    "hold_ratio": 1.20,
                    "shares": 15000000,
                    "change": 0.3,
                },
            ],
            "total_holders": 4,
            "institutional_ratio": 61.26,
            "updated_at": datetime.now().isoformat(),
        }


def get_institutional_holdings_provider() -> InstitutionalHoldingsProvider:
    """Get singleton provider"""
    if not hasattr(get_institutional_holdings_provider, "_instance"):
        get_institutional_holdings_provider._instance = InstitutionalHoldingsProvider()
    return get_institutional_holdings_provider._instance
