# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — 确定性评分卡（纯函数，无 LLM / 无网络）。

设计：
- LLM 负责"判断"（α 公告扫描 + β 政策分析 → 给出六维方向评分与 α/β 头条分）。
- 本模块负责"确定性聚合"：六维加权 → ``dimension_composite``；α/β 按 horizon
  再权重 → ``horizon_blend``；二者按 ``W_DIM``/``W_BLEND`` 合成 → ``final``
  （clamp 到 [-100, 100]）→ 5 档等级 + 仓位指令 + 预期冲击区间 + Markdown。

镜像 ``serenity_scorecard`` 的"LLM 评因子 → 工具确定性合成"模型，但为原生可导入
模块（无 importlib、无 json 配置），权重/档位为模块级常量。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ============================================================
# 常量（单一真源）
# ============================================================

DIMENSION_KEYS: tuple[str, ...] = (
    "event_importance",      # 事件重要性
    "policy_exposure",       # 政策相关度/暴露度
    "earnings_impact",       # 盈利影响
    "valuation_impact",      # 估值影响
    "price_sensitivity",     # 股价敏感度
    "time_urgency",          # 时间紧迫度
)

DIMENSION_WEIGHTS: Dict[str, float] = {
    "event_importance": 0.20,
    "policy_exposure": 0.20,
    "earnings_impact": 0.25,
    "valuation_impact": 0.15,
    "price_sensitivity": 0.10,
    "time_urgency": 0.10,
}  # 和 = 1.0

DIMENSION_LABELS_ZH: Dict[str, str] = {
    "event_importance": "事件重要性",
    "policy_exposure": "政策相关度/暴露度",
    "earnings_impact": "盈利影响",
    "valuation_impact": "估值影响",
    "price_sensitivity": "股价敏感度",
    "time_urgency": "时间紧迫度",
}

# horizon → (alpha 权重, beta 权重)；短期公司公告主导，长期宏观政策主导
HORIZON_BLEND: Dict[str, tuple[float, float]] = {
    "short": (0.70, 0.30),
    "medium": (0.50, 0.50),
    "long": (0.30, 0.70),
}

W_DIM = 0.6    # 六维分析的权重
W_BLEND = 0.4  # α/β 头条分（按 horizon 再权重）的权重

# 5 档等级（按 lo 降序；lo 含义：final >= lo 即落入该档）
TIERS: List[Dict[str, Any]] = [
    {
        "key": "strong_bull", "lo": 70, "emoji": "🟢", "label": "强利好", "action": "加仓",
        "car": {"1d": (2.0, 5.0), "3d": (3.0, 8.0), "10d": (5.0, 12.0)},
    },
    {
        "key": "bull", "lo": 30, "emoji": "🟡", "label": "中等利好", "action": "增持",
        "car": {"1d": (0.5, 2.0), "3d": (1.0, 3.0), "10d": (2.0, 5.0)},
    },
    {
        "key": "neutral", "lo": -30, "emoji": "⚪", "label": "中性", "action": "持有/观望",
        "car": {"1d": (-0.5, 0.5), "3d": (-1.0, 1.0), "10d": (-2.0, 2.0)},
    },
    {
        "key": "bear", "lo": -70, "emoji": "🟠", "label": "中等利空", "action": "减持",
        "car": {"1d": (-2.0, -0.5), "3d": (-3.0, -1.0), "10d": (-5.0, -2.0)},
    },
    {
        "key": "strong_bear", "lo": -100, "emoji": "🔴", "label": "强利空", "action": "清仓/回避",
        "car": {"1d": (-5.0, -2.0), "3d": (-8.0, -3.0), "10d": (-15.0, -5.0)},
    },
]

DISCLAIMER = "本分析基于公开信息，历史表现不代表未来，不构成投资建议，买卖由你自己决定。"
CAR_NOTE = "历史经验区间，非精确预测"


# ============================================================
# 规整辅助
# ============================================================

def _clamp_unit(value: float) -> float:
    """限制到 [-100, 100]。"""
    if value > 100.0:
        return 100.0
    if value < -100.0:
        return -100.0
    return value


def _coerce_dim(value: Any) -> float:
    """把一个维度评分规整为 [-100,100] 的 float；非法/缺失归 0。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return _clamp_unit(number)


def _coerce_optional(value: Any) -> Optional[float]:
    """α/β 头条分：None/缺失保持 None（走降级），否则 clamp 到 [-100,100]。"""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return _clamp_unit(number)


def _tier_for(final: float) -> Dict[str, Any]:
    """返回 final 命中的档位（TIERS 已按 lo 降序）。"""
    for tier in TIERS:
        if final >= tier["lo"]:
            return tier
    return TIERS[-1]  # 兜底（clamp 后 final>=-100，必然命中上一行）


def _normalize_horizon(horizon: Any) -> str:
    return horizon if horizon in HORIZON_BLEND else "medium"


# ============================================================
# score
# ============================================================

def score(payload: Dict[str, Any], horizon: str) -> Dict[str, Any]:
    """对一份排雷 payload 计算结构化评分结果。

    payload 字段：stock_code/stock_name/dimensions(六维 -100~100)/alpha_score/
    beta_score/dominant_factor/confidence/scenarios/evidence。
    """
    payload = payload or {}
    horizon = _normalize_horizon(horizon)
    wa, wb = HORIZON_BLEND[horizon]

    # 1) 六维加权 → dimension_composite
    dims_raw = payload.get("dimensions") or {}
    dims: Dict[str, float] = {key: _coerce_dim(dims_raw.get(key, 0)) for key in DIMENSION_KEYS}
    dimension_composite = round(sum(dims[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_KEYS))
    dimension_composite = int(_clamp_unit(dimension_composite))

    # 2) α/β 头条分按 horizon 再权重 → horizon_blend（缺失走降级）
    alpha = _coerce_optional(payload.get("alpha_score"))
    beta = _coerce_optional(payload.get("beta_score"))
    horizon_blend: float
    if alpha is None and beta is None:
        horizon_blend = dimension_composite
    elif alpha is None:
        # beta 在此分支必然非 None（两者皆 None 已由上一分支处理）
        horizon_blend = beta if beta is not None else dimension_composite
    elif beta is None:
        horizon_blend = alpha if alpha is not None else dimension_composite
    else:
        horizon_blend = int(_clamp_unit(round(wa * alpha + wb * beta)))

    # 3) 合成 final
    final = int(_clamp_unit(round(W_DIM * dimension_composite + W_BLEND * horizon_blend)))

    tier = _tier_for(final)
    dimension_details = {
        key: {"score": dims[key], "weight": DIMENSION_WEIGHTS[key]} for key in DIMENSION_KEYS
    }

    return {
        "stock_code": payload.get("stock_code", ""),
        "stock_name": payload.get("stock_name", ""),
        "final": final,
        "dimension_composite": dimension_composite,
        "horizon_blend": horizon_blend,
        "alpha_score": alpha,
        "beta_score": beta,
        "horizon": horizon,
        "tier": tier["key"],
        "emoji": tier["emoji"],
        "label": tier["label"],
        "action": tier["action"],
        "expected_car": tier["car"],
        "dimension_details": dimension_details,
        "dominant_factor": payload.get("dominant_factor", ""),
        "confidence": payload.get("confidence"),
        "scenarios": payload.get("scenarios", {}),
        "evidence": payload.get("evidence", []),
        "disclaimer": DISCLAIMER,
        "car_note": CAR_NOTE,
    }


# ============================================================
# to_markdown（中文人话标签，不泄露内部字段名）
# ============================================================

def to_markdown(result: Dict[str, Any]) -> str:
    """把 score() 的结果渲染成结构化排雷 Markdown。"""
    name = result.get("stock_name") or "未知"
    code = result.get("stock_code") or ""
    title = f"{name}（{code}）" if code else name

    lines: List[str] = [
        f"# 政策与公告双维度排雷：{title}",
        "",
        f"{result.get('emoji', '')} **{result.get('label', '')}**　"
        f"综合分 **{result.get('final', 0)}**　置信度 **{_fmt_conf(result.get('confidence'))}**",
        f"仓位指令：**{result.get('action', '')}**",
        "",
        "## 预期冲击区间",
        f"_{result.get('car_note', '')}_",
        "",
        "| 窗口 | 区间 |",
        "|---|---|",
    ]
    car = result.get("expected_car", {})
    for window, label in (("1d", "1日"), ("3d", "3日"), ("10d", "10日")):
        lo, hi = car.get(window, (0, 0))
        lines.append(f"| {label} | {lo}% ~ {hi}% |")

    lines.extend([
        "",
        "## 公司层面 / 政策层面",
        f"- 公司层面（α）：{_fmt_score(result.get('alpha_score'))}",
        f"- 政策层面（β）：{_fmt_score(result.get('beta_score'))}",
        f"- 主导因子：{result.get('dominant_factor', '') or '—'}",
        "",
        "## 六维评分明细",
        "| 维度 | 评分 | 权重 |",
        "|---|---:|---:|",
    ])
    for key in DIMENSION_KEYS:
        detail = result.get("dimension_details", {}).get(key, {})
        lines.append(
            f"| {DIMENSION_LABELS_ZH[key]} | {detail.get('score', 0)} | {detail.get('weight', 0)} |"
        )

    scenarios = result.get("scenarios") or {}
    if scenarios:
        lines.extend(["", "## 情景分析", "| 情景 | 假设 | 评分 |", "|---|---|---:|"])
        for skey, label in (("optimistic", "乐观"), ("base_case", "基准"), ("pessimistic", "悲观")):
            item = scenarios.get(skey) or {}
            lines.append(
                f"| {label} | {item.get('assumption', '—')} | {item.get('score', '—')} |"
            )

    evidence = result.get("evidence") or []
    if evidence:
        lines.extend(["", "## 证据"])
        for ev in evidence:
            if isinstance(ev, dict):
                claim = str(ev.get("claim", "")).strip()
                source = str(ev.get("source", "")).strip()
                date = str(ev.get("date", "")).strip()
                strength = str(ev.get("strength", "")).strip()
                url = str(ev.get("url", "")).strip()
                if claim or source:
                    line = f"- [{strength}] {claim} — {source}（{date}）"
                    if url:
                        # 公司公告原文地址（α 从检索工具结果捕获），作为可核验证据链接
                        line += f" [原文]({url})"
                    lines.append(line)

    lines.extend(["", "---", result.get("disclaimer", DISCLAIMER), ""])
    return "\n".join(lines)


def _fmt_conf(conf: Any) -> str:
    try:
        return f"{int(round(float(conf) * 100))}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_score(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):+d}"
    except (TypeError, ValueError):
        return "—"
