# -*- coding: utf-8 -*-
"""
Tests for DataFetcherManager caching and performance-related paths.

Covers:
- Fundamental context instance-level caching
- Realtime quote global cache in EfinanceFetcher
- _run_with_timeout worker-pool limiting
- Cache pruning under capacity pressure
"""

import os
import sys
import time
import unittest
from threading import BoundedSemaphore, Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import DataFetcherManager


class _DummyFundamentalAdapter:
    def __init__(self):
        self.calls = []

    def get_fundamental_bundle(self, stock_code):
        self.calls.append(stock_code)
        return {
            "status": "partial",
            "growth": {"revenue_yoy": 10.0},
            "earnings": {},
            "institution": {},
            "source_chain": ["dummy"],
            "errors": [],
        }


class TestDataFetcherCaching(unittest.TestCase):
    def test_fundamental_context_cache_avoids_duplicate_adapter_calls(self):
        manager = DataFetcherManager(fetchers=[])
        cfg = SimpleNamespace(
            enable_fundamental_pipeline=True,
            fundamental_cache_ttl_seconds=60,
            fundamental_cache_max_entries=256,
            fundamental_stage_timeout_seconds=2.0,
            fundamental_fetch_timeout_seconds=1.0,
            fundamental_retry_max=1,
        )
        adapter = _DummyFundamentalAdapter()
        quote = SimpleNamespace(
            price=100.0,
            pe_ratio=12.0,
            pb_ratio=2.0,
            total_mv=1e11,
            circ_mv=7e10,
            source=SimpleNamespace(value="dummy"),
        )

        with patch("src.config.get_config", return_value=cfg), \
                patch.object(manager, "get_realtime_quote", return_value=quote), \
                patch(
                    "data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_fundamental_bundle",
                    side_effect=adapter.get_fundamental_bundle,
                ), \
                patch.object(manager, "get_capital_flow_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_dragon_tiger_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_board_context", return_value={"status": "not_supported", "source_chain": []}):
            ctx1 = manager.get_fundamental_context("600519", budget_seconds=1.5)
            ctx2 = manager.get_fundamental_context("600519", budget_seconds=1.5)

        self.assertEqual(adapter.calls, ["600519"])
        self.assertEqual(ctx1["market"], "cn")
        self.assertEqual(ctx2["market"], "cn")

    def test_fundamental_context_cache_isolated_by_budget_bucket(self):
        manager = DataFetcherManager(fetchers=[])
        cfg = SimpleNamespace(
            enable_fundamental_pipeline=True,
            fundamental_cache_ttl_seconds=60,
            fundamental_cache_max_entries=256,
            fundamental_stage_timeout_seconds=2.0,
            fundamental_fetch_timeout_seconds=1.0,
            fundamental_retry_max=1,
        )
        adapter = _DummyFundamentalAdapter()
        quote = SimpleNamespace(
            price=100.0,
            pe_ratio=12.0,
            pb_ratio=2.0,
            total_mv=1e11,
            circ_mv=7e10,
            source=SimpleNamespace(value="dummy"),
        )

        with patch("src.config.get_config", return_value=cfg), \
                patch.object(manager, "get_realtime_quote", return_value=quote), \
                patch(
                    "data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_fundamental_bundle",
                    side_effect=adapter.get_fundamental_bundle,
                ), \
                patch.object(manager, "get_capital_flow_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_dragon_tiger_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_board_context", return_value={"status": "not_supported", "source_chain": []}):
            manager.get_fundamental_context("600519", budget_seconds=1.0)
            manager.get_fundamental_context("600519", budget_seconds=2.0)

        # Different budget buckets should produce two distinct adapter calls
        self.assertEqual(adapter.calls, ["600519", "600519"])

    def test_fundamental_context_cache_prunes_oldest_on_capacity(self):
        manager = DataFetcherManager(fetchers=[])
        cfg = SimpleNamespace(
            enable_fundamental_pipeline=True,
            fundamental_cache_ttl_seconds=3600,
            fundamental_cache_max_entries=2,
            fundamental_stage_timeout_seconds=2.0,
            fundamental_fetch_timeout_seconds=1.0,
            fundamental_retry_max=1,
        )
        adapter = _DummyFundamentalAdapter()
        quote = SimpleNamespace(
            price=100.0,
            pe_ratio=12.0,
            pb_ratio=2.0,
            total_mv=1e11,
            circ_mv=7e10,
            source=SimpleNamespace(value="dummy"),
        )

        with patch("src.config.get_config", return_value=cfg), \
                patch.object(manager, "get_realtime_quote", return_value=quote), \
                patch(
                    "data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_fundamental_bundle",
                    side_effect=adapter.get_fundamental_bundle,
                ), \
                patch.object(manager, "get_capital_flow_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_dragon_tiger_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_board_context", return_value={"status": "not_supported", "source_chain": []}):
            manager.get_fundamental_context("600519", budget_seconds=1.0)
            time.sleep(0.01)
            manager.get_fundamental_context("000001", budget_seconds=1.0)
            time.sleep(0.01)
            # Adding a third distinct key forces eviction of the oldest entry (600519)
            manager.get_fundamental_context("000002", budget_seconds=1.0)
            time.sleep(0.01)
            manager.get_fundamental_context("600519", budget_seconds=1.0)

        # 600519 was evicted then re-fetched
        self.assertEqual(adapter.calls, ["600519", "000001", "000002", "600519"])

    def test_fundamental_context_cache_respects_ttl(self):
        manager = DataFetcherManager(fetchers=[])
        cfg = SimpleNamespace(
            enable_fundamental_pipeline=True,
            fundamental_cache_ttl_seconds=0.05,
            fundamental_cache_max_entries=256,
            fundamental_stage_timeout_seconds=2.0,
            fundamental_fetch_timeout_seconds=1.0,
            fundamental_retry_max=1,
        )
        adapter = _DummyFundamentalAdapter()
        quote = SimpleNamespace(
            price=100.0,
            pe_ratio=12.0,
            pb_ratio=2.0,
            total_mv=1e11,
            circ_mv=7e10,
            source=SimpleNamespace(value="dummy"),
        )

        with patch("src.config.get_config", return_value=cfg), \
                patch.object(manager, "get_realtime_quote", return_value=quote), \
                patch(
                    "data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_fundamental_bundle",
                    side_effect=adapter.get_fundamental_bundle,
                ), \
                patch.object(manager, "get_capital_flow_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_dragon_tiger_context", return_value={"status": "not_supported", "source_chain": []}), \
                patch.object(manager, "get_board_context", return_value={"status": "not_supported", "source_chain": []}):
            manager.get_fundamental_context("600519", budget_seconds=1.0)
            time.sleep(0.06)
            manager.get_fundamental_context("600519", budget_seconds=1.0)

        self.assertEqual(adapter.calls, ["600519", "600519"])

    def test_run_with_timeout_limits_hanging_workers(self):
        manager = DataFetcherManager(fetchers=[])
        manager._fundamental_timeout_slots = BoundedSemaphore(1)

        unblock = Event()

        def _hanging_task():
            unblock.wait(timeout=0.5)
            return 1

        try:
            result, err, _ = manager._run_with_timeout(_hanging_task, 0.01, "hang")
            self.assertIsNone(result)
            self.assertIn("timeout", err or "")

            result2, err2, _ = manager._run_with_timeout(_hanging_task, 0.01, "hang")
            self.assertIsNone(result2)
            self.assertIn("worker pool exhausted", err2 or "")
        finally:
            unblock.set()
            time.sleep(0.02)


class TestEfinanceRealtimeCache(unittest.TestCase):
    def test_efinance_realtime_global_cache_avoids_duplicate_network_calls(self):
        import pandas as pd
        from data_provider import efinance_fetcher
        from data_provider.efinance_fetcher import EfinanceFetcher

        fetcher = EfinanceFetcher.__new__(EfinanceFetcher)

        fake_df = pd.DataFrame([
            {
                "股票代码": "600519",
                "股票名称": "贵州茅台",
                "最新价": 1700.0,
                "涨跌幅": 1.0,
                "涨跌额": 17.0,
                "成交量": 10000,
                "成交额": 1000000.0,
                "换手率": 0.5,
                "振幅": 1.5,
                "最高": 1710.0,
                "最低": 1690.0,
                "今开": 1695.0,
                "昨收": 1683.0,
            }
        ])

        # Prime the module-level cache so no network call is needed
        efinance_fetcher._realtime_cache["data"] = fake_df
        efinance_fetcher._realtime_cache["timestamp"] = time.time()

        def _should_not_call(_func, *args, **kwargs):
            self.fail("_ef_call_with_timeout should not be called when cache is warm")

        with patch("data_provider.efinance_fetcher._ef_call_with_timeout", side_effect=_should_not_call):
            quote1 = fetcher.get_realtime_quote("600519")
            quote2 = fetcher.get_realtime_quote("600519")

        # EfinanceFetcher uses a module-level cache; no network call should occur
        self.assertIsNotNone(quote1)
        self.assertIsNotNone(quote2)
        self.assertEqual(quote1.name, "贵州茅台")
        self.assertEqual(quote2.name, "贵州茅台")


if __name__ == "__main__":
    unittest.main()
