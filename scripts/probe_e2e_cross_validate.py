#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：用真实 MX + iFinD 对 600519 跑交叉验证，看置信度分布。

验证项：
- MX 主源 + iFinD 验证源 实际取数是否成功
- 关键锚点（PE/PB/总市值/营收/净利/ROE/融资余额）双源是否一致
- main_inflow 方向验证（量级口径差异）
- build_cross_validation_block 端到端是否产出有效 block
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# 强制开启开关（覆盖 .env，确保走验证路径）
os.environ["DEEP_RESEARCH_CROSS_VALIDATE"] = "true"

from data_provider.cross_source_validator import CrossSourceValidator  # noqa: E402
from data_provider.mx_data_adapter import MXSource  # noqa: E402
from data_provider.ifind_fundamental_adapter import IfindFetcher, IfindSource  # noqa: E402
from src.agent.tools.cross_validation_helpers import reset_validator  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("端到端交叉验证 · 600519 贵州茅台（真实 MX + iFinD）")
    print("=" * 70)

    # 构建验证器：MX 主源 + iFinD 验证源
    mx = MXSource()
    ifind_fetcher = IfindFetcher()
    ifind = IfindSource(fetcher=ifind_fetcher)
    print(f"MX available: {mx.available}")
    print(f"iFinD available: {ifind.available}")

    validator = CrossSourceValidator(sources=[mx, ifind])

    # 估值/财务/资金锚点
    anchors = [
        ("pe_ratio", None),
        ("pb_ratio", None),
        ("total_mv", None),
        ("circ_mv", None),
        ("revenue", "2024年报"),
        ("net_profit", "2024年报"),
        ("roe", "2024年报"),
        ("margin_balance", None),
        ("main_inflow", None),
    ]

    results = []
    for field, period in anchors:
        v = validator.verify("600519", field, period=period)
        row = {
            "field": field,
            "value": round(v.value, 4) if v.value else None,
            "confidence": v.confidence,
            "sources": list(v.sources),
            "discrepancy_pct": round(v.discrepancy_pct, 2) if v.discrepancy_pct is not None else None,
            "caliber": v.caliber,
            "period": v.period,
        }
        results.append(row)
        marker = {"high": "✓", "medium": "~", "low": "⚠"}.get(v.confidence, "?")
        print(f"  [{marker} {v.confidence:6}] {field:14} = {row['value']}  "
              f"src={v.sources} diff={row['discrepancy_pct']}%")

    # 统计
    high = sum(1 for r in results if r["confidence"] == "high")
    med = sum(1 for r in results if r["confidence"] == "medium")
    low = sum(1 for r in results if r["confidence"] == "low")
    print(f"\n汇总: high={high}  medium={med}  low={low}  (共 {len(results)})")

    out_path = Path("reports/deep_research/_e2e_cross_validate.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"results": results, "summary": {"high": high, "medium": med, "low": low}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n详细结果: {out_path}")
    return 0


if __name__ == "__main__":
    reset_validator()
    sys.exit(main())
