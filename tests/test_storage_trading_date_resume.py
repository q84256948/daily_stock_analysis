# -*- coding: utf-8 -*-
"""
Tests for StockStorage / DatabaseManager resume logic.

Covers:
- has_today_data natural-day matching (current behavior)
- Weekend/holiday behavior where latest trading-day data exists
"""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage import DatabaseManager, StockDaily


class TestStorageTradingDateResume(unittest.TestCase):
    def setUp(self):
        DatabaseManager.reset_instance()
        self.db = DatabaseManager(db_url="sqlite:///:memory:")

    def tearDown(self):
        DatabaseManager.reset_instance()

    def _save_daily(self, code, day, close=100.0):
        with self.db.get_session() as session:
            session.add(
                StockDaily(
                    code=code,
                    date=day,
                    open=close - 1.0,
                    high=close + 1.0,
                    low=close - 1.0,
                    close=close,
                    volume=1000,
                    amount=100000.0,
                    pct_chg=0.0,
                    data_source="test",
                )
            )
            session.commit()

    def test_has_today_data_true_when_target_date_exists(self):
        today = date.today()
        self._save_daily("600519", today)

        self.assertTrue(self.db.has_today_data("600519", target_date=today))

    def test_has_today_data_false_when_target_date_missing(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        self._save_daily("600519", yesterday)

        self.assertFalse(self.db.has_today_data("600519", target_date=today))

    def test_has_today_data_uses_today_by_default(self):
        today = date.today()
        self._save_daily("600519", today)

        self.assertTrue(self.db.has_today_data("600519"))

    def test_weekend_runs_currently_miss_latest_trading_day_data(self):
        """
        Current has_today_data uses the natural day. If today is a weekend and
        the DB only has Friday's bar, the method returns False.

        This test documents the current behavior that the P1 optimization
        "resume by trading day" aims to fix.
        """
        # Pick a known weekend date (Saturday)
        saturday = date(2026, 6, 20)
        friday = saturday - timedelta(days=1)
        self._save_daily("600519", friday)

        # Current implementation checks for Saturday data explicitly
        self.assertFalse(self.db.has_today_data("600519", target_date=saturday))


if __name__ == "__main__":
    unittest.main()
