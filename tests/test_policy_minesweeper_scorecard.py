# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — scorecard 纯函数单元测试。

不依赖 LLM 与网络，只验证六维加权、horizon 动态权重、5 档映射、
降级容错与 Markdown 渲染契约（中文标签、不泄露内部字段名、强制免责声明）。
"""

from __future__ import annotations

import math

from src.services.policy_minesweeper_scorecard import (
    DIMENSION_KEYS,
    DIMENSION_LABELS_ZH,
    DIMENSION_WEIGHTS,
    HORIZON_BLEND,
    TIERS,
    W_BLEND,
    W_DIM,
    score,
    to_markdown,
)


# ---------------------------------------------------------------- helpers

def _dims(value: float) -> dict:
    """六个维度全设为同一个值。"""
    return {key: value for key in DIMENSION_KEYS}


def _payload(**overrides) -> dict:
    """构造一份完整 payload；alpha/beta/dims 默认全 0。"""
    data = {
        "stock_code": "300750",
        "stock_name": "示例公司",
        "dimensions": _dims(0.0),
        "alpha_score": 0.0,
        "beta_score": 0.0,
        "dominant_factor": "宏观与公司层面信号均衡",
        "confidence": 0.5,
        "scenarios": {
            "optimistic": {"assumption": "政策缓和", "score": 40},
            "base_case": {"assumption": "维持现状", "score": 0},
            "pessimistic": {"assumption": "政策升级", "score": -40},
        },
        "evidence": [
            {"claim": "签订重大合同", "source": "巨潮公告", "date": "2026-06-20", "strength": "primary"}
        ],
    }
    data.update(overrides)
    return data


def _aligned(x: float) -> dict:
    """dims / alpha / beta 全部 = x，使 final == x（便于命中档位边界）。"""
    return _payload(dimensions=_dims(x), alpha_score=x, beta_score=x)


# ============================================================
# 常量完整性（防漂移）
# ============================================================

class TestConstants:
    def test_dimension_weights_sum_to_one(self):
        assert math.isclose(sum(DIMENSION_WEIGHTS.values()), 1.0)

    def test_dimension_keys_match_weights_and_labels(self):
        assert set(DIMENSION_WEIGHTS) == set(DIMENSION_KEYS) == set(DIMENSION_LABELS_ZH)

    def test_horizon_blend_partitions_sum_to_one(self):
        for wa, wb in HORIZON_BLEND.values():
            assert math.isclose(wa + wb, 1.0)
            assert 0.0 <= wa <= 1.0 and 0.0 <= wb <= 1.0

    def test_weights_combination_is_one(self):
        assert math.isclose(W_DIM + W_BLEND, 1.0)

    def test_tiers_cover_full_range_and_descending(self):
        los = [t["lo"] for t in TIERS]
        assert los == sorted(los, reverse=True), "TIERS 必须按 lo 降序"
        assert los[0] == 70 and los[-1] == -100
        # 每档必须有 emoji/label/action/car
        for t in TIERS:
            assert {"key", "lo", "emoji", "label", "action", "car"} <= set(t)
            assert set(t["car"]) == {"1d", "3d", "10d"}


# ============================================================
# score() 基本契约
# ============================================================

class TestScoreBasic:
    def test_returns_dict_with_required_keys(self):
        result = score(_payload(), "medium")
        assert isinstance(result, dict)
        for key in (
            "stock_code", "stock_name", "final", "dimension_composite",
            "horizon_blend", "tier", "action", "emoji", "label",
            "expected_car", "dimension_details", "alpha_score", "beta_score",
            "confidence", "dominant_factor", "scenarios", "evidence",
            "disclaimer", "car_note",
        ):
            assert key in result, f"缺失字段 {key}"

    def test_final_in_valid_range(self):
        for x in (-100, -50, 0, 50, 100):
            result = score(_aligned(x), "medium")
            assert -100 <= result["final"] <= 100

    def test_aligned_input_final_equals_x(self):
        # dims=alpha=beta=x 且 blend=alpha=beta → final == x
        for x in (-77, -1, 0, 33, 88):
            assert score(_aligned(x), "medium")["final"] == x


# ============================================================
# 六维加权 & clamp
# ============================================================

class TestDimensionWeighting:
    def test_all_max_dims_max_composite(self):
        result = score(_payload(dimensions=_dims(100), alpha_score=None, beta_score=None), "medium")
        assert result["dimension_composite"] == 100

    def test_all_min_dims_min_composite(self):
        result = score(_payload(dimensions=_dims(-100), alpha_score=None, beta_score=None), "medium")
        assert result["dimension_composite"] == -100

    def test_oversize_dims_clamped(self):
        # 超出 ±100 应被 clamp，不报错
        result = score(_payload(dimensions=_dims(99999)), "medium")
        assert result["dimension_composite"] == 100

    def test_undersize_dims_clamped(self):
        result = score(_payload(dimensions=_dims(-99999)), "medium")
        assert result["dimension_composite"] == -100

    def test_missing_dimension_treated_as_zero(self):
        dims = {"event_importance": 100}  # 其余缺失
        result = score(_payload(dimensions=dims, alpha_score=None, beta_score=None), "medium")
        # 只有 1 个维度=100(权重 0.20)，其余 0
        assert result["dimension_composite"] == 20

    def test_invalid_dimension_coerced_to_zero(self):
        dims = {"event_importance": "not-a-number", "policy_exposure": 50}
        result = score(_payload(dimensions=dims, alpha_score=None, beta_score=None), "medium")
        # event_importance 非法→0；policy_exposure=50(权重 0.20)→10
        assert result["dimension_composite"] == 10

    def test_dimension_details_present(self):
        result = score(_payload(), "medium")
        assert set(result["dimension_details"]) == set(DIMENSION_KEYS)
        for key, detail in result["dimension_details"].items():
            assert {"score", "weight"} <= set(detail)


# ============================================================
# horizon 动态权重（α/β 再权重）
# ============================================================

class TestHorizonBlend:
    def test_short_favors_alpha_medium_balanced_long_favors_beta(self):
        # alpha=100, beta=-100, dims=0 → blend 随 horizon 变化
        p = _payload(dimensions=_dims(0), alpha_score=100, beta_score=-100)
        short = score(p, "short")["final"]
        medium = score(p, "medium")["final"]
        long_ = score(p, "long")["final"]
        assert short > medium > long_
        # short 偏多(>0)，long 偏空(<0)
        assert short > 0 and long_ < 0

    def test_invalid_horizon_defaults_to_medium(self):
        p = _payload(dimensions=_dims(0), alpha_score=100, beta_score=-100)
        assert score(p, "nonsense")["final"] == score(p, "medium")["final"]

    def test_both_alpha_beta_missing_blend_falls_back_to_composite(self):
        # alpha/beta 都缺 → blend = dimension_composite → final == composite
        p = _payload(dimensions=_dims(40), alpha_score=None, beta_score=None)
        result = score(p, "medium")
        assert result["horizon_blend"] == 40
        assert result["final"] == 40

    def test_one_of_alpha_beta_missing_uses_present_one(self):
        # beta 缺 → blend = alpha（任意 horizon 权重都退化为 present 值）
        p = _payload(dimensions=_dims(0), alpha_score=80, beta_score=None)
        assert score(p, "short")["horizon_blend"] == 80
        p2 = _payload(dimensions=_dims(0), alpha_score=None, beta_score=-60)
        assert score(p2, "long")["horizon_blend"] == -60


# ============================================================
# 5 档映射（边界）
# ============================================================

class TestTierMapping:
    def test_boundaries(self):
        assert score(_aligned(70), "medium")["tier"] == "strong_bull"
        assert score(_aligned(69), "medium")["tier"] == "bull"
        assert score(_aligned(30), "medium")["tier"] == "bull"
        assert score(_aligned(29), "medium")["tier"] == "neutral"
        assert score(_aligned(-30), "medium")["tier"] == "neutral"
        assert score(_aligned(-31), "medium")["tier"] == "bear"
        assert score(_aligned(-70), "medium")["tier"] == "bear"
        assert score(_aligned(-71), "medium")["tier"] == "strong_bear"
        assert score(_aligned(-100), "medium")["tier"] == "strong_bear"

    def test_action_and_emoji_match_tier(self):
        for t in TIERS:
            result = score(_aligned(t["lo"]), "medium")
            assert result["emoji"] == t["emoji"]
            assert result["label"] == t["label"]
            assert result["action"] == t["action"]

    def test_expected_car_attached(self):
        result = score(_aligned(80), "medium")
        assert result["expected_car"] == {
            t["key"]: t["car"] for t in TIERS
        }["strong_bull"]


# ============================================================
# 单调性 sanity
# ============================================================

class TestMonotonicity:
    def test_more_bullish_higher_final(self):
        bull = score(_aligned(60), "medium")["final"]
        bear = score(_aligned(-60), "medium")["final"]
        assert bull > bear


# ============================================================
# Markdown 渲染契约
# ============================================================

class TestMarkdown:
    def test_renders_core_sections(self):
        result = score(_aligned(-35), "medium")
        md = to_markdown(result)
        assert isinstance(md, str)
        # 等级 / 仓位指令 / 预期冲击 / 六维 / 情景 / 证据 / 免责
        assert result["emoji"] in md
        assert result["action"] in md
        assert "预期冲击" in md
        assert "六维" in md or "维度" in md
        assert "情景" in md
        assert "巨潮公告" in md  # 证据来源出现
        assert "不构成投资建议" in md
        assert result["car_note"] in md

    def test_no_internal_field_names_leaked(self):
        result = score(_payload(), "medium")
        md = to_markdown(result)
        # 不得泄露内部 snake_case 维度 key / tier key
        for key in DIMENSION_KEYS:
            assert key not in md
        assert "strong_bull" not in md and "strong_bear" not in md

    def test_uses_chinese_dimension_labels(self):
        result = score(_payload(), "medium")
        md = to_markdown(result)
        for label in DIMENSION_LABELS_ZH.values():
            assert label in md


# ============================================================
# 防御性分支（formatter / coerce 容错，不得崩）
# ============================================================

class TestDefensiveBranches:
    def test_non_numeric_alpha_beta_coerced_to_none(self):
        result = score(_payload(alpha_score="bad", beta_score="x"), "medium")
        assert result["alpha_score"] is None
        assert result["beta_score"] is None
        # 两者都 None → blend 回退到 dimension_composite
        assert result["horizon_blend"] == result["dimension_composite"]

    def test_tier_for_fallback_below_range(self):
        from src.services.policy_minesweeper_scorecard import _tier_for

        assert _tier_for(-999)["key"] == "strong_bear"

    def test_markdown_handles_invalid_confidence(self):
        result = score(_payload(confidence=None), "medium")
        md = to_markdown(result)  # 不崩
        assert "—" in md

    def test_markdown_handles_missing_alpha_beta(self):
        result = score(_payload(alpha_score=None, beta_score=None), "medium")
        md = to_markdown(result)
        # α/β 缺失 → 各渲染一个 "—"
        assert md.count("—") >= 2

    def test_markdown_handles_garbage_alpha(self):
        # 绕过 score() 直接喂 formatter 非法值，不得崩
        result = score(_payload(), "medium")
        result["alpha_score"] = "garbage"
        md = to_markdown(result)
        assert isinstance(md, str)
