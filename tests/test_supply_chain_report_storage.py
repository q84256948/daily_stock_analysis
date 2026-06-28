# -*- coding: utf-8 -*-
"""供应链分析报告 — storage 层 CRUD 单元测试（真实内存 SQLite）。

镜像 tests/test_policy_minesweeper_storage.py 的 DatabaseManager(db_url="sqlite:///:memory:")
模式，覆盖新增 6 个 CRUD 方法 + to_dict + 异常分支，不依赖 LLM/网络。
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.storage import DatabaseManager, SupplyChainReport


@pytest.fixture
def db():
    """每个测试一个全新的内存 SQLite 实例。"""
    DatabaseManager.reset_instance()
    inst = DatabaseManager(db_url="sqlite:///:memory:")
    yield inst
    DatabaseManager.reset_instance()


def _save_sample(
    db: DatabaseManager,
    report_id: str = "sc_202606271530_1",
    topic: str = "A 股 AI 半导体供应链",
    **overrides: Any,
) -> bool:
    kwargs: Dict[str, Any] = dict(
        report_id=report_id,
        topic=topic,
        research_hint="重点验证 CPO 光模块上游",
        md_path=f"/tmp/{report_id}.md",
        status="success",
        total_steps=24,
        total_tokens=12000,
        provider="test",
        model="test-model",
        error=None,
    )
    kwargs.update(overrides)
    return db.save_supply_chain_report(**kwargs)


# ============================================================
# save / get 闭环
# ============================================================

class TestSaveGet:
    def test_save_then_get_roundtrip(self, db):
        assert _save_sample(db) is True
        rec = db.get_supply_chain_report("sc_202606271530_1")
        assert rec is not None
        assert rec.topic == "A 股 AI 半导体供应链"
        assert rec.research_hint == "重点验证 CPO 光模块上游"
        assert rec.total_steps == 24
        assert rec.provider == "test"
        assert rec.model == "test-model"
        assert isinstance(rec, SupplyChainReport)

    def test_save_merge_upsert_same_id(self, db):
        _save_sample(db, status="success", total_steps=10)
        # 同 id 再存 → 覆盖
        _save_sample(db, status="partial", total_steps=24)
        rec = db.get_supply_chain_report("sc_202606271530_1")
        assert rec.status == "partial" and rec.total_steps == 24
        # 仍是 1 条（merge 不新增）
        _, total = db.get_supply_chain_reports()
        assert total == 1

    def test_get_missing_returns_none(self, db):
        assert db.get_supply_chain_report("nope") is None

    def test_save_nullable_hint_and_model(self, db):
        _save_sample(db, research_hint=None, model=None)
        rec = db.get_supply_chain_report("sc_202606271530_1")
        assert rec.research_hint is None and rec.model is None


# ============================================================
# 列表（分页/倒序）
# ============================================================

class TestList:
    def test_list_pagination_and_order(self, db):
        _save_sample(db, report_id="sc_202606270900_1")
        _save_sample(db, report_id="sc_202606271000_1")
        _save_sample(db, report_id="sc_202606271100_1")
        rows, total = db.get_supply_chain_reports(limit=10)
        assert total == 3
        assert len(rows) == 3

    def test_list_offset_limit(self, db):
        for i in range(5):
            _save_sample(db, report_id=f"sc_2026062711{i:02d}_1")
        rows, total = db.get_supply_chain_reports(offset=1, limit=2)
        assert total == 5
        assert len(rows) == 2


# ============================================================
# to_dict
# ============================================================

class TestToDict:
    def test_to_dict_shape(self, db):
        _save_sample(db)
        rec = db.get_supply_chain_report("sc_202606271530_1")
        d = rec.to_dict()
        assert d["id"] == "sc_202606271530_1"
        assert d["topic"] == "A 股 AI 半导体供应链"
        assert d["research_hint"] == "重点验证 CPO 光模块上游"
        assert d["pdf_path"] is None
        assert d["status"] == "success"
        assert "created_at" in d and d["created_at"] is not None


# ============================================================
# set_pdf_path / delete
# ============================================================

class TestPdfAndDelete:
    def test_set_pdf_path(self, db):
        _save_sample(db)
        assert db.set_supply_chain_pdf_path("sc_202606271530_1", "/tmp/x.pdf") is True
        rec = db.get_supply_chain_report("sc_202606271530_1")
        assert rec.pdf_path == "/tmp/x.pdf"

    def test_set_pdf_path_missing_returns_false(self, db):
        assert db.set_supply_chain_pdf_path("nope", "/tmp/x.pdf") is False

    def test_delete_returns_paths(self, db):
        _save_sample(db, md_path="/tmp/a.md")
        paths = db.delete_supply_chain_report("sc_202606271530_1")
        assert paths == {"md_path": "/tmp/a.md", "pdf_path": None}
        assert db.get_supply_chain_report("sc_202606271530_1") is None

    def test_delete_missing_returns_none(self, db):
        assert db.delete_supply_chain_report("nope") is None


# ============================================================
# prune
# ============================================================

class TestPrune:
    def test_prune_no_excess_returns_empty(self, db):
        _save_sample(db)
        assert db.prune_supply_chain_reports(10) == []

    def test_prune_zero_or_negative_returns_empty(self, db):
        _save_sample(db)
        assert db.prune_supply_chain_reports(0) == []
        assert db.prune_supply_chain_reports(-1) == []

    def test_prune_removes_oldest(self, db):
        # 插 3 条，max=1 → 应删最旧 2 条。返回被删记录的 paths。
        for rid in ["sc_202606270900_1", "sc_202606271000_1", "sc_202606271100_1"]:
            _save_sample(db, report_id=rid, md_path=f"/tmp/{rid}.md")
        pruned = db.prune_supply_chain_reports(1)
        assert len(pruned) == 2
        assert all(p["md_path"].startswith("/tmp/") for p in pruned)
        _, total = db.get_supply_chain_reports()
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
        assert db.set_supply_chain_pdf_path("sc_202606271530_1", "/tmp/x.pdf") is False

    def test_delete_error_returns_none(self, db, monkeypatch):
        _save_sample(db)

        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert db.delete_supply_chain_report("sc_202606271530_1") is None

    def test_prune_error_returns_empty(self, db, monkeypatch):
        _save_sample(db)

        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "_run_write_transaction", _boom)
        assert db.prune_supply_chain_reports(0) == []  # 早返，不进事务
        assert db.prune_supply_chain_reports(10) == []  # 进入事务路径再抛
