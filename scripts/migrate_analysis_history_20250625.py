#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate analysis_history and scheduled_task_log tables for 2025-06-25 schema.

The analysis_history model gained five new Text columns for long-term research
framework output. Existing SQLite databases created before this change will fail
to save reports with:

    sqlite3.OperationalError: table analysis_history has no column named ...

This script adds the missing columns idempotently and creates the
scheduled_task_log table if it does not exist yet.

Usage:
    python scripts/migrate_analysis_history_20250625.py
"""

import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Resolve the SQLite database path used by the application."""
    # Prefer the path defined by environment; default to project data dir.
    db_path = Path(__file__).parent.parent / "data" / "stock_analysis.db"
    env_db = __import__("os").environ.get("DATABASE_PATH")
    if env_db:
        db_path = Path(env_db)
    return db_path


def migrate_analysis_history(conn: sqlite3.Connection) -> None:
    """Add missing long-term-research columns to analysis_history."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(analysis_history)")
    existing = {row[1] for row in cursor.fetchall()}

    required = {
        "research_framework": "TEXT",
        "bayesian_framework": "TEXT",
        "supply_chain": "TEXT",
        "value_scenarios": "TEXT",
        "investment_conclusion": "TEXT",
    }

    for column, dtype in required.items():
        if column in existing:
            print(f"[SKIP] analysis_history.{column} already exists")
            continue
        cursor.execute(f"ALTER TABLE analysis_history ADD COLUMN {column} {dtype}")
        print(f"[ADD]  analysis_history.{column} {dtype}")

    conn.commit()


def migrate_scheduled_task_log(conn: sqlite3.Connection) -> None:
    """Create scheduled_task_log table if it does not exist."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_task_log'"
    )
    if cursor.fetchone():
        print("[SKIP] scheduled_task_log table already exists")
        return

    cursor.execute(
        """
        CREATE TABLE scheduled_task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name VARCHAR(32) NOT NULL,
            scheduled_at DATETIME NOT NULL,
            started_at DATETIME,
            finished_at DATETIME,
            status VARCHAR(16) NOT NULL,
            detail TEXT,
            report_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX ix_sched_task_name_time ON scheduled_task_log (task_name, scheduled_at)"
    )
    conn.commit()
    print("[CREATE] scheduled_task_log table and index")


def main() -> int:
    db_path = get_db_path()
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        return 1

    print(f"[INFO] Migrating database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        migrate_analysis_history(conn)
        migrate_scheduled_task_log(conn)
    finally:
        conn.close()

    print("[DONE] Migration completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
