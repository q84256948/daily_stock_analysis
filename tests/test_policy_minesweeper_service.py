# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — 编排服务单元测试。

mock get_db + _get_executor，覆盖 generate/list/get/delete/pdf 编排、
A 股归一化、report_id 唯一化、名称反查、score 解析。不依赖真实 LLM/网络/DB。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.agent.policy_minesweeper_executor import PolicyMinesweeperResult
from src.services import policy_minesweeper_service as svc_mod
from src.services.policy_minesweeper_service import (
    PolicyMinesweeperInputError,
    PolicyMinesweeperService,
    extract_score,
    normalize_a_share,
)


# banner 示例（scorecard to_markdown 产出格式）
_BANNER_MD = (
    "# 政策与公告双维度排雷：示例（300750）\n\n"
    "🟠 **中等利空**　综合分 **-35**　置信度 **78%**\n"
    "仓位指令：**减持**\n"
)


def _fake_result(**kw: Any) -> PolicyMinesweeperResult:
    base = dict(
        success=True, status="success", markdown=_BANNER_MD,
        stock_code="300750", stock_name="示例", horizon="medium",
        alpha_ok=True, beta_ok=True, omega_ok=True,
        total_steps=20, total_tokens=3000, provider="test",
    )
    base.update(kw)
    return PolicyMinesweeperResult(**base)


# ============================================================
# A 股归一化
# ============================================================

class TestNormalizeAShare:
    def test_valid_a_share(self):
        assert normalize_a_share("600519") == "600519"
        assert normalize_a_share(" 300750 ") == "300750"

    def test_non_a_share_rejected(self):
        for bad in ("hk00700", "AAPL", "00700"):
            with pytest.raises(PolicyMinesweeperInputError):
                normalize_a_share(bad)

    def test_empty_rejected(self):
        with pytest.raises(PolicyMinesweeperInputError):
            normalize_a_share("")
        with pytest.raises(PolicyMinesweeperInputError):
            normalize_a_share("   ")


# ============================================================
# report_id 唯一化
# ============================================================

class TestResolveUniqueReportId:
    def test_absent_unchanged(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        from src.services.policy_minesweeper_service import _resolve_unique_report_id

        assert _resolve_unique_report_id("300750_202606261200") == "300750_202606261200"

    def test_conflict_appends_sequence(self, monkeypatch):
        existing = {"300750_202606261200": True, "300750_202606261200_1": True}
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.side_effect = (
            lambda rid: object() if existing.get(rid) else None
        )
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        from src.services.policy_minesweeper_service import _resolve_unique_report_id

        assert _resolve_unique_report_id("300750_202606261200") == "300750_202606261200_2"


# ============================================================
# 名称反查
# ============================================================

class TestLookupStockName:
    def test_returns_name(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr.return_value.get_realtime_quote.return_value = SimpleNamespace(name="宁德时代")
        monkeypatch.setattr("src.agent.tools.data_tools._get_fetcher_manager", mock_mgr)
        from src.services.policy_minesweeper_service import _lookup_stock_name

        assert _lookup_stock_name("300750") == "宁德时代"

    def test_returns_empty_on_failure(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr.return_value.get_realtime_quote.side_effect = RuntimeError("net down")
        monkeypatch.setattr("src.agent.tools.data_tools._get_fetcher_manager", mock_mgr)
        from src.services.policy_minesweeper_service import _lookup_stock_name

        assert _lookup_stock_name("300750") == ""


# ============================================================
# score 解析
# ============================================================

class TestExtractScore:
    def test_full_banner_parsed(self):
        s = extract_score(_BANNER_MD)
        assert s == {"composite_score": -35, "verdict": "中等利空", "confidence": 78}

    def test_partial_banner(self):
        s = extract_score("综合分 **42**")
        assert s["composite_score"] == 42 and s["verdict"] is None and s["confidence"] is None

    def test_garbage_returns_none(self):
        s = extract_score("没有分数的纯文本")
        assert s == {"composite_score": None, "verdict": None, "confidence": None}

    def test_empty_returns_none(self):
        assert extract_score("") == {"composite_score": None, "verdict": None, "confidence": None}


# ============================================================
# generate_report
# ============================================================

class TestGenerateReport:
    def _wire(self, monkeypatch, tmp_path, result):
        fake_executor = MagicMock()
        fake_executor.generate.return_value = result
        monkeypatch.setattr(svc_mod, "_get_executor", lambda: fake_executor)
        monkeypatch.setattr(svc_mod, "get_policy_minesweeper_dir", lambda: tmp_path)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = None
        mock_db.prune_policy_minesweeper_reports.return_value = []
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        return mock_db

    def test_success_writes_md_and_saves_with_score(self, monkeypatch, tmp_path):
        mock_db = self._wire(monkeypatch, tmp_path, _fake_result())
        saved: Dict[str, Any] = {}
        mock_db.save_policy_minesweeper_report.side_effect = lambda **kw: (saved.update(kw), True)[1]

        out = PolicyMinesweeperService().generate_report("300750", "示例", horizon="medium")

        assert out["status"] == "success"
        assert out["composite_score"] == -35 and out["verdict"] == "中等利空" and out["confidence"] == 78
        assert out["report_id"] and (tmp_path / f"{out['report_id']}.md").exists()
        assert saved["composite_score"] == -35 and saved["stock_code"] == "300750"

    def test_non_a_share_raises(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        with pytest.raises(PolicyMinesweeperInputError):
            PolicyMinesweeperService().generate_report("AAPL", "Apple")

    def test_write_fail_skips_save(self, monkeypatch, tmp_path):
        mock_db = self._wire(monkeypatch, tmp_path, _fake_result())

        def _boom(_self, _path, *_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", _boom)
        out = PolicyMinesweeperService().generate_report("300750", "示例")
        assert out["report_id"] is None
        mock_db.save_policy_minesweeper_report.assert_not_called()

    def test_empty_name_triggers_lookup(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        mock_mgr = MagicMock()
        mock_mgr.return_value.get_realtime_quote.return_value = SimpleNamespace(name="宁德时代")
        monkeypatch.setattr("src.agent.tools.data_tools._get_fetcher_manager", mock_mgr)

        out = PolicyMinesweeperService().generate_report("300750", "")
        assert out["stock_name"] == "宁德时代"

    def test_done_progress_event(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        events = []
        PolicyMinesweeperService().generate_report(
            "300750", "示例", progress_callback=events.append
        )
        assert any(e.get("type") == "done" for e in events)


# ============================================================
# list / get / delete / pdf（代理层）
# ============================================================

class TestProxies:
    def test_list_reports(self, monkeypatch):
        rec = MagicMock()
        rec.to_dict.return_value = {"id": "x"}
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_reports.return_value = ([rec], 1)
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        rows, total = PolicyMinesweeperService().list_reports()
        assert total == 1 and rows == [{"id": "x"}]

    def test_get_report_reads_markdown(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.to_dict.return_value = {"id": "r"}
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        data = PolicyMinesweeperService().get_report("r")
        assert data["markdown"] == "# 正文"

    def test_get_report_missing(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().get_report("nope") is None

    def test_delete_report(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_policy_minesweeper_report.return_value = {"md_path": "/tmp/a.md", "pdf_path": None}
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().delete_report("r") is True

    def test_delete_report_missing(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_policy_minesweeper_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().delete_report("nope") is False


# ============================================================
# PDF
# ============================================================

class TestPdf:
    def test_existing_pdf_returned(self, monkeypatch, tmp_path):
        pdf = tmp_path / "r.pdf"
        pdf.write_text("pdf", encoding="utf-8")
        record = MagicMock()
        record.pdf_path = str(pdf)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().get_pdf_path("r") == str(pdf)

    def test_lazy_generate(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setattr(
            "src.md2pdf.markdown_to_pdf_file",
            lambda _md, out: out,
        )
        assert PolicyMinesweeperService().get_pdf_path("r") == str(md.with_suffix(".pdf"))
        mock_db.set_policy_minesweeper_pdf_path.assert_called_once()

    def test_lazy_generate_failure_returns_none(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setattr("src.md2pdf.markdown_to_pdf_file", lambda _md, _out: None)
        assert PolicyMinesweeperService().get_pdf_path("r") is None


# ============================================================
# 杂项：加载器/缓存/归一化边界/清理/异常分支
# ============================================================

class TestMisc:
    def test_get_policy_minesweeper_dir_creates_and_returns(self, monkeypatch, tmp_path):
        target = tmp_path / "pm"
        monkeypatch.setattr(svc_mod, "_POLICY_MINESWEEPER_DIR", target)
        from src.services.policy_minesweeper_service import get_policy_minesweeper_dir

        assert get_policy_minesweeper_dir() == target
        assert target.exists()

    def test_max_reports_exception_fallback(self, monkeypatch):
        monkeypatch.setattr(svc_mod, "get_config", lambda: (_ for _ in ()).throw(RuntimeError()))
        from src.services.policy_minesweeper_service import _max_reports

        assert _max_reports() == 200

    def test_max_reports_custom(self, monkeypatch):
        monkeypatch.setattr(svc_mod, "get_config", lambda: SimpleNamespace(policy_minesweeper_max_reports=5))
        from src.services.policy_minesweeper_service import _max_reports

        assert _max_reports() == 5

    def test_get_executor_caches(self, monkeypatch):
        import src.agent.factory as fac

        monkeypatch.setattr(svc_mod, "_executor_instance", None)
        monkeypatch.setattr(fac, "build_policy_minesweeper_executor", lambda: "FAKE_EXEC", raising=False)
        from src.services.policy_minesweeper_service import _get_executor

        assert _get_executor() == "FAKE_EXEC"
        # 第二次应命中缓存（不再调用 factory）
        monkeypatch.setattr(fac, "build_policy_minesweeper_executor", lambda: "SHOULD_NOT_CALL", raising=False)
        assert _get_executor() == "FAKE_EXEC"

    def test_normalize_unrecognized_raises(self):
        with pytest.raises(PolicyMinesweeperInputError):
            normalize_a_share("!!!非代码!!!")

    def test_get_report_read_error_returns_empty_markdown(self, monkeypatch, tmp_path):
        record = MagicMock()
        record.to_dict.return_value = {"id": "r"}
        record.md_path = str(tmp_path)  # 目录 → read_text 抛 OSError
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        data = PolicyMinesweeperService().get_report("r")
        assert data["markdown"] == ""

    def test_get_pdf_missing_record(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().get_pdf_path("nope") is None

    def test_generate_pdf_import_error(self, monkeypatch, tmp_path):
        import sys

        md = tmp_path / "r.md"
        md.write_text("# x", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setitem(sys.modules, "src.md2pdf", None)
        assert PolicyMinesweeperService().get_pdf_path("r") is None

    def test_generate_pdf_md_missing(self, monkeypatch, tmp_path):
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(tmp_path / "nope.md")
        mock_db = MagicMock()
        mock_db.get_policy_minesweeper_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert PolicyMinesweeperService().get_pdf_path("r") is None

    def test_prune_and_clean_files(self, monkeypatch, tmp_path):
        md = tmp_path / "a.md"
        pdf = tmp_path / "a.pdf"
        md.write_text("x", encoding="utf-8")
        pdf.write_text("y", encoding="utf-8")
        mock_db = MagicMock()
        mock_db.prune_policy_minesweeper_reports.return_value = [
            {"md_path": str(md), "pdf_path": str(pdf)}
        ]
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        PolicyMinesweeperService()._prune_and_clean_files(5)
        assert not md.exists() and not pdf.exists()

    def test_prune_and_clean_files_zero_noop(self, monkeypatch):
        mock_db = MagicMock()
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        PolicyMinesweeperService()._prune_and_clean_files(0)
        mock_db.prune_policy_minesweeper_reports.assert_not_called()

    def test_prune_unlink_error_swallowed(self, monkeypatch, tmp_path):
        mock_db = MagicMock()
        mock_db.prune_policy_minesweeper_reports.return_value = [{"md_path": "/tmp/x.md", "pdf_path": None}]
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)

        def _boom(_self, *_a, **_k):
            raise OSError("boom")

        monkeypatch.setattr(Path, "unlink", _boom)
        # 不抛异常（仅记录日志）
        PolicyMinesweeperService()._prune_and_clean_files(5)

    def test_delete_unlink_error_swallowed(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_policy_minesweeper_report.return_value = {
            "md_path": "/tmp/x.md", "pdf_path": "/tmp/x.pdf"
        }
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)

        def _boom(_self, *_a, **_k):
            raise OSError("boom")

        monkeypatch.setattr(Path, "unlink", _boom)
        assert PolicyMinesweeperService().delete_report("r") is True
