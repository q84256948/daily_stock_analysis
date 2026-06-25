# -*- coding: utf-8 -*-
"""capital_flow_provider 单测 —— 纯逻辑 100% 覆盖（网络层 # pragma: no cover）。

覆盖：
- ``compute_cumulative``（纯函数）：n 窗口求和、不足 n 求全和、空/None→None、负值累加。
- ``get_main_inflow_cumulative``（编排）：注入假 ``IfindFetcher`` 验证 today/5d/10d/daily_series；
  iFinD 不可用 / 空序列 → ``{}``（fail-open）。真实 MCP 调用 ``# pragma: no cover``。
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.capital_flow_provider import (  # noqa: E402
    _WINDOW_10D,
    _WINDOW_5D,
    compute_cumulative,
    get_main_inflow_cumulative,
)


def _series(*pairs):
    """构造「最新在前」序列：pairs = [(date_str, value), ...]。"""
    return [(d, v) for d, v in pairs]


class TestComputeCumulative(unittest.TestCase):
    def test_n5_sums_first_five(self):
        # 1,2,3,4,5,6,7 → 前 5 求和 = 15
        s = _series(("d1", 1), ("d2", 2), ("d3", 3), ("d4", 4), ("d5", 5), ("d6", 6), ("d7", 7))
        self.assertEqual(compute_cumulative(s, 5), 15.0)

    def test_fewer_than_n_sums_all(self):
        # 序列不足 n 个 → 全求和（诚实：有多少算多少）
        s = _series(("d1", 2), ("d2", -1), ("d3", 3))
        self.assertEqual(compute_cumulative(s, 5), 4.0)

    def test_negative_accumulates(self):
        # 负值正确累加
        s = _series(("d1", -2e8), ("d2", -1.5e8))
        self.assertAlmostEqual(compute_cumulative(s, 5), -3.5e8)

    def test_empty_or_none_returns_none(self):
        self.assertIsNone(compute_cumulative([], 5))
        self.assertIsNone(compute_cumulative(None, 5))

    def test_window_constants(self):
        # 窗口常量对齐 get_capital_flow 的 inflow_5d / inflow_10d
        self.assertEqual((_WINDOW_5D, _WINDOW_10D), (5, 10))


class _FakeFetcher:
    """IfindFetcher 替身：available + 可编排的 fetch_main_inflow_series 返回值。"""

    def __init__(self, available=True, series=None, raises=False):
        self.available = available
        self._series = series
        self._raises = raises

    def fetch_main_inflow_series(self, code, days=12):
        if self._raises:
            raise RuntimeError("boom")
        return self._series


class TestGetMainInflowCumulative(unittest.TestCase):
    """get_main_inflow_cumulative：编排 iFinD 序列 → today/5d/10d（fail-open）。"""

    def test_full_payload(self):
        # 12 日序列（最新在前），main_net_inflow=最新日，5d=前5求和，10d=前10求和
        s = _series(*[(f"d{i}", float(i)) for i in range(1, 13)])  # 1..12
        fake = _FakeFetcher(available=True, series=s)
        with patch(
            "data_provider.ifind_fundamental_adapter.IfindFetcher.get_instance",
            return_value=fake,
        ):
            out = get_main_inflow_cumulative("688486")
        self.assertEqual(out["source"], "ifind")
        self.assertEqual(out["main_net_inflow"], 1.0)  # series[0][1] = d1 → 1
        self.assertEqual(out["inflow_5d"], 15.0)       # 1+2+3+4+5
        self.assertEqual(out["inflow_10d"], 55.0)      # 1..10
        self.assertEqual(len(out["daily_series"]), 12)
        self.assertEqual(out["daily_series"][0], {"date": "d1", "value": 1.0})

    def test_short_series_sums_all(self):
        # 序列只有 3 行：5d/10d 都退化为全求和
        s = _series(("d1", 10), ("d2", 20), ("d3", 30))
        fake = _FakeFetcher(available=True, series=s)
        with patch(
            "data_provider.ifind_fundamental_adapter.IfindFetcher.get_instance",
            return_value=fake,
        ):
            out = get_main_inflow_cumulative("688486")
        self.assertEqual(out["main_net_inflow"], 10)
        self.assertEqual(out["inflow_5d"], 60)  # 不足5 → 全求和
        self.assertEqual(out["inflow_10d"], 60)

    def test_unavailable_returns_empty(self):
        fake = _FakeFetcher(available=False)
        with patch(
            "data_provider.ifind_fundamental_adapter.IfindFetcher.get_instance",
            return_value=fake,
        ):
            self.assertEqual(get_main_inflow_cumulative("688486"), {})

    def test_empty_series_returns_empty(self):
        fake = _FakeFetcher(available=True, series=[])
        with patch(
            "data_provider.ifind_fundamental_adapter.IfindFetcher.get_instance",
            return_value=fake,
        ):
            self.assertEqual(get_main_inflow_cumulative("688486"), {})

    def test_fetch_raises_returns_empty(self):
        # 抓取异常被 IfindFetcher 内部吞掉返回 None → {}
        fake = _FakeFetcher(available=True, series=None)  # None 视为空序列
        with patch(
            "data_provider.ifind_fundamental_adapter.IfindFetcher.get_instance",
            return_value=fake,
        ):
            self.assertEqual(get_main_inflow_cumulative("688486"), {})


if __name__ == "__main__":
    unittest.main()
