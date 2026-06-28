# -*- coding: utf-8 -*-
"""供应链分析表单式报告 — API endpoints 单元测试。

用 TestClient（裸 FastAPI 挂 supply_chain_reports router，绕过 AuthMiddleware），覆盖：
- SSE generate_stream（topic 校验 422 / agent 禁用 400 / success done 事件 / error 事件 /
  线索输入错误 InputError → error 事件）
- CRUD 4 端点（list / get / delete / PDF）
- report_id 白名单 ``^sc_\\d{12}(_\\d+)?$`` 防路径穿越

不跑真实 LLM/网络/文件系统（mock service 层）。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from src.services.supply_chain_report_service import SupplyChainReportInputError


@pytest.fixture
def app():
    """裸 FastAPI（无 AuthMiddleware），挂 supply_chain_reports router。"""
    app = FastAPI()
    from api.v1.endpoints.supply_chain_reports import router

    app.include_router(router)
    return app


@pytest.fixture
def client(app, monkeypatch):
    """TestClient with AuthMiddleware bypassed + agent enabled."""
    monkeypatch.setattr("src.config.Config.is_agent_available", lambda self: True)
    from fastapi.testclient import TestClient

    return TestClient(app)


_SVC = "src.services.supply_chain_report_service.supply_chain_report_service"


# ============================================================
# generate_stream
# ============================================================

class TestGenerateStream:
    def test_empty_topic_returns_422(self, client):
        # Layer 3：Pydantic min_length=1 在解析期拦截空主题 → 422，不进 SSE
        resp = client.post("/generate/stream", json={"topic": ""})
        assert resp.status_code == 422

    def test_too_long_topic_returns_422(self, client):
        resp = client.post("/generate/stream", json={"topic": "x" * 1001})
        assert resp.status_code == 422

    def test_missing_topic_returns_422(self, client):
        resp = client.post("/generate/stream", json={})
        assert resp.status_code == 422

    def test_too_long_hint_returns_422(self, client):
        resp = client.post("/generate/stream", json={"topic": "ok", "research_hint": "x" * 2001})
        assert resp.status_code == 422

    def test_agent_disabled_returns_400(self, client, monkeypatch):
        monkeypatch.setattr("src.config.Config.is_agent_available", lambda self: False)
        resp = client.post("/generate/stream", json={"topic": "光模块产业链"})
        assert resp.status_code == 400

    def test_success_done_event(self, client, monkeypatch):
        def fake_generate(*, raw_topic, raw_hint, progress_callback):
            assert raw_topic == "光模块产业链"
            assert raw_hint == "CPO 上游"
            progress_callback({
                "type": "done",
                "success": True,
                "report_id": "sc_202606271530_1",
                "status": "success",
                "markdown": "# 供应链分析报告",
                "total_steps": 24,
            })
            return {"report_id": "sc_202606271530_1"}

        monkeypatch.setattr(f"{_SVC}.generate_report", fake_generate)
        resp = client.post(
            "/generate/stream",
            json={"topic": "光模块产业链", "research_hint": "CPO 上游"},
        )
        assert resp.status_code == 200
        payloads = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        done = [p for p in payloads if p.get("type") == "done"]
        assert len(done) == 1
        assert done[0]["report_id"] == "sc_202606271530_1"
        assert done[0]["status"] == "success"

    def test_service_error_yields_error_event(self, client, monkeypatch):
        def boom(**_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(f"{_SVC}.generate_report", boom)
        resp = client.post("/generate/stream", json={"topic": "光模块产业链"})
        assert resp.status_code == 200
        payloads = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        assert any(p.get("type") == "error" for p in payloads)

    def test_input_error_yields_error_event(self, client, monkeypatch):
        def raise_input(**_kw):
            raise SupplyChainReportInputError("分析主题不能为空")

        monkeypatch.setattr(f"{_SVC}.generate_report", raise_input)
        resp = client.post("/generate/stream", json={"topic": "   "})
        assert resp.status_code == 200
        payloads = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        errs = [p for p in payloads if p.get("type") == "error"]
        assert len(errs) == 1
        assert "分析主题不能为空" in errs[0]["message"]


# ============================================================
# list_reports
# ============================================================

class TestListReports:
    def test_empty_list(self, client, monkeypatch):
        svc = MagicMock()
        svc.list_reports.return_value = ([], 0)
        monkeypatch.setattr(f"{_SVC}.list_reports", svc.list_reports)
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["data"] == []

    def test_list_items(self, client, monkeypatch):
        svc = MagicMock()
        svc.list_reports.return_value = (
            [{
                "id": "sc_202606271530_1",
                "topic": "光模块产业链",
                "research_hint": "CPO 上游",
                "status": "success",
                "pdf_path": "/tmp/x.pdf",
            }],
            1,
        )
        monkeypatch.setattr(f"{_SVC}.list_reports", svc.list_reports)
        resp = client.get("/reports?limit=10&offset=0")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["topic"] == "光模块产业链"
        assert data[0]["has_pdf"] is True

    def test_list_passes_pagination(self, client, monkeypatch):
        svc = MagicMock()
        svc.list_reports.return_value = ([], 0)
        monkeypatch.setattr(f"{_SVC}.list_reports", svc.list_reports)
        client.get("/reports?limit=5&offset=3")
        _, kw = svc.list_reports.call_args
        assert kw == {"limit": 5, "offset": 3}


# ============================================================
# get_report
# ============================================================

class TestGetReport:
    def test_missing_returns_404(self, client, monkeypatch):
        svc = MagicMock()
        svc.get_report.return_value = None
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        resp = client.get("/reports/sc_202606271530_1")
        assert resp.status_code == 404

    def test_invalid_report_id_returns_404(self, client):
        for bad in ("../etc/passwd", "abc", "600519_202606261200", "sc_x", "sc_2026062715", "sc_202606271530_1a"):
            resp = client.get(f"/reports/{bad}")
            assert resp.status_code == 404, f"should reject {bad}"

    def test_found_returns_detail(self, client, monkeypatch):
        svc = MagicMock()
        svc.get_report.return_value = {
            "id": "sc_202606271530_1",
            "topic": "光模块产业链",
            "status": "success",
            "markdown": "# 报告正文",
        }
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        resp = client.get("/reports/sc_202606271530_1")
        assert resp.status_code == 200
        assert resp.json()["data"]["markdown"] == "# 报告正文"


# ============================================================
# delete_report
# ============================================================

class TestDeleteReport:
    def test_missing_returns_404(self, client, monkeypatch):
        svc = MagicMock()
        svc.delete_report.return_value = False
        monkeypatch.setattr(f"{_SVC}.delete_report", svc.delete_report)
        resp = client.delete("/reports/sc_202606271530_1")
        assert resp.status_code == 404

    def test_invalid_id_returns_404(self, client):
        for bad in ("badid", "../etc/passwd", "600519_202606261200", "sc_x"):
            assert client.delete(f"/reports/{bad}").status_code == 404, f"should reject {bad}"

    def test_success(self, client, monkeypatch):
        svc = MagicMock()
        svc.delete_report.return_value = True
        monkeypatch.setattr(f"{_SVC}.delete_report", svc.delete_report)
        resp = client.delete("/reports/sc_202606271530_1")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ============================================================
# download_pdf
# ============================================================

class TestDownloadPdf:
    def test_missing_record_returns_404(self, client, monkeypatch):
        svc = MagicMock()
        svc.get_report.return_value = None
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        resp = client.get("/reports/sc_202606271530_1/pdf")
        assert resp.status_code == 404

    def test_invalid_id_returns_404(self, client):
        resp = client.get("/reports/badid/pdf")
        assert resp.status_code == 404

    def test_pdf_generation_failure_returns_404(self, client, monkeypatch):
        svc = MagicMock()
        svc.get_report.return_value = {"id": "x"}
        svc.get_pdf_path.return_value = None
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        monkeypatch.setattr(f"{_SVC}.get_pdf_path", svc.get_pdf_path)
        resp = client.get("/reports/sc_202606271530_1/pdf")
        assert resp.status_code == 404

    def test_safe_path_returns_file(self, client, monkeypatch, tmp_path):
        pdf = tmp_path / "sc_202606271530_1.pdf"
        pdf.write_text("PDF", encoding="utf-8")
        svc = MagicMock()
        svc.get_report.return_value = {"id": "x"}
        svc.get_pdf_path.return_value = str(pdf)
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        monkeypatch.setattr(f"{_SVC}.get_pdf_path", svc.get_pdf_path)
        monkeypatch.setattr(
            "api.v1.endpoints.supply_chain_reports.get_supply_chain_report_dir",
            lambda: tmp_path,
        )
        resp = client.get("/reports/sc_202606271530_1/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "supply_chain_sc_202606271530_1.pdf" in resp.headers.get("content-disposition", "")

    def test_path_outside_root_returns_404(self, client, monkeypatch, tmp_path):
        # get_pdf_path 返回一个 root 外的路径 → _resolve_safe_path 拒绝 → 404
        outside = tmp_path.parent / "evil.pdf"
        outside.write_text("X", encoding="utf-8")
        svc = MagicMock()
        svc.get_report.return_value = {"id": "x"}
        svc.get_pdf_path.return_value = str(outside)
        monkeypatch.setattr(f"{_SVC}.get_report", svc.get_report)
        monkeypatch.setattr(f"{_SVC}.get_pdf_path", svc.get_pdf_path)
        monkeypatch.setattr(
            "api.v1.endpoints.supply_chain_reports.get_supply_chain_report_dir",
            lambda: tmp_path,
        )
        resp = client.get("/reports/sc_202606271530_1/pdf")
        assert resp.status_code == 404
