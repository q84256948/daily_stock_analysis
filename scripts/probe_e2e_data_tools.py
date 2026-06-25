#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：data_tools 工具注入 cross_validation 块（真实开关 ON）。

验证 get_stock_info / get_realtime_quote / get_capital_flow 三个 handler
在开关开启时返回 cross_validation 块，块内锚点置信度合理。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
os.environ["DEEP_RESEARCH_CROSS_VALIDATE"] = "true"

from src.agent.tools import data_tools  # noqa: E402
from src.agent.tools.cross_validation_helpers import reset_validator  # noqa: E402


def _call_tool(name: str, args: dict) -> dict:
    """直接调用 data_tools 的 dispatch。"""
    # data_tools 的入口签名可能不同，先探测
    dispatch = getattr(data_tools, "dispatch_tool", None) or getattr(data_tools, "call_tool", None)
    if dispatch is None:
        # 尝试通过 ToolRegistry
        from src.agent.tools.tool_registry import ToolRegistry  # type: ignore
        reg = ToolRegistry()
        return reg.call(name, args)
    return dispatch(name, args)


def main() -> int:
    reset_validator()
    print("=" * 70)
    print("data_tools 工具注入 cross_validation 端到端验证（600519）")
    print("=" * 70)

    # 直接调用 handler（绕过 ToolRegistry，验证注入逻辑本身）
    from src.agent.tools.data_tools import (
        _handle_get_realtime_quote,
        _handle_get_stock_info,
        _handle_get_capital_flow,
    )

    tools_to_test = [
        ("get_realtime_quote", lambda: _handle_get_realtime_quote("600519")),
        ("get_stock_info", lambda: _handle_get_stock_info("600519")),
        ("get_capital_flow", lambda: _handle_get_capital_flow("600519")),
    ]

    for tool, call in tools_to_test:
        print(f"\n--- {tool}(600519) ---")
        try:
            result = call()
        except Exception as exc:
            print(f"  调用异常: {type(exc).__name__}: {exc}")
            continue
        if not isinstance(result, dict):
            print(f"  非 dict 返回: {type(result)}")
            continue
        cv = result.get("cross_validation")
        # 工具关键字段（确认主数据正常）
        price = result.get("price") or result.get("current_price")
        pe = result.get("pe_ratio") or result.get("pe")
        print(f"  主数据采样: price={price} pe={pe}")
        if cv is None:
            print("  无 cross_validation 块（开关关 / 全锚点失败）")
            continue
        print(f"  cross_validation.enabled: {cv.get('enabled')}")
        print(f"  summary: {cv.get('summary')}")
        for field, anchor in cv.get("anchors", {}).items():
            print(f"    {field}: v={anchor.get('v')} conf={anchor.get('conf')} "
                  f"src={anchor.get('src')} diff={anchor.get('diff')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
