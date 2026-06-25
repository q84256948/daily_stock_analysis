# -*- coding: utf-8 -*-
"""Schedule status and manual trigger endpoints."""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_config_dep
from src.config import Config
from src.repositories.scheduled_task_log_repo import ScheduledTaskLogRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_TASKS = {"watchlist", "market_review"}


class ScheduleStatusResponse(BaseModel):
    recent_logs: list[Dict[str, Any]]
    next_runs: Dict[str, Optional[str]]
    health: Dict[str, Any]


class ScheduleTriggerRequest(BaseModel):
    task: str = Field(..., description="Task name: watchlist or market_review")


class ScheduleTriggerResponse(BaseModel):
    message: str
    task: str
    triggered_at: str


class ScheduleLogsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    logs: list[Dict[str, Any]]


@router.get(
    "/status",
    response_model=ScheduleStatusResponse,
    summary="Get scheduler status",
    description="Returns recent execution logs, next scheduled runs, and health.",
)
def get_schedule_status(
    config: Config = Depends(get_config_dep),
) -> ScheduleStatusResponse:
    repo = ScheduledTaskLogRepository()

    recent_logs = []
    for entry in repo.get_recent(limit=10):
        recent_logs.append(entry.to_dict())

    next_runs: Dict[str, Optional[str]] = {
        "watchlist": None,
        "market_review": None,
    }
    watchlist_time = getattr(config, "watchlist_analysis_time", "") or ""
    if watchlist_time.strip():
        next_runs["watchlist"] = watchlist_time.strip()
    market_time = getattr(config, "market_review_time", "") or ""
    if market_time.strip():
        next_runs["market_review"] = market_time.strip()

    heartbeat_path = Path(getattr(config, "database_path", "./data/stock_analysis.db")).parent / "scheduler_heartbeat"
    health_status = "unknown"
    last_heartbeat = None
    try:
        if heartbeat_path.exists():
            raw = heartbeat_path.read_text(encoding="utf-8").strip()
            last_heartbeat = raw.splitlines()[0] if raw else None
            health_status = "healthy"
    except OSError:
        pass

    return ScheduleStatusResponse(
        recent_logs=recent_logs,
        next_runs=next_runs,
        health={
            "status": health_status,
            "last_heartbeat": last_heartbeat,
        },
    )


@router.post(
    "/trigger",
    response_model=ScheduleTriggerResponse,
    summary="Manually trigger a scheduled task",
    description="Triggers watchlist or market_review task immediately. "
    "Returns 409 if the task is already running.",
)
def trigger_task(
    request: ScheduleTriggerRequest,
    config: Config = Depends(get_config_dep),
) -> ScheduleTriggerResponse:
    if request.task not in _VALID_TASKS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_task",
                "message": f"Task must be one of: {', '.join(sorted(_VALID_TASKS))}",
            },
        )

    from src.core.scheduled_task_lock import acquire_task_lock, release_task_lock

    lock_timeout = getattr(config, "schedule_lock_timeout", 7200)
    lock_token = acquire_task_lock(config, request.task, timeout_seconds=lock_timeout)
    if lock_token is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_task",
                "message": f"Task '{request.task}' is already running.",
            },
        )

    repo = ScheduledTaskLogRepository()
    now = datetime.now()
    try:
        repo.save(
            task_name=request.task,
            scheduled_at=now,
            status="running",
            started_at=now,
        )

        if request.task == "watchlist":
            _run_watchlist_task(config)
        else:
            _run_market_review_task(config)

        finished = datetime.now()
        repo.save(
            task_name=request.task,
            scheduled_at=now,
            status="success",
            started_at=now,
            finished_at=finished,
        )
    except Exception as exc:
        logger.exception("Manual trigger failed for %s: %s", request.task, exc)
        repo.save(
            task_name=request.task,
            scheduled_at=now,
            status="failed",
            detail={"error": str(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "trigger_failed",
                "message": f"Task '{request.task}' failed: {exc}",
            },
        )
    finally:
        release_task_lock(lock_token)

    return ScheduleTriggerResponse(
        message=f"Task '{request.task}' triggered successfully.",
        task=request.task,
        triggered_at=datetime.now().isoformat(),
    )


@router.get(
    "/logs",
    response_model=ScheduleLogsResponse,
    summary="Get schedule execution logs",
    description="Returns paginated schedule execution logs.",
)
def get_schedule_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    task_name: Optional[str] = Query(None, description="Filter by task name"),
) -> ScheduleLogsResponse:
    repo = ScheduledTaskLogRepository()
    logs = repo.get_recent(task_name=task_name, limit=page * page_size)
    start = (page - 1) * page_size
    page_logs = [entry.to_dict() for entry in logs[start : start + page_size]]

    return ScheduleLogsResponse(
        total=len(logs),
        page=page,
        page_size=page_size,
        logs=page_logs,
    )


def _build_default_args() -> argparse.Namespace:
    """Build a minimal args namespace for manual trigger (mirrors CLI defaults)."""
    return argparse.Namespace(
        no_notify=False,
        no_market_review=False,
        single_notify=False,
        force_run=True,
        no_run_immediately=True,
        schedule=False,
        debug=False,
        dry_run=False,
    )


def _run_watchlist_task(config: Config) -> None:
    """Execute the watchlist analysis task (manual trigger, no market review)."""
    from main import _reload_runtime_config, run_full_analysis

    runtime_config = _reload_runtime_config()
    args = _build_default_args()
    args.no_market_review = True
    run_full_analysis(runtime_config, args, None)


def _run_market_review_task(config: Config) -> None:
    """Execute the market review task (manual trigger)."""
    from main import _reload_runtime_config, _run_market_review_with_shared_lock
    from src.core.market_review import run_market_review
    from src.core.market_review_runtime import build_market_review_runtime

    runtime_config = _reload_runtime_config()
    notifier, analyzer, search_service = build_market_review_runtime(runtime_config)
    _run_market_review_with_shared_lock(
        runtime_config,
        run_market_review,
        notifier=notifier,
        analyzer=analyzer,
        search_service=search_service,
        send_notification=True,
        trigger_source="api",
    )
