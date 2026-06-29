# -*- coding: utf-8 -*-
"""郑希框架评分的机械指标计算。

移植自 zhengxi-views/scripts/score_fund.py 的纯计算部分
（换手代理、集中度、区间收益、最大回撤），不依赖任何抓取逻辑。
所有函数对缺失数据返回 ``None``，由调用方决定如何标注。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Tuple

# 一个净值点：(毫秒时间戳, 净值)
NavPoint = Tuple[int, float]


def turnover_proxy(quarters: List[dict[str, Any]]) -> Optional[float]:
    """季度间换手代理（%）。

    取近 5 季，计算相邻季度前十大重仓股"重叠率之补"的平均：
    重叠越低 → 换手越高 → 越像郑希所说的"周期拼接"。
    """
    qs = sorted(quarters, key=lambda q: (q.get("year", 0), q.get("quarter", 0)))[-5:]
    diffs: List[float] = []
    for prev, curr in zip(qs, qs[1:]):
        sa = {h.get("股票代码") for h in prev.get("holdings", []) if h.get("股票代码")}
        sb = {h.get("股票代码") for h in curr.get("holdings", []) if h.get("股票代码")}
        if sa and sb:
            diffs.append(1 - len(sa & sb) / max(len(sb), 1))
    if not diffs:
        return None
    return round(sum(diffs) / len(diffs) * 100, 1)


def _parse_pct(value: Any) -> float:
    """``"2.53%"`` -> ``2.53``；无法解析返回 ``0.0``。"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().rstrip("%").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def concentration(holdings: List[dict[str, Any]]) -> Optional[float]:
    """前十大重仓占净值比之和（%）。"""
    if not holdings:
        return None
    return round(sum(_parse_pct(h.get("占净值比")) for h in holdings), 1)


def nav_series(raw: Any) -> List[NavPoint]:
    """从"累计净值走势"提取 ``(ts_ms, value)`` 序列，过滤空值。

    天天基金该字段为 ``[[ts, value], ...]`` 二元组列表。
    """
    if not isinstance(raw, list):
        return []
    series: List[NavPoint] = []
    for point in raw:
        if isinstance(point, (list, tuple)) and len(point) >= 2 and point[1] is not None:
            try:
                series.append((int(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    return series


def year_return(nav: Iterable[NavPoint]) -> Optional[float]:
    """今年以来收益（%）。"""
    series = [p for p in nav if p]
    if not series:
        return None
    last_dt = datetime.fromtimestamp(series[-1][0] / 1000, tz=timezone.utc)
    year_start_ms = int(
        datetime(last_dt.year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
    )
    base = next((v for ts, v in series if ts >= year_start_ms), None)
    if not base or base == 0:
        return None
    return round((series[-1][1] / base - 1) * 100, 2)


def window_return(nav: Iterable[NavPoint], days: int) -> Optional[float]:
    """近 N 天收益（%）。"""
    series = [p for p in nav if p]
    if len(series) < 2:
        return None
    threshold = series[-1][0] - days * 86_400_000
    base = next((v for ts, v in series if ts >= threshold), None)
    if not base or base == 0:
        return None
    return round((series[-1][1] / base - 1) * 100, 2)


def since_inception_return(nav: Iterable[NavPoint]) -> Optional[float]:
    """成立以来收益（%）。"""
    series = [p for p in nav if p]
    if len(series) < 2 or series[0][1] == 0:
        return None
    return round((series[-1][1] / series[0][1] - 1) * 100, 2)


def max_drawdown(nav: Iterable[NavPoint]) -> Optional[float]:
    """成立以来最大回撤（%）。"""
    values = [v for _, v in nav if v is not None]
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return round(worst * 100, 2)


def fmt_ts(ts_ms: int) -> str:
    """毫秒时间戳 -> ``YYYY-MM-DD``（UTC）。"""
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""
