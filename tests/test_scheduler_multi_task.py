# -*- coding: utf-8 -*-
"""Tests for Scheduler multi-task support."""

from datetime import datetime
import sys
import unittest
from unittest.mock import MagicMock, patch


class _FakeJob:
    def __init__(self, schedule_module):
        self._schedule_module = schedule_module
        self.next_run = datetime(2026, 1, 1, 18, 0, 0)
        self.at_time = None

    @property
    def day(self):
        return self

    def at(self, value):
        self.at_time = value
        hour, minute = [int(part) for part in value.split(":")]
        self.next_run = datetime(2026, 1, 1, hour, minute, 0)
        return self

    def do(self, fn, *args, **kwargs):
        self.job_func = fn
        self.job_args = args
        self.job_kwargs = kwargs
        self._schedule_module.jobs.append(self)
        return self


class _FakeScheduleModule:
    def __init__(self):
        self.jobs = []

    def every(self):
        return _FakeJob(self)

    def get_jobs(self):
        return list(self.jobs)

    def run_pending(self):
        return None

    def cancel_job(self, job):
        self.jobs.remove(job)


class SchedulerMultiTaskTestCase(unittest.TestCase):
    def test_add_daily_task_success(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()
            calls = []

            result = scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: calls.append("watchlist"),
                schedule_time="09:00",
                run_immediately=False,
            )

        self.assertTrue(result)
        self.assertEqual(len(fake_schedule.jobs), 1)
        self.assertEqual(fake_schedule.jobs[0].at_time, "09:00")

    def test_add_daily_task_invalid_time(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()

            result = scheduler.add_daily_task(
                name="invalid_task",
                task=lambda: None,
                schedule_time="25:99",
                run_immediately=False,
            )

        self.assertFalse(result)
        self.assertEqual(len(fake_schedule.jobs), 0)

    def test_add_multiple_daily_tasks(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()

            result1 = scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: None,
                schedule_time="09:00",
                run_immediately=False,
            )
            result2 = scheduler.add_daily_task(
                name="market_review",
                task=lambda: None,
                schedule_time="21:00",
                run_immediately=False,
            )

        self.assertTrue(result1)
        self.assertTrue(result2)
        self.assertEqual(len(fake_schedule.jobs), 2)
        self.assertEqual(fake_schedule.jobs[0].at_time, "09:00")
        self.assertEqual(fake_schedule.jobs[1].at_time, "21:00")

    def test_add_daily_task_replaces_same_name(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()

            scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: None,
                schedule_time="09:00",
                run_immediately=False,
            )
            scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: None,
                schedule_time="10:00",
                run_immediately=False,
            )

        self.assertEqual(len(fake_schedule.jobs), 1)
        self.assertEqual(fake_schedule.jobs[0].at_time, "10:00")

    def test_add_daily_task_run_immediately(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()
            calls = []

            scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: calls.append("ran"),
                schedule_time="09:00",
                run_immediately=True,
            )

        self.assertEqual(calls, ["ran"])

    def test_safe_run_named_task_catches_exception(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()
            scheduler.add_daily_task(
                name="failing_task",
                task=lambda: 1 / 0,
                schedule_time="09:00",
                run_immediately=False,
            )

            # Should not raise
            scheduler._safe_run_named_task("failing_task")

    def test_safe_run_named_task_nonexistent(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()

            # Should not raise
            scheduler._safe_run_named_task("nonexistent")

    def test_cancel_named_daily_job(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()
            scheduler.add_daily_task(
                name="watchlist_analysis",
                task=lambda: None,
                schedule_time="09:00",
                run_immediately=False,
            )
            scheduler._cancel_named_daily_job("watchlist_analysis")

        self.assertEqual(len(fake_schedule.jobs), 0)
        self.assertNotIn("watchlist_analysis", scheduler._daily_task_callbacks)

    def test_cancel_named_daily_job_nonexistent(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src.scheduler import Scheduler

            scheduler = Scheduler()

            # Should not raise
            scheduler._cancel_named_daily_job("nonexistent")


class RunWithScheduleMultiTaskTestCase(unittest.TestCase):
    def test_run_with_schedule_daily_tasks(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src import scheduler as scheduler_module

            order = []

            class FakeScheduler:
                def __init__(self, schedule_time="18:00", schedule_time_provider=None, heartbeat_path=None):
                    order.append(("init", schedule_time))

                def add_background_task(self, **kwargs):
                    order.append(("background", kwargs["name"]))

                def add_daily_task(
                    self, name, task, schedule_time, run_immediately=False
                ):
                    order.append(("daily_task", name, schedule_time))
                    return True

                def set_daily_task(self, task, run_immediately=True):
                    order.append(("daily", run_immediately))

                def run(self):
                    order.append(("run", None))

            with patch.object(scheduler_module, "Scheduler", FakeScheduler):
                scheduler_module.run_with_schedule(
                    daily_tasks=[
                        {
                            "name": "watchlist_analysis",
                            "task": lambda: None,
                            "schedule_time": "09:00",
                        },
                        {
                            "name": "market_review",
                            "task": lambda: None,
                            "schedule_time": "21:00",
                        },
                    ],
                    background_tasks=[
                        {
                            "task": lambda: None,
                            "interval_seconds": 60,
                            "run_immediately": True,
                            "name": "event_monitor",
                        },
                    ],
                )

        self.assertEqual(order[0], ("init", "18:00"))
        self.assertEqual(order[1], ("background", "event_monitor"))
        self.assertEqual(order[2], ("daily_task", "watchlist_analysis", "09:00"))
        self.assertEqual(order[3], ("daily_task", "market_review", "21:00"))
        self.assertEqual(order[4], ("run", None))
        # Should not call set_daily_task in multi-task mode
        self.assertFalse(any(x[0] == "daily" for x in order))

    def test_run_with_schedule_single_task_backward_compatible(self):
        fake_schedule = _FakeScheduleModule()
        with patch.dict(sys.modules, {"schedule": fake_schedule}):
            from src import scheduler as scheduler_module

            order = []

            class FakeScheduler:
                def __init__(self, schedule_time="18:00", schedule_time_provider=None, heartbeat_path=None):
                    order.append(("init", schedule_time))

                def add_background_task(self, **kwargs):
                    order.append(("background", kwargs["name"]))

                def add_daily_task(
                    self, name, task, schedule_time, run_immediately=False
                ):
                    order.append(("daily_task", name, schedule_time))
                    return True

                def set_daily_task(self, task, run_immediately=True):
                    order.append(("daily", run_immediately))

                def run(self):
                    order.append(("run", None))

            with patch.object(scheduler_module, "Scheduler", FakeScheduler):
                scheduler_module.run_with_schedule(
                    task=lambda: None,
                    schedule_time="18:00",
                    run_immediately=True,
                )

        self.assertEqual(order[0], ("init", "18:00"))
        self.assertEqual(order[1], ("daily", True))
        self.assertEqual(order[2], ("run", None))
        # Should not call add_daily_task in single-task mode
        self.assertFalse(any(x[0] == "daily_task" for x in order))


if __name__ == "__main__":
    unittest.main()
