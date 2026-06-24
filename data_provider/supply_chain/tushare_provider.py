# -*- coding: utf-8 -*-
"""
Tushare Pro Supply Chain Data Provider.

Fetches supplier and customer data from Tushare Pro.
"""

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TushareSupplyChainProvider:
    """Provider for supplier and customer data from Tushare Pro"""

    def __init__(self, token: Optional[str] = None):
        self._token = token or os.getenv("TUSHARE_TOKEN")
        self._pro = None
        self._init_tushare()

    def _init_tushare(self):
        """Initialize Tushare Pro API"""
        if self._token is None:
            logger.warning("[TushareSupplyChainProvider] TUSHARE_TOKEN not set")
            return

        try:
            import tushare as ts

            self._pro = ts.pro_api(self._token)
            logger.info("[TushareSupplyChainProvider] initialized")
        except ImportError:
            logger.warning("[TushareSupplyChainProvider] tushare not installed")
        except Exception as e:
            logger.warning(f"[TushareSupplyChainProvider] init failed: {e}")

    def get_supplier_customer(
        self, stock_code: str, year: int = 2023
    ) -> Dict[str, List[str]]:
        """
        Get top 5 suppliers and customers.

        Args:
            stock_code: Stock code (e.g., 600519.SH)
            year: Report year

        Returns:
            Dict with 'suppliers' and 'customers' lists
        """
        if self._pro is None:
            return {"suppliers": [], "customers": []}

        try:
            ts_code = self._normalize_ts_code(stock_code)
            end_date = f"{year}1231"

            df = self._pro.disclosure_supplier_customer(
                ts_code=ts_code, end_date=end_date
            )

            if df is None or df.empty:
                logger.info(f"[TushareSupplyChainProvider] No data for {stock_code}")
                return {"suppliers": [], "customers": []}

            suppliers = []
            customers = []

            for _, row in df.iterrows():
                supplier = row.get("supplier_name", "")
                supplier_ratio = row.get("supplier_ratio", 0)
                if supplier and str(supplier).strip():
                    suppliers.append(f"{supplier} ({supplier_ratio}%)")

                customer = row.get("customer_name", "")
                customer_ratio = row.get("customer_ratio", 0)
                if customer and str(customer).strip():
                    customers.append(f"{customer} ({customer_ratio}%)")

            logger.info(
                f"[TushareSupplyChainProvider] {stock_code}: "
                f"{len(suppliers)} suppliers, {len(customers)} customers"
            )

            return {"suppliers": suppliers[:5], "customers": customers[:5]}

        except Exception as e:
            logger.warning(f"[TushareSupplyChainProvider] Failed: {e}")
            return {"suppliers": [], "customers": []}

    def _normalize_ts_code(self, stock_code: str) -> str:
        """Convert stock code to Tushare format (e.g., 600519.SH)"""
        code = stock_code.strip().upper()

        if "." in code:
            return code

        if code.startswith("HK"):
            return f"{code}.HK"

        if len(code) == 5:
            return f"{code}.SH"

        if code.startswith("00") and len(code) == 6:
            return f"{code}.SZ"

        if code.startswith("60") or code.startswith("688"):
            return f"{code}.SH"

        if (
            code.startswith("00")
            or code.startswith("30")
            or code.startswith("002")
            or code.startswith("003")
        ):
            return f"{code}.SZ"

        if code.startswith("8") or code.startswith("4"):
            return f"{code}.BJ"

        return f"{code}.SH"
