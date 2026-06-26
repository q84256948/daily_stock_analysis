# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — 工具层单元测试。

不依赖 LLM 与网络，只验证 ``score_policy_minesweeper`` 工具 handler 的入参规整、
返回契约（中文 verdict / Markdown / 仓位指令 / usage_note）、容错与元数据。
"""

from __future__ import annotations

import pytest

from src.agent.tools import policy_minesweeper_tools as pmt
from src.agent.tools.policy_minesweeper_tools import (
    ALL_POLICY_MINESWEEPER_TOOLS,
    DIMENSION_HINTS,
    _build_announcement_query,
    _get_announcement_search_service,
    _handle_score_policy_minesweeper,
    _handle_search_company_announcements,
    _is_official_announcement_source,
    _pick_search_provider,
)


def _dims(value: float) -> dict:
    return {key: value for key in DIMENSION_HINTS}


def _full(**overrides) -> dict:
    kwargs = dict(
        stock_code="300750",
        stock_name="示例公司",
        horizon="medium",
        dimensions=_dims(0.0),
        alpha_score=0.0,
        beta_score=0.0,
        dominant_factor="信号均衡",
        confidence=0.6,
        scenarios={
            "optimistic": {"assumption": "政策缓和", "score": 40},
            "base_case": {"assumption": "维持现状", "score": 0},
            "pessimistic": {"assumption": "政策升级", "score": -40},
        },
        evidence=[{"claim": "重大合同", "source": "巨潮公告", "date": "2026-06-20", "strength": "primary"}],
    )
    kwargs.update(overrides)
    return kwargs


# ============================================================
# 正常打分
# ============================================================

class TestNormalScoring:
    def test_returns_required_keys_no_error(self):
        result = _handle_score_policy_minesweeper(**_full())
        for key in ("stock_code", "stock_name", "verdict", "final", "action",
                    "expected_car", "score_report_markdown", "usage_note"):
            assert key in result
        assert "error" not in result

    def test_verdict_is_chinese_with_emoji(self):
        result = _handle_score_policy_minesweeper(**_full(dimensions=_dims(80), alpha_score=80, beta_score=80))
        assert result["verdict"].startswith("🟢") or result["verdict"].startswith("🟡")
        assert "strong_bull" not in result["verdict"]
        assert result["action"] in ("加仓", "增持", "持有/观望", "减持", "清仓/回避")

    def test_markdown_no_field_name_leak(self):
        result = _handle_score_policy_minesweeper(**_full())
        md = result["score_report_markdown"]
        for key in DIMENSION_HINTS:
            assert key not in md
        assert "不构成投资建议" in md

    def test_usage_note_disclaims_advice(self):
        result = _handle_score_policy_minesweeper(**_full())
        assert "投资建议" in result["usage_note"]


# ============================================================
# 容错（缺失 / 非法值）
# ============================================================

class TestRobustness:
    def test_missing_dimensions_defaults_zero(self):
        result = _handle_score_policy_minesweeper(stock_code="X", stock_name="Y")
        assert "error" not in result
        assert result["final"] == 0

    def test_invalid_dimension_values_coerced(self):
        result = _handle_score_policy_minesweeper(
            stock_code="X", stock_name="Y",
            dimensions={"event_importance": 99999, "policy_exposure": "bad", "earnings_impact": -99999},
        )
        assert "error" not in result
        assert isinstance(result["final"], int)

    def test_optional_alpha_beta_omitted(self):
        result = _handle_score_policy_minesweeper(
            stock_code="X", stock_name="Y", dimensions=_dims(40),
        )
        # alpha/beta 缺 → blend 回退 composite → final == 40
        assert result["final"] == 40
        assert "error" not in result

    def test_invalid_horizon_defaults_medium(self):
        r1 = _handle_score_policy_minesweeper(
            stock_code="X", stock_name="Y", dimensions=_dims(0),
            alpha_score=100, beta_score=-100, horizon="nonsense",
        )
        r2 = _handle_score_policy_minesweeper(
            stock_code="X", stock_name="Y", dimensions=_dims(0),
            alpha_score=100, beta_score=-100, horizon="medium",
        )
        assert r1["final"] == r2["final"]


# ============================================================
# 异常路径（scorecard 抛错 → 返回 error + input_echo）
# ============================================================

class TestErrorPath:
    def test_scorecard_exception_returns_error_echo(self, monkeypatch):
        def boom(_payload, _horizon):
            raise RuntimeError("boom")

        monkeypatch.setattr(pmt._scorecard, "score", boom)
        result = _handle_score_policy_minesweeper(**_full())
        assert "error" in result
        assert "input_echo" in result
        assert result["input_echo"]["stock_code"] == "300750"


# ============================================================
# 工具集元数据
# ============================================================

class TestToolMetadata:
    def test_two_tools(self):
        assert len(ALL_POLICY_MINESWEEPER_TOOLS) == 2
        names = {t.name for t in ALL_POLICY_MINESWEEPER_TOOLS}
        assert names == {"score_policy_minesweeper", "search_company_announcements"}

    def test_announcement_tool_metadata(self):
        tool = next(
            t for t in ALL_POLICY_MINESWEEPER_TOOLS if t.name == "search_company_announcements"
        )
        assert tool.category == "search"
        params = {p.name for p in tool.parameters}
        assert {"stock_code", "stock_name"} <= params

    def test_required_params_present(self):
        tool = ALL_POLICY_MINESWEEPER_TOOLS[0]
        names = {p.name for p in tool.parameters}
        assert {"stock_code", "stock_name", "dimensions"} <= names

    def test_horizon_param_enum(self):
        tool = ALL_POLICY_MINESWEEPER_TOOLS[0]
        horizon = next(p for p in tool.parameters if p.name == "horizon")
        assert set(horizon.enum) == {"short", "medium", "long"}

    def test_dimension_hints_match_scorecard(self):
        from src.services.policy_minesweeper_scorecard import DIMENSION_KEYS

        assert set(DIMENSION_HINTS) == set(DIMENSION_KEYS)


# ============================================================
# 证据原文地址（公司公告 url）端到端
# ============================================================

class TestEvidenceUrl:
    def test_announcement_url_passes_through_to_markdown(self):
        # 公司公告类证据带 url → 工具输出的 score_report_markdown 含 [原文](url) 链接
        result = _handle_score_policy_minesweeper(**_full(
            evidence=[{
                "claim": "签订重大合同",
                "source": "巨潮公告",
                "date": "2026-06-20",
                "strength": "primary",
                "url": "http://www.cninfo.com.cn/ann/x.html",
            }],
        ))
        assert "error" not in result
        assert "[原文](http://www.cninfo.com.cn/ann/x.html)" in result["score_report_markdown"]

    def test_evidence_param_documents_url(self):
        # score 工具 evidence 参数描述必须文档化 url 字段（提示 Ω 传公告原文地址）
        tool = ALL_POLICY_MINESWEEPER_TOOLS[0]
        evidence_param = next(p for p in tool.parameters if p.name == "evidence")
        assert "url" in evidence_param.description
        assert "原文地址" in evidence_param.description


# ============================================================
# 公司公告检索（search_company_announcements，DI 搜索服务，无网络）
# ============================================================

class _FakeResult:
    """鸭子类型 SearchResult（title/snippet/url/source/published_date）。"""

    def __init__(self, title, url, source, snippet="", published_date=""):
        self.title = title
        self.url = url
        self.source = source
        self.snippet = snippet
        self.published_date = published_date


class _FakeSearchResponse:
    """鸭子类型 SearchResponse。"""

    def __init__(self, results, success=True, error_message="", provider="Tavily"):
        self.results = results
        self.success = success
        self.error_message = error_message
        self.provider = provider


class _FakeProvider:
    """鸭子类型 search provider：记录原生 .search() 调用，可控 is_available/结果/抛错。"""

    def __init__(self, *, available=True, response=None, raise_exc=None, name="Tavily"):
        self.is_available = available
        self.name = name
        self._response = response
        self._raise = raise_exc
        self.calls = []

    def search(self, query, max_results=5, days=30):
        self.calls.append({"query": query, "max_results": max_results, "days": days})
        if self._raise:
            raise self._raise
        return self._response


class _FakeSearchService:
    """鸭子类型 SearchService：仅持有 _providers 列表。"""

    def __init__(self, providers):
        self._providers = providers


def _patch_service(monkeypatch, provider):
    """把 _get_announcement_search_service 替换为含单个 provider 的 fake service。"""
    svc = _FakeSearchService([provider])
    monkeypatch.setattr(pmt, "_get_announcement_search_service", lambda: svc)
    return provider


class TestBuildAnnouncementQuery:
    def test_includes_name_code_and_announcement_terms(self):
        q = _build_announcement_query("贵州茅台", "600519")
        assert "贵州茅台" in q and "600519" in q and "公告" in q

    def test_falls_back_to_code_when_name_missing(self):
        q = _build_announcement_query("", "300750")
        assert "300750" in q and "公告" in q


class TestPickSearchProvider:
    def test_returns_none_for_none_service(self):
        assert _pick_search_provider(None) is None

    def test_returns_none_when_no_available_provider(self):
        svc = _FakeSearchService([_FakeProvider(available=False)])
        assert _pick_search_provider(svc) is None

    def test_returns_first_available_provider(self):
        available = _FakeProvider(available=True)
        svc = _FakeSearchService([_FakeProvider(available=False), available])
        assert _pick_search_provider(svc) is available


class TestIsOfficialAnnouncementSource:
    def test_official_sources_are_true(self):
        assert _is_official_announcement_source("http://www.cninfo.com.cn/x", "巨潮") is True
        assert _is_official_announcement_source("https://szse.cn/ann", "深交所") is True

    def test_media_sources_are_false(self):
        assert _is_official_announcement_source("http://finance.sina.com.cn/x", "新浪") is False
        assert _is_official_announcement_source("http://finance.qq.com/x", "腾讯") is False

    def test_empty_is_false(self):
        assert _is_official_announcement_source("", "") is False


class TestAnnouncementSearchServiceAccessor:
    def test_real_accessor_returns_shared_service(self):
        # 不 monkeypatch：走真实 lazy import + get_search_service()，覆盖函数体
        svc = _get_announcement_search_service()
        assert svc is not None
        assert hasattr(svc, "is_available")  # SearchService 单例契约


class TestSearchCompanyAnnouncementsHandler:
    def test_returns_error_when_no_available_provider(self, monkeypatch):
        _patch_service(monkeypatch, _FakeProvider(available=False))
        result = _handle_search_company_announcements("600519", "贵州茅台")
        assert "error" in result and "不可用" in result["error"]
        assert result["stock_code"] == "600519"

    def test_returns_error_when_service_none(self, monkeypatch):
        monkeypatch.setattr(pmt, "_get_announcement_search_service", lambda: None)
        result = _handle_search_company_announcements("600519", "贵州茅台")
        assert "error" in result and "不可用" in result["error"]

    def test_maps_results_and_marks_official_flag(self, monkeypatch):
        response = _FakeSearchResponse(results=[
            _FakeResult("重大合同公告", "http://www.cninfo.com.cn/ann/x", "巨潮资讯网", "摘要A", "2026-06-20"),
            _FakeResult("腾讯证券报道", "http://finance.qq.com/x", "腾讯证券", "摘要B", "2026-06-19"),
        ])
        provider = _FakeProvider(available=True, response=response)
        _patch_service(monkeypatch, provider)

        result = _handle_search_company_announcements("600519", "贵州茅台")

        assert "error" not in result
        assert result["count"] == 2
        assert result["announcements"][0]["url"] == "http://www.cninfo.com.cn/ann/x"
        assert result["announcements"][0]["is_official"] is True
        assert result["announcements"][1]["is_official"] is False
        assert result["announcements"][0]["date"] == "2026-06-20"
        assert result["provider"] == "Tavily"
        # 公告导向 query + 30 天窗口透传给 provider 原生 .search()
        assert provider.calls[0]["days"] == 30
        assert "公告" in provider.calls[0]["query"]
        assert provider.calls[0]["max_results"] == 8

    def test_returns_error_on_search_failure(self, monkeypatch):
        response = _FakeSearchResponse(results=[], success=False, error_message="quota exceeded")
        _patch_service(monkeypatch, _FakeProvider(available=True, response=response))

        result = _handle_search_company_announcements("600519", "贵州茅台")

        assert "error" in result and "quota exceeded" in result["error"]
        assert result["query"].startswith("贵州茅台")

    def test_returns_error_on_search_exception(self, monkeypatch):
        _patch_service(monkeypatch, _FakeProvider(available=True, raise_exc=RuntimeError("boom")))

        result = _handle_search_company_announcements("600519", "贵州茅台")

        assert "error" in result and "boom" in result["error"]

    def test_truncates_long_snippet(self, monkeypatch):
        long_text = "x" * 1000
        response = _FakeSearchResponse(
            results=[_FakeResult("t", "http://www.cninfo.com.cn/a", "巨潮", long_text)],
        )
        _patch_service(monkeypatch, _FakeProvider(available=True, response=response))

        result = _handle_search_company_announcements("600519", "贵州茅台")

        assert result["announcements"][0]["snippet"] == "x" * 500
