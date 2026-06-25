#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度投研数据源可行性探测脚本（方案 Phase 0）。

真实调用 MX Data / iFinD，验证方案硬前提：
1. MX_APIKEY 可用 + 9 锚点 query 返回结构（字段名/nameMap）
2. MX 数据实时性（snapshot 最新价 vs realtime_quote）
3. iFinD MCP 工具列表（需配置 endpoint+token）
4. MX 对科创板/北交所代码的解析
5. MX/iFinD 主力净流入口径差异量级

用法（需在 .env 配置真实 key）::

    python scripts/probe_data_sources.py

输出 JSON 报告到 stdout，并写 ``reports/deep_research/_probe_<ts>.json``。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROBE_STOCKS = ["600519", "300750", "688981"]  # 主板/创业板/科创板
PROBE_ANCHORS = {
    "snapshot": ["最新价", "总市值", "流通市值", "市盈率", "市净率"],
    "financials": ["营业收入", "归属于母公司净利润", "净资产收益率"],
    "capital": ["主力净流入额", "融资余额"],
}


def probe_mx() -> dict:
    """探测 MX Data：连通、query 结构、实时性。"""
    from data_provider.mx_data_adapter import MXClient

    client = MXClient()
    report = {"available": client.available, "stocks": {}}
    if not client.available:
        report["error"] = "MX_APIKEY not set"
        return report

    for code in PROBE_STOCKS:
        stock_report = {"snapshot": {}, "financials": {}, "capital": {}}
        try:
            stock_report["snapshot"] = client.fetch_snapshot(code)
        except Exception as exc:  # noqa: BLE001
            stock_report["snapshot_error"] = str(exc)
        try:
            stock_report["financials"] = client.query_financials(code, "2024年报")
        except Exception as exc:  # noqa: BLE001
            stock_report["financials_error"] = str(exc)
        try:
            stock_report["capital"] = client.query_capital(code)
        except Exception as exc:  # noqa: BLE001
            stock_report["capital_error"] = str(exc)
        report["stocks"][code] = stock_report
    return report


def probe_ifind() -> dict:
    """探测 iFinD MCP：连通 + 工具列表（需 endpoint+token）。"""
    report = {
        "available": bool(os.getenv("IFIND_MCP_ENDPOINT") and os.getenv("IFIND_MCP_TOKEN")),
        "endpoint": os.getenv("IFIND_MCP_ENDPOINT", ""),
    }
    if not report["available"]:
        report["error"] = "IFIND_MCP_ENDPOINT/IFIND_MCP_TOKEN not set"
        return report
    try:  # pragma: no cover — 真实 MCP 探测
        import asyncio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def _probe():
            headers = {"Authorization": os.getenv("IFIND_MCP_TOKEN", "")}
            async with streamablehttp_client(
                report["endpoint"], headers=headers, timeout=10
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [t.name for t in tools.tools]
        report["tools"] = asyncio.run(_probe())
    except Exception as exc:  # pragma: no cover  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
    return report


def main() -> int:
    # 加载项目根 .env（独立脚本默认不读 dotenv，与 config.py 同路径约定）
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

    print("=" * 60)
    print("深度投研数据源可行性探测（Phase 0）")
    print("=" * 60)

    report = {"mx_data": probe_mx(), "ifind": probe_ifind()}

    out_path = Path("reports/deep_research/_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n--- MX Data ---")
    print(json.dumps(report["mx_data"], ensure_ascii=False, indent=2)[:2000])
    print("\n--- iFinD ---")
    print(json.dumps(report["ifind"], ensure_ascii=False, indent=2))
    print(f"\n报告已写入: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
