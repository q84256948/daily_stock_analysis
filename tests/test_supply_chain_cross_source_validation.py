# -*- coding: utf-8 -*-
"""供应链双源校验（东方财富 + 同花顺）单元测试。

设计（KISS + 高内聚低耦合，镜像 tests/test_supply_chain_clue_hype_tool.py）：
- 纯逻辑（归一 / 匹配 / 重合度 / 决策表）零 IO，直接断言；
- IO 探针用鸭子类型 fake 注入（DI），无真实网络；
- 覆盖 fail-open（探针异常 / 源不可用不影响另一源）、状态决策表全分支、
  工具注册与 handler 输出契约、prompt 双源校验约束。
"""

from __future__ import annotations

import sys
import types
from typing import Any, List, Tuple

import pytest

from data_provider.supply_chain.cross_source import (
    BOARD_MATCH_CONTAINS,
    BOARD_MATCH_EXACT,
    EastMoneyProbe,
    SourceEvidence,
    SupplyChainCrossSourceValidator,
    ThsAkshareProbe,
    board_match_level,
    code_in_constituents,
    compute_matched_by,
    constituent_overlap_ratio,
    find_matched_boards,
    get_default_validator,
    judge_verification,
    normalize_a_share_code,
    normalize_name,
)
import src.agent.tools.supply_chain_tools as sct
from src.agent.tools.supply_chain_tools import (
    ALL_SUPPLY_CHAIN_TOOLS,
    _handle_verify_supply_chain_evidence,
    verify_supply_chain_evidence_tool,
)
from src.agent.supply_chain_executor import _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE

PROMPT = _SUPPLY_CHAIN_SYSTEM_PROMPT_TEMPLATE


# ============================================================
# 辅助：构造证据 / fake 探针 / fake provider / fake ak
# ============================================================

def _ev(
    source: str = "eastmoney",
    available: bool = True,
    matched: bool = False,
    boards: Tuple[str, ...] = (),
    constituents: Tuple[str, ...] = (),
    error: str = None,
) -> SourceEvidence:
    return SourceEvidence(source, available, matched, boards, constituents, error)


class _RecordingProbe:
    """记录每次 probe 入参的 fake 探针，返回固定证据或抛指定异常。"""

    def __init__(self, name: str, evidence: Any) -> None:
        self.name = name
        self._evidence = evidence
        self.calls: List[Tuple[str, str, str]] = []

    def probe(self, code: str, name: str, keyword: str) -> SourceEvidence:
        self.calls.append((code, name, keyword))
        if isinstance(self._evidence, Exception):
            raise self._evidence
        return self._evidence


class _FakeConceptProvider:
    """东财 ConceptBoardProvider 的鸭子类型 fake。"""

    def __init__(self, boards: list, constituents_map: dict) -> None:
        self._boards = boards
        self._cons = constituents_map

    def get_concept_boards(self) -> list:
        return self._boards

    def get_concept_constituents(self, name: str) -> list:
        return self._cons.get(name, [])


class _FakeDf:
    """akshare DataFrame 的最小鸭子类型：``.columns`` + ``.get(col)`` 返回列或 None。"""

    def __init__(self, columns: dict) -> None:
        self._data = columns
        self.columns = list(columns.keys())

    def get(self, col: str):
        return self._data.get(col)


class _SeriesLike:
    """模拟 pandas Series：可迭代，但 ``bool()`` 歧义（``series or []`` 抛 ValueError）。

    用于回归：真实 akshare 返回 pandas Series，``get(col) or []`` 会触发
    "truth value of a Series is ambiguous"；fake 返回 list 时无法复现此 bug。
    """

    def __init__(self, values: list) -> None:
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def __bool__(self) -> bool:
        raise ValueError("The truth value of a Series is ambiguous.")


class _FakeAk:
    """akshare 模块的鸭子类型 fake（同花顺概念列表；成分股由注入的 http_get 提供）。"""

    def __init__(self, name_df: _FakeDf) -> None:
        self._name_df = name_df

    def stock_board_concept_name_ths(self) -> _FakeDf:
        return self._name_df


# ============================================================
# 纯逻辑：代码归一
# ============================================================

class TestNormalizeAShareCode:
    def test_plain_six_digit_all_valid_prefixes(self):
        assert normalize_a_share_code("300750") == "300750"  # 深市 创业板
        assert normalize_a_share_code("000001") == "000001"  # 深市 主板
        assert normalize_a_share_code("600519") == "600519"  # 沪市
        assert normalize_a_share_code("688981") == "688981"  # 沪市 科创板
        assert normalize_a_share_code("430047") == "430047"  # 北交所
        assert normalize_a_share_code("830799") == "830799"  # 北交所
        assert normalize_a_share_code("920099") == "920099"  # 北交所

    def test_strips_prefix_and_suffix(self):
        assert normalize_a_share_code("sz300750") == "300750"
        assert normalize_a_share_code("SH600519") == "600519"
        assert normalize_a_share_code("bj430047") == "430047"
        assert normalize_a_share_code("300750.SZ") == "300750"
        assert normalize_a_share_code("600519.SH") == "600519"
        assert normalize_a_share_code("430047.BJ") == "430047"

    @pytest.mark.parametrize("code", ["100001", "200002", "500001", "700001"])
    def test_invalid_first_digit_returns_none(self, code):
        assert normalize_a_share_code(code) is None

    @pytest.mark.parametrize(
        "code",
        ["hk00700", "00700", "AAPL", "TSLA", "3007501", "12345", "", "   ", None, 300750],
    )
    def test_non_a_share_or_invalid_returns_none(self, code):
        assert normalize_a_share_code(code) is None


# ============================================================
# 纯逻辑：名称 / 板块名标准化与匹配
# ============================================================

class TestNormalizeName:
    def test_strips_whitespace_and_punct(self):
        assert normalize_name(" 宁德 时代 ") == "宁德时代"
        assert normalize_name("动力　电池") == "动力电池"  # 全角空格
        assert normalize_name("HBM-3E/CoWoS") == "HBM3ECoWoS"

    def test_non_string_returns_empty(self):
        assert normalize_name(None) == ""
        assert normalize_name(123) == ""


class TestBoardMatchLevel:
    def test_exact(self):
        assert board_match_level("动力电池", "动力电池") == BOARD_MATCH_EXACT

    def test_exact_after_normalize(self):
        assert board_match_level(" 动力电池 ", "动力电池") == BOARD_MATCH_EXACT

    def test_contains_keyword_in_board(self):
        assert board_match_level("动力电池", "动力电池产业链") == BOARD_MATCH_CONTAINS

    def test_contains_board_in_keyword(self):
        assert board_match_level("宁德时代概念", "宁德时代") == BOARD_MATCH_CONTAINS

    def test_no_match(self):
        assert board_match_level("动力电池", "半导体") is None

    def test_empty_returns_none(self):
        assert board_match_level("", "动力电池") is None
        assert board_match_level("动力电池", "") is None


class TestFindMatchedBoards:
    def test_filters_and_dedup_in_order(self):
        names = ["半导体", "动力电池", "动力电池概念", "白酒"]
        assert find_matched_boards("动力电池", names) == ("动力电池", "动力电池概念")

    def test_dedup_exact_duplicates(self):
        assert find_matched_boards("动力电池", ["动力电池", "动力电池"]) == ("动力电池",)

    def test_empty_input(self):
        assert find_matched_boards("动力电池", []) == ()
        assert find_matched_boards("动力电池", ["", None]) == ()


# ============================================================
# 纯逻辑：成分股命中与重合度
# ============================================================

class TestCodeInConstituents:
    def test_present(self):
        assert code_in_constituents("300750", ["300750", "002594"]) is True

    def test_present_with_suffix(self):
        assert code_in_constituents("300750", ["300750.SZ", "sz002594"]) is True

    def test_absent(self):
        assert code_in_constituents("300750", ["002594", "600519"]) is False

    def test_empty_code_or_constituents(self):
        assert code_in_constituents("", ["300750"]) is False
        assert code_in_constituents("300750", []) is False
        assert code_in_constituents("300750", None) is False


class TestConstituentOverlapRatio:
    def test_partial_overlap(self):
        # {300750,002594} vs {300750,600519} → 交集1 / 并集3
        assert constituent_overlap_ratio(["300750", "002594"], ["300750", "600519"]) == pytest.approx(1 / 3)

    def test_full_overlap(self):
        assert constituent_overlap_ratio(["300750", "002594"], ["002594", "300750"]) == 1.0

    def test_disjoint(self):
        assert constituent_overlap_ratio(["300750"], ["600519"]) == 0.0

    def test_both_empty(self):
        assert constituent_overlap_ratio([], []) == 0.0

    def test_one_empty(self):
        assert constituent_overlap_ratio(["300750"], []) == 0.0

    def test_normalizes_prefixed_codes(self):
        # 前缀写法归一后仍算同一只
        assert constituent_overlap_ratio(["300750.SZ"], ["sz300750"]) == 1.0


# ============================================================
# 纯逻辑：matched_by 维度汇总
# ============================================================

class TestComputeMatchedBy:
    def test_code_dim(self):
        em = _ev(constituents=("300750",))
        ths = _ev(source="akshare_ths")
        assert compute_matched_by("300750", em, ths, "动力电池") == ("code",)

    def test_code_and_board_name_dims(self):
        em = _ev(boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", boards=("动力电池",))
        assert compute_matched_by("300750", em, ths, "动力电池") == ("code", "board_name")

    def test_board_name_only(self):
        em = _ev(boards=("动力电池",))
        ths = _ev(source="akshare_ths", boards=("动力电池",))
        # 公司不在成分股，但板块名命中
        assert compute_matched_by("300750", em, ths, "动力电池") == ("board_name",)

    def test_no_dim_when_nothing_matches(self):
        em = _ev(boards=("半导体",))
        ths = _ev(source="akshare_ths")
        assert compute_matched_by("300750", em, ths, "动力电池") == ()

    def test_no_board_name_when_hint_empty(self):
        em = _ev(boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths")
        assert compute_matched_by("300750", em, ths, "") == ("code",)


# ============================================================
# 纯逻辑：决策表（judge_verification 全分支）
# ============================================================

class TestJudgeVerification:
    CODE = "300750"
    NAME = "宁德时代"
    HINT = "动力电池"

    def test_confirmed_when_both_matched(self):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750",))
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("confirmed", "high")
        assert r.scope == "a_share"
        assert set(r.matched_by) == {"code", "board_name"}

    def test_conflict_when_both_found_theme_but_disagree(self):
        # 两源都定位到「动力电池」，但同花顺成分股不含目标公司
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750", "002594"))
        ths = _ev(source="akshare_ths", matched=False, boards=("动力电池",), constituents=("002594", "300788"))
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("conflict", "low")
        assert "冲突" in r.note

    def test_partial_when_one_matched_other_found_no_theme(self):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", matched=False, boards=(), constituents=())
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("partial", "medium")

    def test_partial_when_one_source_unavailable_but_other_matched(self):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", available=False, matched=False)
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("partial", "medium")

    def test_partial_when_only_ths_matched(self):
        em = _ev(matched=False, available=True, boards=(), constituents=())
        ths = _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750",))
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("partial", "medium")

    def test_unverified_when_both_available_but_neither_matched(self):
        em = _ev(matched=False, boards=(), constituents=())
        ths = _ev(source="akshare_ths", matched=False, boards=(), constituents=())
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("unverified", "low")
        assert "待核验" in r.note

    def test_unverified_when_one_available_not_matched_other_unavailable(self):
        em = _ev(matched=False, boards=(), constituents=())
        ths = _ev(source="akshare_ths", available=False, matched=False)
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("unverified", "low")

    def test_unverified_when_both_unavailable(self):
        em = _ev(available=False, matched=False)
        ths = _ev(source="akshare_ths", available=False, matched=False)
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        assert (r.status, r.confidence) == ("unverified", "low")

    def test_overlap_ratio_reported(self):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750", "002594"))
        ths = _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750", "600519"))
        r = judge_verification(self.CODE, self.NAME, em, ths, self.HINT)
        # {300750,002594} ∩ {300750,600519} = {300750}；并集3 → 1/3
        assert r.overlap_ratio == pytest.approx(1 / 3)


# ============================================================
# 数据结构：to_dict 序列化
# ============================================================

class TestSerialization:
    def test_source_evidence_to_dict_without_error(self):
        ev = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        d = ev.to_dict()
        assert d == {
            "available": True,
            "matched": True,
            "boards": ["动力电池"],
            "constituents": ["300750"],
            "source": "eastmoney",
        }
        assert "error" not in d

    def test_source_evidence_to_dict_with_error(self):
        ev = _ev(available=False, error="boom")
        assert ev.to_dict()["error"] == "boom"

    def test_verification_result_to_dict_shape(self):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750",))
        r = judge_verification("300750", "宁德时代", em, ths, "动力电池")
        d = r.to_dict()
        assert set(d) == {
            "stock_code", "stock_name", "scope", "status", "confidence",
            "eastmoney", "ths", "overlap", "note",
        }
        assert d["stock_code"] == "300750"
        assert d["status"] == "confirmed"
        assert d["overlap"]["matched_by"] == ["code", "board_name"]
        assert isinstance(d["overlap"]["constituent_overlap_ratio"], float)
        assert d["eastmoney"]["source"] == "eastmoney"
        assert d["ths"]["source"] == "akshare_ths"


# ============================================================
# IO 探针：EastMoneyProbe / ThsAkshareProbe（fail-open）
# ============================================================

class TestEastMoneyProbe:
    def test_probe_matched(self, monkeypatch):
        fake = _FakeConceptProvider(
            boards=[{"name": "动力电池"}, {"name": "半导体"}],
            constituents_map={"动力电池": ["300750", "002594"]},
        )
        # 默认 _resolve 分支：monkeypatch get_concept_board_provider
        import data_provider.supply_chain.concept_board as cb

        monkeypatch.setattr(cb, "get_concept_board_provider", lambda: fake)
        probe = EastMoneyProbe()
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.source == "eastmoney"
        assert ev.available is True
        assert ev.matched is True
        assert ev.boards == ("动力电池",)
        assert "300750" in ev.constituents

    def test_probe_not_matched(self):
        fake = _FakeConceptProvider(
            boards=[{"name": "动力电池"}],
            constituents_map={"动力电池": ["002594"]},
        )
        probe = EastMoneyProbe(provider=fake)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.matched is False
        assert ev.boards == ("动力电池",)

    def test_probe_no_board_matches(self):
        fake = _FakeConceptProvider(boards=[{"name": "白酒"}], constituents_map={})
        probe = EastMoneyProbe(provider=fake)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.available is True
        assert ev.matched is False
        assert ev.boards == ()
        assert ev.constituents == ()


class TestConceptPairs:
    def test_name_code_columns(self):
        df = _FakeDf({"name": ["动力电池", "半导体"], "code": ["300733", "300099"]})
        assert ThsAkshareProbe._concept_pairs(df) == [("动力电池", "300733"), ("半导体", "300099")]

    def test_chinese_column_fallback(self):
        df = _FakeDf({"概念名称": ["动力电池"], "代码": ["300733"]})
        assert ThsAkshareProbe._concept_pairs(df) == [("动力电池", "300733")]

    def test_column_drift_returns_empty(self):
        df = _FakeDf({"foo": ["x"], "bar": ["y"]})
        assert ThsAkshareProbe._concept_pairs(df) == []

    def test_none_returns_empty(self):
        assert ThsAkshareProbe._concept_pairs(None) == []

    def test_no_columns_attribute_returns_empty(self):
        class _NoCols:
            pass

        assert ThsAkshareProbe._concept_pairs(_NoCols()) == []

    def test_handles_pandas_series_truthiness(self):
        # 回归：真实 akshare 返回 pandas Series，``or []`` 会抛 ValueError
        df = _FakeDf({"name": _SeriesLike(["动力电池", "半导体"]), "code": _SeriesLike(["300733", "300099"])})
        assert ThsAkshareProbe._concept_pairs(df) == [("动力电池", "300733"), ("半导体", "300099")]


class TestThsAkshareProbe:
    @staticmethod
    def _ak_with(concepts: list[tuple[str, str]]) -> _FakeAk:
        return _FakeAk(_FakeDf({"name": [n for n, _ in concepts], "code": [c for _, c in concepts]}))

    def test_probe_matched(self):
        ak = self._ak_with([("动力电池", "300733"), ("新能源车", "300050")])
        http_get = lambda code, page: f"<td>{code}</td><td>300750</td><td>002594</td>" if code == "300733" else ""
        probe = ThsAkshareProbe(akshare_module=ak, http_get=http_get)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.source == "akshare_ths"
        assert ev.available is True
        assert ev.matched is True
        assert ev.boards == ("动力电池",)
        assert "300750" in ev.constituents

    def test_probe_not_matched(self):
        ak = self._ak_with([("动力电池", "300733")])
        http_get = lambda code, page: "<td>002594</td>"  # 不含目标公司
        probe = ThsAkshareProbe(akshare_module=ak, http_get=http_get)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.matched is False

    def test_probe_paginates_until_empty(self):
        # page1 有 1 只，page2 有 2 只，page3 空 → 停止翻页，合并 3 只
        ak = self._ak_with([("动力电池", "300733")])
        pages = {1: "<td>300750</td>", 2: "<td>002594</td><td>300996</td>", 3: "<no codes here>"}
        called = []

        def http_get(code, page):
            called.append(page)
            return pages.get(page, "")

        probe = ThsAkshareProbe(akshare_module=ak, http_get=http_get)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.matched is True
        assert set(ev.constituents) == {"300750", "002594", "300996"}
        assert called == [1, 2, 3]  # 第 3 页空 → 停

    def test_probe_pagination_cap(self):
        # 每页都有码、永不空 → 翻到封顶 _MAX_THS_PAGES
        ak = self._ak_with([("动力电池", "300733")])
        called = []

        def http_get(code, page):
            called.append(page)
            return f"<td>3{page:05d}</td>"

        probe = ThsAkshareProbe(akshare_module=ak, http_get=http_get)
        probe.probe("300750", "宁德时代", "动力电池")
        assert len(called) == ThsAkshareProbe._MAX_THS_PAGES

    def test_probe_http_get_failure_isolated(self):
        # 两个概念都匹配关键词；其中一个 http_get 抛异常 → 跳过它，另一个仍取数
        ak = self._ak_with([("动力电池甲", "000001"), ("动力电池乙", "300733")])

        def http_get(code, page):
            if code == "000001":
                raise RuntimeError("timeout")
            return "<td>300750</td>"

        probe = ThsAkshareProbe(akshare_module=ak, http_get=http_get)
        ev = probe.probe("300750", "宁德时代", "动力电池")
        # 动力电池乙命中，动力电池甲抓取失败被跳过
        assert ev.available is True
        assert ev.matched is True
        assert "动力电池乙" in ev.boards

    def test_probe_unavailable_when_akshare_missing(self, monkeypatch):
        # import akshare → ImportError（sys.modules 置 None 强制触发）
        monkeypatch.setitem(sys.modules, "akshare", None)
        probe = ThsAkshareProbe()
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.available is False
        assert ev.matched is False
        assert ev.error  # 含错误摘要

    def test_resolve_http_get_default(self, monkeypatch):
        # 默认 http_get 走 requests（注入 fake requests 模块，零真实网络）
        class _FakeResp:
            content = "<td>300750</td><td>002594</td>".encode("gbk")

        fake_requests = types.SimpleNamespace(
            get=lambda url, headers=None, timeout=None: _FakeResp()
        )
        monkeypatch.setitem(sys.modules, "requests", fake_requests)
        probe = ThsAkshareProbe()
        getter = probe._resolve_http_get()
        html = getter("309084", 1)
        assert "300750" in html  # GBK 解码后含成分股代码

    def test_probe_default_resolve_with_fake_akshare(self, monkeypatch):
        # import akshare 成功分支 + 显式 http_get：注入 fake akshare，http_get 显式注入
        ak = self._ak_with([("动力电池", "300733")])
        monkeypatch.setitem(sys.modules, "akshare", ak)
        probe = ThsAkshareProbe(http_get=lambda code, page: "<td>300750</td>" if page == 1 else "")
        ev = probe.probe("300750", "宁德时代", "动力电池")
        assert ev.available is True
        assert ev.matched is True
        assert ev.source == "akshare_ths"
        assert ev.boards == ("动力电池",)


# ============================================================
# 编排：SupplyChainCrossSourceValidator
# ============================================================

class TestValidator:
    def test_not_applicable_skips_probes(self):
        em = _RecordingProbe("eastmoney", _ev())
        ths = _RecordingProbe("akshare_ths", _ev(source="akshare_ths"))
        v = SupplyChainCrossSourceValidator(em, ths)
        r = v.verify("hk00700", "腾讯", claim="x")
        assert (r.status, r.confidence) == ("not_applicable", "low")
        assert r.scope == "not_applicable"
        assert em.calls == [] and ths.calls == []  # 探针未被调用

    def test_not_applicable_for_us(self):
        v = SupplyChainCrossSourceValidator(
            _RecordingProbe("eastmoney", _ev()), _RecordingProbe("akshare_ths", _ev(source="akshare_ths"))
        )
        r = v.verify("AAPL", "Apple", claim="x")
        assert r.status == "not_applicable"

    def test_keyword_fallback_board_hint_first(self):
        em = _RecordingProbe("eastmoney", _ev(matched=True, constituents=("300750",)))
        ths = _RecordingProbe("akshare_ths", _ev(source="akshare_ths", matched=True, constituents=("300750",)))
        v = SupplyChainCrossSourceValidator(em, ths)
        v.verify("300750", "宁德时代", board_hint="动力电池", topic="新能源")
        assert em.calls[-1][2] == "动力电池"  # board_hint 优先

    def test_keyword_fallback_to_topic(self):
        em = _RecordingProbe("eastmoney", _ev())
        ths = _RecordingProbe("akshare_ths", _ev(source="akshare_ths"))
        v = SupplyChainCrossSourceValidator(em, ths)
        v.verify("300750", "宁德时代", board_hint="", topic="新能源车电池")
        assert em.calls[-1][2] == "新能源车电池"

    def test_keyword_fallback_to_name(self):
        em = _RecordingProbe("eastmoney", _ev())
        ths = _RecordingProbe("akshare_ths", _ev(source="akshare_ths"))
        v = SupplyChainCrossSourceValidator(em, ths)
        v.verify("300750", "宁德时代", board_hint="", topic="")
        assert em.calls[-1][2] == "宁德时代"  # 最后回退名称

    def test_probe_exception_isolated(self):
        # 东财探针抛异常 → available=False，不影响同花顺判定
        em = _RecordingProbe("eastmoney", RuntimeError("network down"))
        ths = _RecordingProbe("akshare_ths", _ev(source="akshare_ths", matched=True, constituents=("300750",)))
        v = SupplyChainCrossSourceValidator(em, ths)
        r = v.verify("300750", "宁德时代", board_hint="动力电池")
        assert r.eastmoney.available is False
        assert "network down" in r.eastmoney.error
        assert r.eastmoney.source == "eastmoney"
        # 同花顺仍命中 → partial
        assert (r.status, r.confidence) == ("partial", "medium")

    def test_end_to_end_confirmed(self):
        em = _RecordingProbe("eastmoney", _ev(matched=True, boards=("动力电池",), constituents=("300750",)))
        ths = _RecordingProbe(
            "akshare_ths", _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750",))
        )
        v = SupplyChainCrossSourceValidator(em, ths)
        r = v.verify("300750", "宁德时代", claim="核心中游制造商", board_hint="动力电池")
        assert (r.status, r.confidence) == ("confirmed", "high")


# ============================================================
# 默认校验器单例
# ============================================================

class TestDefaultValidator:
    def test_singleton_and_probe_types(self):
        v1 = get_default_validator()
        v2 = get_default_validator()
        assert v1 is v2
        assert isinstance(v1._em, EastMoneyProbe)
        assert isinstance(v1._ths, ThsAkshareProbe)


# ============================================================
# 工具层：注册 / handler / 输出契约
# ============================================================

class TestVerifyTool:
    def test_registered_in_supply_chain_tools(self):
        names = {t.name for t in ALL_SUPPLY_CHAIN_TOOLS}
        assert "verify_supply_chain_evidence" in names

    def test_metadata(self):
        tool = verify_supply_chain_evidence_tool
        assert tool.name == "verify_supply_chain_evidence"
        assert tool.category == "analysis"
        param_names = {p.name for p in tool.parameters}
        assert {"stock_code", "stock_name", "claim", "board_hint", "topic"} == param_names
        required = {p.name for p in tool.parameters if p.required}
        assert {"stock_code", "stock_name", "claim"} <= required
        assert {"board_hint", "topic"}.isdisjoint(required)  # 可选

    def test_handler_returns_confirmed_dict(self, monkeypatch):
        em = _ev(matched=True, boards=("动力电池",), constituents=("300750",))
        ths = _ev(source="akshare_ths", matched=True, boards=("动力电池",), constituents=("300750",))
        fake_validator = SupplyChainCrossSourceValidator(
            _RecordingProbe("eastmoney", em), _RecordingProbe("akshare_ths", ths)
        )
        monkeypatch.setattr(sct, "_get_supply_chain_validator", lambda: fake_validator)
        out = _handle_verify_supply_chain_evidence(
            stock_code="300750", stock_name="宁德时代", claim="核心中游制造商", board_hint="动力电池"
        )
        assert out["status"] == "confirmed"
        assert out["confidence"] == "high"
        assert out["scope"] == "a_share"
        assert out["eastmoney"]["source"] == "eastmoney"
        assert out["ths"]["source"] == "akshare_ths"
        assert out["overlap"]["matched_by"] == ["code", "board_name"]
        assert "note" in out

    def test_handler_not_applicable_for_hk(self, monkeypatch):
        # 非 A 股：不调探针即返回 not_applicable
        em = _RecordingProbe("eastmoney", RuntimeError("should not be called"))
        ths = _RecordingProbe("akshare_ths", RuntimeError("should not be called"))
        fake_validator = SupplyChainCrossSourceValidator(em, ths)
        monkeypatch.setattr(sct, "_get_supply_chain_validator", lambda: fake_validator)
        out = _handle_verify_supply_chain_evidence(
            stock_code="hk00700", stock_name="腾讯", claim="游戏产业链"
        )
        assert out["status"] == "not_applicable"
        assert out["scope"] == "not_applicable"
        assert em.calls == [] and ths.calls == []

    def test_handler_normalizes_prefixed_code(self, monkeypatch):
        em = _ev(matched=True, constituents=("300750",))
        ths = _ev(source="akshare_ths", matched=True, constituents=("300750",))
        fake_validator = SupplyChainCrossSourceValidator(
            _RecordingProbe("eastmoney", em), _RecordingProbe("akshare_ths", ths)
        )
        monkeypatch.setattr(sct, "_get_supply_chain_validator", lambda: fake_validator)
        out = _handle_verify_supply_chain_evidence(
            stock_code="sz300750", stock_name="宁德时代", claim="x", board_hint="动力电池"
        )
        assert out["stock_code"] == "300750"  # 归一为 6 位
        assert out["status"] == "confirmed"


# ============================================================
# Prompt 层：双源校验约束
# ============================================================

class TestPromptConstraints:
    @pytest.mark.parametrize(
        "needle",
        [
            "东方财富", "同花顺", "双源校验", "待核验", "双源状态",
            "verify_supply_chain_evidence", "confirmed", "partial",
            "conflict", "unverified", "not_applicable",
            "东财校验", "同花顺校验", "口径冲突",
        ],
    )
    def test_prompt_contains(self, needle):
        assert needle in PROMPT, f"prompt 缺少关键约束: {needle}"
