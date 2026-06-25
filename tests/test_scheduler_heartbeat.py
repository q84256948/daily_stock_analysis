# -*- coding: utf-8 -*-
"""Tests for scheduler heartbeat mechanism."""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSchedulerHeartbeat:
    def test_heartbeat_file_written(self, tmp_path):
        from src.scheduler import Scheduler

        heartbeat_path = tmp_path / "heartbeat.json"
        scheduler = Scheduler(schedule_time="00:00", heartbeat_path=heartbeat_path)

        # Simulate one tick of the run loop
        scheduler._running = False  # Don't enter the while loop
        scheduler._write_heartbeat()

        assert heartbeat_path.exists()
        data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        assert "timestamp" in data
        assert "pid" in data
        assert "next_run" in data

    def test_heartbeat_no_path_is_noop(self):
        from src.scheduler import Scheduler

        scheduler = Scheduler(schedule_time="00:00", heartbeat_path=None)
        scheduler._write_heartbeat()  # Should not raise

    def test_heartbeat_registered_tasks(self, tmp_path):
        from src.scheduler import Scheduler

        heartbeat_path = tmp_path / "heartbeat.json"
        scheduler = Scheduler(schedule_time="00:00", heartbeat_path=heartbeat_path)

        # Add a dummy task callback
        scheduler._daily_task_callbacks["watchlist"] = lambda: None

        scheduler._write_heartbeat()

        data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        assert "watchlist" in data["registered_tasks"]

    def test_run_with_schedule_passes_heartbeat_path(self, tmp_path):
        from src.scheduler import Scheduler

        heartbeat_path = tmp_path / "hb.json"

        # Verify Scheduler accepts heartbeat_path parameter
        scheduler = Scheduler(
            schedule_time="00:00",
            heartbeat_path=heartbeat_path,
        )
        assert scheduler._heartbeat_path == heartbeat_path
