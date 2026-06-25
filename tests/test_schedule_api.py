# -*- coding: utf-8 -*-
"""Tests for schedule API endpoints."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import create_app


def _make_client():
    temp_dir = tempfile.TemporaryDirectory()
    return temp_dir, TestClient(create_app(static_dir=Path(temp_dir.name)))


class ScheduleStatusEndpointTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir, cls.client = _make_client()

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    @patch("api.v1.endpoints.schedule.ScheduledTaskLogRepository")
    def test_get_schedule_status_returns_200(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo
        mock_repo.get_recent.return_value = []

        resp = self.client.get("/api/v1/schedule/status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("recent_logs", body)
        self.assertIn("next_runs", body)
        self.assertIn("health", body)

    @patch("api.v1.endpoints.schedule.ScheduledTaskLogRepository")
    def test_get_schedule_status_with_logs(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo
        mock_entry = MagicMock()
        mock_entry.to_dict.return_value = {
            "id": 1,
            "task_name": "watchlist_analysis",
            "status": "success",
        }
        mock_repo.get_recent.return_value = [mock_entry]

        resp = self.client.get("/api/v1/schedule/status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["recent_logs"]), 1)
        self.assertEqual(body["recent_logs"][0]["task_name"], "watchlist_analysis")


class ScheduleTriggerEndpointTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir, cls.client = _make_client()

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    @patch("src.core.scheduled_task_lock.acquire_task_lock")
    @patch("src.core.scheduled_task_lock.release_task_lock")
    @patch("api.v1.endpoints.schedule.ScheduledTaskLogRepository")
    @patch("api.v1.endpoints.schedule._run_watchlist_task")
    def test_trigger_watchlist_success(
        self, mock_run, MockRepo, mock_release, mock_acquire
    ):
        mock_acquire.return_value = MagicMock()
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo

        resp = self.client.post(
            "/api/v1/schedule/trigger",
            json={"task": "watchlist"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["task"], "watchlist")
        mock_run.assert_called_once()
        mock_release.assert_called_once()

    def test_trigger_invalid_task(self):
        resp = self.client.post(
            "/api/v1/schedule/trigger",
            json={"task": "invalid_task"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("src.core.scheduled_task_lock.acquire_task_lock")
    def test_trigger_duplicate_task(self, mock_acquire):
        mock_acquire.return_value = None
        resp = self.client.post(
            "/api/v1/schedule/trigger",
            json={"task": "watchlist"},
        )
        self.assertEqual(resp.status_code, 409)


class ScheduleLogsEndpointTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir, cls.client = _make_client()

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    @patch("api.v1.endpoints.schedule.ScheduledTaskLogRepository")
    def test_get_logs_returns_200(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo
        mock_repo.get_recent.return_value = []

        resp = self.client.get("/api/v1/schedule/logs")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("total", body)
        self.assertIn("logs", body)

    @patch("api.v1.endpoints.schedule.ScheduledTaskLogRepository")
    def test_get_logs_pagination(self, MockRepo):
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo
        mock_repo.get_recent.return_value = []

        resp = self.client.get("/api/v1/schedule/logs?page=2&page_size=10")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 10)
