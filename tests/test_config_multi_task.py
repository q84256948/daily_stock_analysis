# -*- coding: utf-8 -*-
"""Tests for multi-task scheduling configuration."""

import os
import unittest
from unittest.mock import patch


class MultiTaskConfigTestCase(unittest.TestCase):
    def test_config_has_watchlist_analysis_time(self):
        """Test that Config dataclass has watchlist_analysis_time field."""
        from src.config import Config

        config = Config()
        self.assertTrue(hasattr(config, "watchlist_analysis_time"))
        self.assertEqual(config.watchlist_analysis_time, "")

    def test_config_has_market_review_time(self):
        """Test that Config dataclass has market_review_time field."""
        from src.config import Config

        config = Config()
        self.assertTrue(hasattr(config, "market_review_time"))
        self.assertEqual(config.market_review_time, "")

    def test_config_watchlist_analysis_time_from_env(self):
        """Test that watchlist_analysis_time can be loaded from env."""
        from src.config import Config

        with patch.dict(os.environ, {"WATCHLIST_ANALYSIS_TIME": "09:00"}):
            config = Config._load_from_env()
            self.assertEqual(config.watchlist_analysis_time, "09:00")

    def test_config_market_review_time_from_env(self):
        """Test that market_review_time can be loaded from env."""
        from src.config import Config

        with patch.dict(os.environ, {"MARKET_REVIEW_TIME": "21:00"}):
            config = Config._load_from_env()
            self.assertEqual(config.market_review_time, "21:00")

    def test_config_empty_times_by_default(self):
        """Test that times are empty by default (disabled)."""
        from src.config import Config

        with patch.dict(os.environ, {}, clear=True):
            # Remove the env vars if they exist
            os.environ.pop("WATCHLIST_ANALYSIS_TIME", None)
            os.environ.pop("MARKET_REVIEW_TIME", None)
            config = Config()
            self.assertEqual(config.watchlist_analysis_time, "")
            self.assertEqual(config.market_review_time, "")


class MainScheduleModeMultiTaskTestCase(unittest.TestCase):
    def test_main_schedule_mode_uses_multi_task_when_configured(self):
        """Test that main.py uses multi-task mode when times are configured."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock the config with multi-task settings
        mock_config = MagicMock()
        mock_config.schedule_enabled = True
        mock_config.schedule_time = "18:00"
        mock_config.schedule_run_immediately = False
        mock_config.watchlist_analysis_time = "09:00"
        mock_config.market_review_time = "21:00"
        mock_config.stock_list = ["600519"]
        mock_config.agent_event_monitor_enabled = False

        # Track which mode was used
        call_tracker = {"mode": None}

        class FakeScheduler:
            def __init__(self, **kwargs):
                pass

            def add_daily_task(self, name, task, schedule_time, run_immediately=False):
                call_tracker["mode"] = "multi_task"
                call_tracker[f"task_{name}"] = schedule_time
                return True

            def add_background_task(self, **kwargs):
                pass

            def set_daily_task(self, task, run_immediately=True):
                call_tracker["mode"] = "single_task"

            def run(self):
                pass

        with patch("src.scheduler.Scheduler", FakeScheduler):
            from src import scheduler as scheduler_module

            # Test multi-task mode
            scheduler_module.run_with_schedule(
                daily_tasks=[
                    {
                        "name": "watchlist",
                        "task": lambda: None,
                        "schedule_time": "09:00",
                    },
                    {"name": "market", "task": lambda: None, "schedule_time": "21:00"},
                ],
            )

        self.assertEqual(call_tracker["mode"], "multi_task")
        self.assertEqual(call_tracker["task_watchlist"], "09:00")
        self.assertEqual(call_tracker["task_market"], "21:00")


if __name__ == "__main__":
    unittest.main()
