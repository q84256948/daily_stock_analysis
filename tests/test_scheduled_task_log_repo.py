# -*- coding: utf-8 -*-
"""Tests for src/repositories/scheduled_task_log_repo.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.storage import ScheduledTaskLog


@pytest.fixture
def mock_db_manager():
    """Return a mock DatabaseManager."""
    db = MagicMock()
    session = MagicMock()
    db.get_session.return_value = session
    return db, session


class TestScheduledTaskLogRepository:
    def test_save_creates_entry(self, mock_db_manager):
        db, session = mock_db_manager
        from src.repositories.scheduled_task_log_repo import ScheduledTaskLogRepository

        repo = ScheduledTaskLogRepository(db_manager=db)
        now = datetime.now()
        entry_id = repo.save(
            task_name="watchlist_analysis",
            scheduled_at=now,
            status="success",
            started_at=now,
            finished_at=now,
            detail={"total": 3, "success": 3, "failed": 0},
            report_path="/tmp/report.md",
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_save_rolls_back_on_error(self, mock_db_manager):
        db, session = mock_db_manager
        session.commit.side_effect = Exception("db error")
        from src.repositories.scheduled_task_log_repo import ScheduledTaskLogRepository

        repo = ScheduledTaskLogRepository(db_manager=db)
        now = datetime.now()

        with pytest.raises(Exception, match="db error"):
            repo.save(
                task_name="test",
                scheduled_at=now,
                status="failed",
            )

        session.rollback.assert_called_once()
        session.close.assert_called_once()

    def test_get_recent(self, mock_db_manager):
        db, session = mock_db_manager
        mock_entry = MagicMock(spec=ScheduledTaskLog)
        mock_entry.to_dict.return_value = {"task_name": "test"}
        query_mock = MagicMock()
        query_mock.order_by.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.limit.return_value.all.return_value = [mock_entry]
        session.query.return_value = query_mock

        from src.repositories.scheduled_task_log_repo import ScheduledTaskLogRepository

        repo = ScheduledTaskLogRepository(db_manager=db)
        results = repo.get_recent(task_name="test", limit=5)

        assert len(results) == 1
        session.close.assert_called_once()

    def test_get_latest_by_task(self, mock_db_manager):
        db, session = mock_db_manager
        mock_entry = MagicMock(spec=ScheduledTaskLog)
        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.first.return_value = mock_entry
        session.query.return_value = query_mock

        from src.repositories.scheduled_task_log_repo import ScheduledTaskLogRepository

        repo = ScheduledTaskLogRepository(db_manager=db)
        result = repo.get_latest_by_task("watchlist_analysis")

        assert result is mock_entry
        session.close.assert_called_once()
