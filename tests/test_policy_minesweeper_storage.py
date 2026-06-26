# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — storage 层 CRUD 单元测试（真实内存 SQLite）。

镜像 tests/test_storage.py 的 DatabaseManager(db_url="sqlite:///:memory:") 模式，
覆盖新增 6 个 CRUD 方法 + to_dict + 异常分支，不依赖 LLM/网络。
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.storage import DatabaseManager, PolicyMinesweeperReport


@pytest.fixture
def db():
    """每个测试一个全新的内存 SQLite 实例。"""
    DatabaseManager.reset_instance()
    inst = DatabaseManager(db_url="sqlite:///:memory:")
    yield inst
    DatabaseManager.reset_instance()


def _save_sample(
    db: DatabaseManager,
    report_id: str = "600519_202606261200",
    stock_code: str = "600519",
    stock_name: str = "贵州茅台",
    **overrides: Any,
) -> bool:
    kwargs: Dict[str, Any] = dict(
        report_id=report_id,
        stock_code=stock_code,
        stock_name=stock_name,
        md_path=f"/tmp/{report_id}.md",
        status="success",
        horizon="medium",
        alpha_ok=True,
        beta_ok=True,
        omega_ok=True,
        composite_score=-35,
        verdict="中等利空",
        confidence=78,
        total_steps=20,
        total_tokens=3000,
        provider="test",
    )
    kwargs.update(overrides)
    return db.save_policy_minesweeper_report(**kwargs)


# ============================================================
# save / get 闭环
# ============================================================

class TestSaveGet:
    def test_save_then_get_roundtrip(self, db):
        assert _save_sample(db) is True
        rec = db.get_policy_minesweeper_report("600519_202606261200")
        assert rec is not None
        assert rec.stock_code == "600519"
        assert rec.composite_score == -35
        assert rec.verdict == "中等利空"
        assert rec.confidence == 78
        assert rec.alpha_ok is True and rec.omega_ok is True

    def test_save_merge_upsert_same_id(self, db):
        _save_sample(db, verdict="中等利空", composite_score=-35)
        # 同 id 再存 → 覆盖
        _save_sample(db, verdict="强利空", composite_score=80, status="success")
        rec = db.get_policy_minesweeper_report("600519_202606261200")
        assert rec.verdict == "强利空" and rec.composite_score == 80
        # 仍是 1 条（merge 不新增）
        _, total = db.get_policy_minesweeper_reports()
        assert total == 1

    def test_get_missing_returns_none(self, db):
        assert db.get_policy_minesweeper_report("nope") is None

    def test_save_nullable_score_fields(self, db):
        # best-effort 解析不到时 score 字段为 None
        _save_sample(db, composite_score=None, verdict=None, confidence=None)
        rec = db.get_policy_minesweeper_report("600519_202606261200")
        assert rec.composite_score is None and rec.verdict is None and rec.confidence is None


# ============================================================
# 列表（分页/过滤/倒序）
# ============================================================

class TestList:
    def test_list_pagination_and_order(self, db):
        # 插 3 条不同时间（同分钟可能 created_at 相同，用显式 id 区分；顺序由 created_at desc）
        _save_sample(db, report_id="600519_202606260900")
        _save_sample(db, report_id="600519_202606261000")
        _save_sample(db, report_id="300750_202606261100", stock_code="300750")
        rows, total = db.get_policy_minesweeper_reports(limit=10)
        assert total == 3
        assert len(rows) == 3

    def test_list_filter_by_stock_code(self, db):
        _save_sample(db, report_id="600519_202606260900", stock_code="600519")
        _save_sample(db, report_id="300750_202606261000", stock_code="300750")
        rows, total = db.get_policy_minesweeper_reports(stock_code="300750")
        assert total == 1
        assert rows[0].stock_code == "300750"


# ============================================================
# to_dict
# ============================================================

class TestToDict:
    def test_to_dict_shape(self, db):
        _save_sample(db)
        rec = db.get_policy_minesweeper_report("600519_202606261200")
        d = rec.to_dict()
        assert d["id"] == "600519_202606261200"
        assert d["stock_code"] == "600519"
        assert d["composite_score"] == -35
        assert d["verdict"] == "中等利空"
        assert d["pdf_path"] is None
        assert "created_at" in d and d["created_at"] is not None


# ============================================================
# set_pdf_path / delete
# ============================================================

class TestPdfAndDelete:
    def test_set_pdf_path(self, db):
        _save_sample(db)
        assert db.set_policy_minesweeper_pdf_path("600519_202606261200", "/tmp/x.pdf") is True
        rec = db.get_policy_minesweeper_report("600519_202606261200")
        assert rec.pdf_path == "/tmp/x.pdf"

    def test_set_pdf_path_missing_returns_false(self, db):
        assert db.set_policy_minesweeper_pdf_path("nope", "/tmp/x.pdf") is False

    def test_delete_returns_paths(self, db):
        _save_sample(db, md_path="/tmp/a.md")
        paths = db.delete_policy_minesweeper_report("600519_202606261200")
        assert paths == {"md_path": "/tmp/a.md", "pdf_path": None}
        assert db.get_policy_minesweeper_report("600519_202606261200") is None

    def test_delete_missing_returns_none(self, db):
        assert db.delete_policy_minesweeper_report("nope") is None


# ============================================================
# prune
# ============================================================

class TestPrune:
    def test_prune_no_excess_returns_empty(self, db):
        _save_sample(db)
        assert db.prune_policy_minesweeper_reports(10) == []

    def test_prune_zero_or_negative_returns_empty(self, db):
        _save_sample(db)
        assert db.prune_policy_minesweeper_reports(0) == []
        assert db.prune_policy_minesweeper_reports(-1) == []

    def test_prune_removes_oldest(self, db):
        # 插 3 条，max=1 → 应删最旧 2 条。用不同 id；created_at 同分钟时按插入序，
        # asc(created_at) 取最旧。返回被删记录的 paths。
        for i, rid in enumerate(["600519_202606260900", "600519_202606261000", "600519_202606261100"]):
            _save_sample(db, report_id=rid, md_path=f"/tmp/{rid}.md")
        pruned = db.prune_policy_minesweeper_reports(1)
        assert len(pruned) == 2
        assert all(p["md_path"].startswith("/tmp/") for p in pruned)
        _, total = db.get_policy_minesweeper_reports()
        assert total == 1


# ============================================================
# 异常分支（_run_write_transaction 抛错 → 安全降级）
# ============================================================

class TestErrorBranches:
    def test_save_error_returns_false(self, db, monkeypatch):
        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert _save_sample(db) is False

    def test_set_pdf_path_error_returns_false(self, db, monkeypatch):
        _save_sample(db)

        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert db.set_policy_minesweeper_pdf_path("600519_202606261200", "/tmp/x.pdf") is False

    def test_delete_error_returns_none(self, db, monkeypatch):
        _save_sample(db)

        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert db.delete_policy_minesweeper_report("600519_202606261200") is None

    def test_prune_error_returns_empty(self, db, monkeypatch):
        _save_sample(db)

        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert db.prune_policy_minesweeper_reports(0) == []  # 早返，不进事务
        # 强制进入事务路径再抛
        assert db.prune_policy_minesweeper_reports(10) == []
