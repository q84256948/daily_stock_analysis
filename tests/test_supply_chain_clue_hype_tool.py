# -*- coding: utf-8 -*-
"""供应链「线索多源炒作检索」工具（search_clue_hype）单元测试。

镜像 tests/test_supply_chain_semianalysis_tool.py：
- 鸭子类型 fake（_FakeResult/_FakeSearchResponse/_FakeProvider/_FakeSearchService）
- DI 搜索服务（monkeypatch _get_search_service），无真实网络
- 覆盖 query 构造 / hype_signal 分级 / handler 多源逐源检索（含单源容错）/ 元数据 / prompt 规则
"""

from __future__ import annotations

from typing import Any, List

import pytest

import src.agent.tools.supply_chain_tools as sct
from src.agent.tools.supply_chain_tools import (
    ALL_SUPPLY_CHAIN_TOOLS,
    _CLUE_HYPE_DAYS,
    _CLUE_HYPE_SOURCES,
    _build_clue_hype_query,
    _handle_search_clue_hype,
    _hype_signal,
    search_clue_hype_tool,
)
from src.agent.supply_chain_executor import _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE


# ============================================================
# 鸭子类型 fake
# ============================================================

class _FakeResult:
    def __init__(self, title: str, url: str, source: str = ""):
        self.title = title
        self.url = url
        self.source = source


class _FakeSearchResponse:
    def __init__(self, results: List[Any], success: bool = True, error_message: str = ""):
        self.results = results
        self.success = success
        self.error_message = error_message


class _FakeProvider:
    """按 query 内容可控返回：query→response 映射，或全部统一返回；可对特定 query 抛错。"""

    def __init__(self, *, default_response=None, per_query=None, raise_on=None):
        self.is_available = True
        self._default = default_response
        self._per_query = per_query or {}
        self._raise_on = raise_on or ()
        self.calls: List[dict] = []

    def search(self, query, max_results=3, days=180):
        self.calls.append({"query": query, "max_results": max_results, "days": days})
        for needle in self._raise_on:
            if needle in query:
                raise RuntimeError(f"boom on {query}")
        if query in self._per_query:
            return self._per_query[query]
        return self._default


class _FakeSearchService:
    def __init__(self, providers):
        self._providers = providers


def _patch_service(monkeypatch: pytest.MonkeyPatch, provider: _FakeProvider):
    svc = _FakeSearchService([provider])
    monkeypatch.setattr(sct, "_get_search_service", lambda: svc)
    return provider


# ============================================================
# _build_clue_hype_query
# ============================================================

class TestBuildClueHypeQuery:
    def test_with_site_prefixes_site_operator(self):
        assert _build_clue_hype_query("xueqiu.com", "新凯来") == "site:xueqiu.com 新凯来"

    def test_without_site_is_bare_clue(self):
        assert _build_clue_hype_query(None, "新凯来 供应商") == "新凯来 供应商"

    def test_strips_whitespace(self):
        assert _build_clue_hype_query("10jqka.com.cn", "  新凯来  ") == "site:10jqka.com.cn 新凯来"

    def test_empty_clue_with_site(self):
        assert _build_clue_hype_query("xueqiu.com", "   ") == "site:xueqiu.com"

    def test_none_clue_without_site(self):
        assert _build_clue_hype_query(None, None) == ""


# ============================================================
# _hype_signal
# ============================================================

class TestHypeSignal:
    def test_zero_is_none(self):
        assert _hype_signal(0) == "无"

    def test_one_two_is_weak(self):
        assert _hype_signal(1) == "弱"
        assert _hype_signal(2) == "弱"

    def test_three_four_is_medium(self):
        assert _hype_signal(3) == "中"
        assert _hype_signal(4) == "中"

    def test_five_plus_is_strong(self):
        assert _hype_signal(5) == "强"
        assert _hype_signal(9) == "强"

    def test_none_or_negative_safe(self):
        assert _hype_signal(None) == "无"
        assert _hype_signal(-1) == "无"


# ============================================================
# _handle_search_clue_hype
# ============================================================

class TestSearchClueHypeHandler:
    def test_returns_error_when_no_available_provider(self, monkeypatch):
        _patch_service(monkeypatch, _FakeProvider(default_response=None))
        monkeypatch.setattr(sct, "_get_search_service", lambda: _FakeSearchService([_FakeProvider()]))
        # provider 无 is_available → _pick_search_provider 返回 None
        svc = _FakeSearchService([_FakeProvider()])
        monkeypatch.setattr(sct, "_get_search_service", lambda: svc)
        # 构造 provider.is_available=False
        prov = _FakeProvider(default_response=_FakeSearchResponse(results=[]))
        prov.is_available = False
        monkeypatch.setattr(sct, "_get_search_service", lambda: _FakeSearchService([prov]))
        result = _handle_search_clue_hype("新凯来")
        assert "error" in result and "不可用" in result["error"]
        assert result["clue"] == "新凯来"

    def test_success_multi_source_aggregation_and_hype_signal(self, monkeypatch):
        # 全网源 + 雪球 + 新浪 各命中若干 → mention_sources 含这 3 个 → 中信号（3-4）
        def resp_for(query):
            if "xueqiu.com" in query:
                return _FakeSearchResponse([_FakeResult("雪球帖", "https://xueqiu.com/a")])
            if "finance.sina.com.cn" in query:
                return _FakeSearchResponse([_FakeResult("新浪", "https://finance.sina.com.cn/b")])
            if query.startswith("新凯来"):  # 全网源（无 site:）
                return _FakeSearchResponse([_FakeResult("全网", "https://g.cn/c")])
            return _FakeSearchResponse([])  # 同花顺/巨潮 无命中
        prov = _FakeProvider(per_query={q: resp_for(q) for q in [
            "site:finance.sina.com.cn 新凯来", "site:xueqiu.com 新凯来",
            "site:10jqka.com.cn 新凯来", "site:cninfo.com.cn 新凯来", "新凯来",
        ]})
        # 简化：让 provider 按 query 动态返回
        prov = _FakeProvider()
        prov.search = lambda query, max_results=3, days=180: (prov.calls.append({"query": query}) or resp_for(query))
        _patch_service(monkeypatch, prov)

        result = _handle_search_clue_hype("新凯来")

        assert "error" not in result
        assert result["clue"] == "新凯来"
        assert len(result["queried"]) == len(_CLUE_HYPE_SOURCES)  # 5 源全查
        # 每源 query 站点限定正确（全网源裸 clue）
        queries = [q["query"] for q in result["queried"]]
        assert "site:xueqiu.com 新凯来" in queries
        assert "新凯来" in queries  # 全网源
        # 提及源聚合：雪球/新浪/全网（3 个）
        assert set(result["mention_sources"]) == {"新浪财经", "雪球", "全网/Google"}
        assert result["total_mentions"] == 3
        assert result["hype_signal"] == "中"  # 3 源 → 中
        assert "题材炒作信号" in result["note"] or "炒作信号" in result["note"]
        # 每个提及源结果含 url
        xueqiu_entry = [q for q in result["queried"] if q["source"] == "雪球"][0]
        assert xueqiu_entry["results"][0]["url"] == "https://xueqiu.com/a"
        assert xueqiu_entry["mention_count"] == 1

    def test_per_source_resilience_one_raises_others_continue(self, monkeypatch):
        # 同花顺源抛异常，其它源正常 → 该源计 0 且带 error，总体仍返回
        def resp_for(query):
            if "xueqiu.com" in query:
                return _FakeSearchResponse([_FakeResult("雪球", "https://xueqiu.com/x")])
            return _FakeSearchResponse([])
        prov = _FakeProvider()
        prov.search = lambda query, max_results=3, days=180: (prov.calls.append({"query": query}) or resp_for(query))
        # 改成对 10jqka 抛错：用 raise_on
        prov2 = _FakeProvider(raise_on=("10jqka.com.cn",))
        prov2.search = lambda query, max_results=3, days=180: (
            prov2.calls.append({"query": query})
            or (_ for _ in ()).throw(RuntimeError("boom")) if "10jqka" in query else resp_for(query)
        )
        _patch_service(monkeypatch, prov2)

        result = _handle_search_clue_hype("新凯来")

        assert "error" not in result  # 整体不报错
        ths = [q for q in result["queried"] if q["source"] == "同花顺"][0]
        assert ths["mention_count"] == 0
        assert "error" in ths and "boom" in ths["error"]
        # 雪球仍命中
        assert "雪球" in result["mention_sources"]
        assert result["hype_signal"] == "弱"  # 仅 1 源

    def test_all_sources_no_hit_yields_none_signal(self, monkeypatch):
        prov = _FakeProvider(default_response=_FakeSearchResponse(results=[]))
        _patch_service(monkeypatch, prov)
        result = _handle_search_clue_hype("某完全不存在的线索xyz")
        assert result["mention_sources"] == []
        assert result["total_mentions"] == 0
        assert result["hype_signal"] == "无"

    def test_search_failure_marks_source_error(self, monkeypatch):
        # response.success=False 的源计入 error、0 提及
        def resp_for(query):
            if "xueqiu.com" in query:
                return _FakeSearchResponse([_FakeResult("雪球", "https://xueqiu.com/x")])
            return _FakeSearchResponse([], success=False, error_message="quota")
        prov = _FakeProvider()
        prov.search = lambda query, max_results=3, days=180: (prov.calls.append({"query": query}) or resp_for(query))
        _patch_service(monkeypatch, prov)
        result = _handle_search_clue_hype("新凯来")
        sina = [q for q in result["queried"] if q["source"] == "新浪财经"][0]
        assert sina["mention_count"] == 0 and sina.get("error") == "quota"
        assert result["mention_sources"] == ["雪球"]

    def test_max_results_per_source_caps_items(self, monkeypatch):
        def resp_for(query):
            if "xueqiu.com" in query:
                return _FakeSearchResponse([_FakeResult(f"t{i}", f"https://xueqiu.com/{i}") for i in range(10)])
            return _FakeSearchResponse([])
        prov = _FakeProvider()
        prov.search = lambda query, max_results=3, days=180: (prov.calls.append({"query": query, "max_results": max_results}) or resp_for(query))
        _patch_service(monkeypatch, prov)
        result = _handle_search_clue_hype("新凯来", max_results_per_source=2)
        xueqiu = [q for q in result["queried"] if q["source"] == "雪球"][0]
        assert xueqiu["mention_count"] == 2  # 封顶 2
        # 透传 cap
        assert prov.calls[0]["max_results"] == 2

    def test_days_window_passed_through(self, monkeypatch):
        prov = _FakeProvider(default_response=_FakeSearchResponse(results=[]))
        captured = {"days": None}
        def spy(query, max_results=3, days=180):
            captured["days"] = days
            return _FakeSearchResponse([])
        prov.search = spy
        _patch_service(monkeypatch, prov)
        _handle_search_clue_hype("新凯来")
        assert captured["days"] == _CLUE_HYPE_DAYS == 180


# ============================================================
# 工具元数据
# ============================================================

class TestSearchClueHypeToolMetadata:
    def test_registered_in_all_supply_chain_tools(self):
        names = {t.name for t in ALL_SUPPLY_CHAIN_TOOLS}
        assert "search_clue_hype" in names

    def test_category_is_search(self):
        assert search_clue_hype_tool.category == "search"

    def test_required_clue_param(self):
        params = {p.name: p for p in search_clue_hype_tool.parameters}
        assert params["clue"].required is True
        assert params["clue"].type == "string"

    def test_max_results_optional_default(self):
        params = {p.name: p for p in search_clue_hype_tool.parameters}
        assert params["max_results_per_source"].required is False
        assert params["max_results_per_source"].default == 3

    def test_description_mentions_sources_and_hype(self):
        desc = search_clue_hype_tool.description
        assert "题材炒作" in desc
        assert "雪球" in desc or "新浪" in desc or "同花顺" in desc

    def test_sources_constant_covers_named_media(self):
        names = {n for n, _ in _CLUE_HYPE_SOURCES}
        assert {"新浪财经", "雪球", "同花顺", "巨潮资讯/公司公告", "全网/Google"} == names


# ============================================================
# prompt 规则（standing，仅用户提供线索时触发）
# ============================================================

class TestClueHypePromptRule:
    def test_prompt_lists_tool_and_rule(self):
        tpl = _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE
        assert "search_clue_hype" in tpl
        assert "题材炒作信号" in tpl

    def test_prompt_names_media_and_hype_risk_linkage(self):
        tpl = _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE
        for media in ("新浪财经", "雪球", "同花顺"):
            assert media in tpl
        assert "hype_risk" in tpl  # 与炒作风险评分联动
        assert "加分项" in tpl
