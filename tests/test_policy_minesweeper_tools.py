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
    _handle_score_policy_minesweeper,
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
    def test_single_tool(self):
        assert len(ALL_POLICY_MINESWEEPER_TOOLS) == 1
        tool = ALL_POLICY_MINESWEEPER_TOOLS[0]
        assert tool.name == "score_policy_minesweeper"
        assert tool.category == "analysis"

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
