# -*- coding: utf-8 -*-
"""郑希基金数据加载与摘要提取。

读取 ``data/fund_manager_views/zhengxi/fund_data/`` 下的静态快照，
返回**精炼摘要**（剔除逐日净值序列——单只基金净值点可达 2000+），
供 Agent 工具返回给 LLM。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, List, Optional

from src.services.zhengxi import scoring
from src.services.zhengxi.paths import fund_data_dir


def _index() -> dict[str, Any]:
    path = os.path.join(fund_data_dir(), "_index.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_funds() -> List[dict[str, Any]]:
    """返回 ``_index.json`` 的基金清单（代码/名称/角色/区间/类型/季度数）。"""
    return _index().get("funds", [])


def _fund_dir(code: str) -> Optional[str]:
    for match in glob.glob(os.path.join(fund_data_dir(), f"{code}_*")):
        if os.path.isdir(match):
            return match
    return None


def resolve_fund(code_or_name: str) -> Optional[dict[str, Any]]:
    """代码或名称 → 基金元信息。

    代码精确匹配；名称模糊匹配，多命中时取最短名（通常是主代码）。
    """
    query = code_or_name.strip()
    funds = list_funds()
    if query.isdigit():
        for fund in funds:
            if fund["code"] == query:
                return fund
        return None
    candidates = [fund for fund in funds if query in fund["name"]]
    if not candidates:
        return None
    candidates.sort(key=lambda fund: len(fund["name"]))
    return candidates[0]


def load_holdings(code: str) -> List[dict[str, Any]]:
    """加载季度持仓（完整历史，按 年+季 升序）。"""
    fund_dir = _fund_dir(code)
    if not fund_dir:
        return []
    path = os.path.join(fund_dir, "季度持仓.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        quarters = json.load(fh)
    quarters.sort(key=lambda q: (q.get("year", 0), q.get("quarter", 0)))
    return quarters


def latest_holdings(code: str) -> Optional[dict[str, Any]]:
    """最新一季前十大重仓 + 集中度 + 换手代理。"""
    quarters = load_holdings(code)
    if not quarters:
        return None
    latest = quarters[-1]
    holdings = latest.get("holdings", [])
    return {
        "year": latest.get("year"),
        "quarter": latest.get("quarter"),
        "title": latest.get("title", ""),
        "top10": [
            {
                "name": h.get("股票名称"),
                "code": h.get("股票代码"),
                "weight_pct": h.get("占净值比"),
            }
            for h in holdings
        ],
        "concentration_top10_pct": scoring.concentration(holdings),
        "turnover_proxy_pct": scoring.turnover_proxy(quarters),
        "quarters_count": len(quarters),
    }


def load_performance_summary(code: str) -> dict[str, Any]:
    """净值业绩规模摘要（精炼，剔除逐日净值序列）。

    覆盖：区间收益（今年/近1年/近3年/成立以来）、最大回撤、规模、
    资产配置、天天基金五维评价、郑希任职回报。
    """
    fund_dir = _fund_dir(code)
    if not fund_dir:
        return {"error": f"无基金数据: {code}"}
    path = os.path.join(fund_dir, "净值业绩规模.json")
    if not os.path.exists(path):
        return {"error": f"缺净值业绩文件: {code}"}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    nav = scoring.nav_series(raw.get("累计净值走势"))
    summary: dict[str, Any] = {
        "fund_name": raw.get("fS_name"),
        "fund_code": raw.get("fS_code"),
        "fee_rate": raw.get("费率"),
        "min_buy": raw.get("起购"),
        "data_cutoff_note": "静态快照，非实时数据",
    }
    if nav:
        summary.update({
            "return_ytd_pct": scoring.year_return(nav),
            "return_1y_pct": scoring.window_return(nav, 365),
            "return_3y_pct": scoring.window_return(nav, 365 * 3),
            "return_since_inception_pct": scoring.since_inception_return(nav),
            "max_drawdown_pct": scoring.max_drawdown(nav),
            "nav_period_start": scoring.fmt_ts(nav[0][0]),
            "nav_period_end": scoring.fmt_ts(nav[-1][0]),
        })

    # 区间收益对比（天天基金：本基金 vs 同类 vs 沪深300 等）
    benchmark = raw.get("累计收益率走势") or []
    if isinstance(benchmark, list) and benchmark and isinstance(benchmark[0], dict):
        ranges = []
        for series in benchmark:
            data = series.get("data") if isinstance(series, dict) else None
            if not data:
                continue
            last = data[-1]
            ranges.append({
                "name": series.get("name"),
                "latest_pct": last[1] if isinstance(last, (list, tuple)) and len(last) >= 2 else None,
            })
        if ranges:
            summary["benchmark_ranges"] = ranges

    # 规模变动
    scale = raw.get("规模变动") or {}
    if isinstance(scale, dict) and scale.get("series") and scale.get("categories"):
        summary["scale_latest"] = {
            "value_yi": scale["series"][-1].get("y"),
            "period": scale["categories"][-1],
        }

    # 资产配置（最新一期）
    alloc = raw.get("资产配置") or {}
    if isinstance(alloc, dict) and alloc.get("series") and alloc.get("categories"):
        summary["asset_allocation_period"] = alloc["categories"][-1]
        summary["asset_allocation"] = [
            {"name": s.get("name"), "pct": (s.get("data") or [None])[-1]}
            for s in alloc["series"]
            if isinstance(s, dict)
        ]

    # 天天基金五维业绩评价（满分 100）
    evaluation = raw.get("业绩评价") or {}
    if isinstance(evaluation, dict) and isinstance(evaluation.get("data"), list):
        summary["eastmoney_evaluation"] = {
            cat: val
            for cat, val in zip(evaluation.get("categories", []), evaluation["data"])
        }

    # 郑希任职回报
    managers = raw.get("基金经理") or []
    if isinstance(managers, list):
        for manager in managers:
            if not (isinstance(manager, dict) and manager.get("name") == "郑希"):
                continue
            profit = manager.get("profit") or {}
            series_list = profit.get("series") or []
            data = series_list[0].get("data") if series_list else None
            if profit.get("categories") and data:
                summary["zhengxi_tenure_return"] = {
                    cat: (x.get("y") if isinstance(x, dict) else x)
                    for cat, x in zip(profit["categories"], data)
                }
            break

    return summary
