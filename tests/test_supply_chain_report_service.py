# -*- coding: utf-8 -*-
"""供应链分析表单式报告 — 编排服务单元测试。

mock get_db + _get_executor，覆盖 generate/list/get/delete/pdf 编排、主题校验、
线索注入、status 派生、report_id 唯一化、纯函数。不依赖真实 LLM/网络/DB。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.services import supply_chain_report_service as svc_mod
from src.services.supply_chain_report_service import (
    SupplyChainReportInputError,
    SupplyChainReportService,
    _status_from_result,
    build_supply_chain_user_message,
)


def _fake_result(**kw: Any) -> SimpleNamespace:
    base = dict(
        success=True,
        content="# 供应链分析报告\n\n## 一句话结论\n...",
        error=None,
        total_steps=24,
        total_tokens=12000,
        provider="test",
        model="test-model",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================
# 纯函数：build_supply_chain_user_message
# ============================================================

class TestUserMessage:
    def test_without_hint_is_topic_only(self):
        msg = build_supply_chain_user_message("光模块产业链", None)
        assert msg == "分析主题：\n光模块产业链"
        assert "线索" not in msg

    def test_with_hint_injects_clue_directive(self):
        msg = build_supply_chain_user_message("光模块产业链", "CPO 上游薄膜铌酸锂")
        assert "分析主题：\n光模块产业链" in msg
        assert "高优先级供应链线索" in msg
        assert "CPO 上游薄膜铌酸锂" in msg
        assert "线索验证" in msg
        assert "证伪" in msg

    def test_with_whitespace_hint_treated_as_none(self):
        msg = build_supply_chain_user_message("光模块产业链", "   ")
        assert msg == "分析主题：\n光模块产业链"


# ============================================================
# 纯函数：_status_from_result
# ============================================================

class TestStatusFromResult:
    def test_success(self):
        assert _status_from_result(True, "# x") == "success"

    def test_partial(self):
        assert _status_from_result(False, "# 有正文") == "partial"

    def test_failed_empty(self):
        assert _status_from_result(False, "") == "failed"

    def test_failed_whitespace_only(self):
        assert _status_from_result(False, "   ") == "failed"


# ============================================================
# report_id 唯一化
# ============================================================

class TestResolveUniqueReportId:
    def test_absent_returns_seq_1(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        from src.services.supply_chain_report_service import _resolve_unique_report_id

        ts = datetime(2026, 6, 27, 15, 30)
        assert _resolve_unique_report_id(ts) == "sc_202606271530_1"

    def test_conflict_appends_sequence(self, monkeypatch):
        existing = {"sc_202606271530_1": True}
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.side_effect = (
            lambda rid: object() if existing.get(rid) else None
        )
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        from src.services.supply_chain_report_service import _resolve_unique_report_id

        ts = datetime(2026, 6, 27, 15, 30)
        assert _resolve_unique_report_id(ts) == "sc_202606271530_2"


# ============================================================
# generate_report
# ============================================================

class TestGenerateReport:
    def _wire(self, monkeypatch, tmp_path, result):
        fake_executor = MagicMock()
        fake_executor.chat.return_value = result
        monkeypatch.setattr(svc_mod, "_get_executor", lambda: fake_executor)
        monkeypatch.setattr(svc_mod, "get_supply_chain_report_dir", lambda: tmp_path)
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = None
        mock_db.prune_supply_chain_reports.return_value = []
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        return fake_executor, mock_db

    def test_success_writes_md_and_saves_metadata(self, monkeypatch, tmp_path):
        fake_executor, mock_db = self._wire(monkeypatch, tmp_path, _fake_result())
        saved: Dict[str, Any] = {}
        mock_db.save_supply_chain_report.side_effect = lambda **kw: (saved.update(kw), True)[1]

        out = SupplyChainReportService().generate_report("光模块产业链", "CPO 上游")

        assert out["status"] == "success"
        assert out["report_id"].startswith("sc_")
        assert (tmp_path / f"{out['report_id']}.md").exists()
        assert saved["topic"] == "光模块产业链"
        assert saved["research_hint"] == "CPO 上游"
        assert saved["status"] == "success"
        assert saved["provider"] == "test" and saved["model"] == "test-model"

    def test_clue_injected_into_chat_message(self, monkeypatch, tmp_path):
        fake_executor, _ = self._wire(monkeypatch, tmp_path, _fake_result())
        SupplyChainReportService().generate_report("光模块产业链", "CPO 上游薄膜铌酸锂")
        sent_msg = fake_executor.chat.call_args.kwargs["message"]
        assert "高优先级供应链线索" in sent_msg
        assert "CPO 上游薄膜铌酸锂" in sent_msg

    def test_no_clue_message_is_topic_only(self, monkeypatch, tmp_path):
        fake_executor, _ = self._wire(monkeypatch, tmp_path, _fake_result())
        SupplyChainReportService().generate_report("光模块产业链", None)
        sent_msg = fake_executor.chat.call_args.kwargs["message"]
        assert sent_msg == "分析主题：\n光模块产业链"

    def test_session_id_isolated_namespace(self, monkeypatch, tmp_path):
        fake_executor, _ = self._wire(monkeypatch, tmp_path, _fake_result())
        out = SupplyChainReportService().generate_report("光模块产业链")
        sid = fake_executor.chat.call_args.kwargs["session_id"]
        assert sid == f"supply_chain_report:{out['report_id']}"
        assert sid.startswith("supply_chain_report:")  # 与旧 supply_chain: 隔离

    def test_empty_topic_raises(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        with pytest.raises(SupplyChainReportInputError):
            SupplyChainReportService().generate_report("")

    def test_whitespace_topic_raises(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        with pytest.raises(SupplyChainReportInputError):
            SupplyChainReportService().generate_report("   ")

    def test_partial_status_when_failed_with_content(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result(success=False, content="# 部分报告"))
        out = SupplyChainReportService().generate_report("光模块产业链")
        assert out["status"] == "partial"

    def test_failed_status_when_no_content(self, monkeypatch, tmp_path):
        mock_db = MagicMock()
        self._wire(monkeypatch, tmp_path, _fake_result(success=False, content=""))
        out = SupplyChainReportService().generate_report("光模块产业链")
        assert out["status"] == "failed"
        assert out["report_id"] is None

    def test_write_fail_skips_save(self, monkeypatch, tmp_path):
        _, mock_db = self._wire(monkeypatch, tmp_path, _fake_result())

        def _boom(_self, _path, *_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", _boom)
        out = SupplyChainReportService().generate_report("光模块产业链")
        assert out["report_id"] is None
        mock_db.save_supply_chain_report.assert_not_called()

    def test_done_progress_event_carries_full_payload(self, monkeypatch, tmp_path):
        self._wire(monkeypatch, tmp_path, _fake_result())
        events = []
        SupplyChainReportService().generate_report(
            "光模块产业链", "CPO 上游", progress_callback=events.append
        )
        done = [e for e in events if e.get("type") == "done"]
        assert len(done) == 1
        e = done[0]
        assert e["success"] is True
        assert e["report_id"].startswith("sc_")
        assert e["status"] == "success"
        assert e["markdown"].startswith("# 供应链分析报告")
        assert e["total_steps"] == 24 and e["provider"] == "test"


# ============================================================
# list / get / delete（代理层）
# ============================================================

class TestProxies:
    def test_list_reports(self, monkeypatch):
        rec = MagicMock()
        rec.to_dict.return_value = {"id": "x"}
        mock_db = MagicMock()
        mock_db.get_supply_chain_reports.return_value = ([rec], 1)
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        rows, total = SupplyChainReportService().list_reports()
        assert total == 1 and rows == [{"id": "x"}]

    def test_get_report_reads_markdown(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.to_dict.return_value = {"id": "r"}
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        data = SupplyChainReportService().get_report("r")
        assert data["markdown"] == "# 正文"

    def test_get_report_missing(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().get_report("nope") is None

    def test_get_report_read_error_returns_empty_markdown(self, monkeypatch, tmp_path):
        record = MagicMock()
        record.to_dict.return_value = {"id": "r"}
        record.md_path = str(tmp_path)  # 目录 → read_text 抛 OSError
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        data = SupplyChainReportService().get_report("r")
        assert data["markdown"] == ""

    def test_delete_report(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_supply_chain_report.return_value = {
            "md_path": "/tmp/a.md",
            "pdf_path": None,
        }
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().delete_report("r") is True

    def test_delete_report_missing(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_supply_chain_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().delete_report("nope") is False

    def test_delete_unlink_error_swallowed(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.delete_supply_chain_report.return_value = {
            "md_path": "/tmp/x.md",
            "pdf_path": "/tmp/x.pdf",
        }
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)

        def _boom(_self, *_a, **_k):
            raise OSError("boom")

        monkeypatch.setattr(Path, "unlink", _boom)
        assert SupplyChainReportService().delete_report("r") is True


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
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().get_pdf_path("r") == str(pdf)

    def test_lazy_generate(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setattr("src.md2pdf.markdown_to_pdf_file", lambda _md, out: out)
        assert SupplyChainReportService().get_pdf_path("r") == str(md.with_suffix(".pdf"))
        mock_db.set_supply_chain_pdf_path.assert_called_once()

    def test_lazy_generate_failure_returns_none(self, monkeypatch, tmp_path):
        md = tmp_path / "r.md"
        md.write_text("# 正文", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setattr("src.md2pdf.markdown_to_pdf_file", lambda _md, _out: None)
        assert SupplyChainReportService().get_pdf_path("r") is None

    def test_get_pdf_missing_record(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = None
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().get_pdf_path("nope") is None

    def test_generate_pdf_import_error(self, monkeypatch, tmp_path):
        import sys

        md = tmp_path / "r.md"
        md.write_text("# x", encoding="utf-8")
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(md)
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        monkeypatch.setitem(sys.modules, "src.md2pdf", None)
        assert SupplyChainReportService().get_pdf_path("r") is None

    def test_generate_pdf_md_missing(self, monkeypatch, tmp_path):
        record = MagicMock()
        record.id = "r"
        record.pdf_path = None
        record.md_path = str(tmp_path / "nope.md")
        mock_db = MagicMock()
        mock_db.get_supply_chain_report.return_value = record
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        assert SupplyChainReportService().get_pdf_path("r") is None


# ============================================================
# 清理
# ============================================================

class TestPrune:
    def test_prune_and_clean_files(self, monkeypatch, tmp_path):
        md = tmp_path / "a.md"
        pdf = tmp_path / "a.pdf"
        md.write_text("x", encoding="utf-8")
        pdf.write_text("y", encoding="utf-8")
        mock_db = MagicMock()
        mock_db.prune_supply_chain_reports.return_value = [
            {"md_path": str(md), "pdf_path": str(pdf)}
        ]
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        SupplyChainReportService()._prune_and_clean_files(5)
        assert not md.exists() and not pdf.exists()

    def test_prune_zero_noop(self, monkeypatch):
        mock_db = MagicMock()
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)
        SupplyChainReportService()._prune_and_clean_files(0)
        mock_db.prune_supply_chain_reports.assert_not_called()

    def test_prune_unlink_error_swallowed(self, monkeypatch, tmp_path):
        mock_db = MagicMock()
        mock_db.prune_supply_chain_reports.return_value = [
            {"md_path": "/tmp/x.md", "pdf_path": None}
        ]
        monkeypatch.setattr(svc_mod, "get_db", lambda: mock_db)

        def _boom(_self, *_a, **_k):
            raise OSError("boom")

        monkeypatch.setattr(Path, "unlink", _boom)
        SupplyChainReportService()._prune_and_clean_files(5)  # 不抛异常


# ============================================================
# 杂项：目录/executor 缓存
# ============================================================

class TestMisc:
    def test_get_dir_creates_and_returns(self, monkeypatch, tmp_path):
        target = tmp_path / "sc"
        monkeypatch.setattr(svc_mod, "_SUPPLY_CHAIN_DIR", target)
        from src.services.supply_chain_report_service import get_supply_chain_report_dir

        assert get_supply_chain_report_dir() == target
        assert target.exists()

    def test_get_executor_caches(self, monkeypatch):
        import src.agent.factory as fac

        monkeypatch.setattr(svc_mod, "_executor_instance", None)
        monkeypatch.setattr(svc_mod, "get_config", lambda: SimpleNamespace())
        monkeypatch.setattr(fac, "build_supply_chain_executor", lambda _cfg: "FAKE_EXEC", raising=False)
        from src.services.supply_chain_report_service import _get_executor

        assert _get_executor() == "FAKE_EXEC"
        # 第二次应命中缓存（不再调用 factory）
        monkeypatch.setattr(fac, "build_supply_chain_executor", lambda _cfg: "SHOULD_NOT_CALL", raising=False)
        assert _get_executor() == "FAKE_EXEC"


# ============================================================
# Prompt 线索核验规则（B3：仅常量段，无线索时不生效）
# ============================================================

class TestClueRulesInPrompt:
    def test_system_prompt_template_contains_clue_rules(self):
        from src.agent.supply_chain_executor import _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE as tpl

        assert "线索核验规则" in tpl
        assert "调查目标" in tpl
        assert "线索验证" in tpl
        # 限定验证状态枚举
        assert "已确认" in tpl and "已证伪" in tpl
