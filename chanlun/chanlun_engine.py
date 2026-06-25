# -*- coding: utf-8 -*-
"""缠论分析引擎 v1.0 (自实现，参考 openclaw-chanlun-skill 算法)

核心逻辑与 skill 一致：
- 分型识别：三根K线极值结构
- 笔构建：分型间连接单元
- 中枢识别：三段重叠区间
- 背驰检测：MACD 背离
- 买卖点提取
- 评分计算

不依赖 PyChanLun 库，兼容 Python 3.10+
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


DEFAULT_PARAMS = {
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "fractal": {"strictness": 1.0},
    "stroke": {"min_bars": 5, "merge_threshold": 0.0},
    "beichi": {"pz_area_ratio": 0.6, "macd_divergence_threshold": 0.05},
    "mm_score_weights": {
        "1buy": 30,
        "2buy": 25,
        "3buy": 20,
        "l2buy": 15,
        "1sell": 25,
        "2sell": 20,
        "3sell": 15,
        "qs_beichi": 20,
        "pz_beichi": 10,
    },
    "signal_strength": {"strong_threshold": 0.4, "medium_threshold": 0.15},
}


def load_params(params_path: str | None = None) -> dict:
    """从 params.json 加载参数。"""
    if params_path is None:
        params_path = Path(__file__).parent / "params.json"
    try:
        with open(params_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        loaded = data.get("params", {})
        return _deep_merge(dict(DEFAULT_PARAMS), loaded)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_PARAMS)


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典。"""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class ChanLunEngine:
    """自实现缠论分析引擎。

    与 skill 算法一致，输出标准化结构：
    - fractals: 分型列表
    - strokes: 笔列表（含背驰）
    - zhongshus: 中枢列表
    - signals: 买卖点列表
    - summary: 分析摘要
    """

    def __init__(self, df: pd.DataFrame, params: dict | None = None):
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required}")

        self.df = df.sort_index().copy().reset_index(drop=True)
        self.p = params or DEFAULT_PARAMS

        self._calculate_indicators()
        self.fractals: List[Dict] = []
        self.strokes: List[Dict] = []
        self.zhongshus: List[Dict] = []
        self.pivots: List[Dict] = []

    def _calculate_indicators(self) -> None:
        """计算 MACD 等指标。"""
        if len(self.df) == 0:
            self.df["ema_fast"] = []
            self.df["ema_slow"] = []
            self.df["macd_dif"] = []
            self.df["macd_dea"] = []
            self.df["macd"] = []
            return

        cfg = self.p.get("macd", DEFAULT_PARAMS["macd"])
        fast = cfg.get("fast", 12)
        slow = cfg.get("slow", 26)
        signal = cfg.get("signal", 9)

        close = self.df["close"].values
        self.df["ema_fast"] = self._ema(close, fast)
        self.df["ema_slow"] = self._ema(close, slow)
        self.df["macd_dif"] = self.df["ema_fast"] - self.df["ema_slow"]
        self.df["macd_dea"] = self._ema(self.df["macd_dif"].values, signal)
        self.df["macd"] = 2 * (self.df["macd_dif"] - self.df["macd_dea"])

    @staticmethod
    def _ema(data: np.ndarray, n: int) -> np.ndarray:
        """计算指数移动平均。"""
        ema = np.empty_like(data, dtype=float)
        ema[0] = data[0]
        k = 2.0 / (n + 1)
        for i in range(1, len(data)):
            ema[i] = data[i] * k + ema[i - 1] * (1 - k)
        return ema

    def analyze(self) -> Dict[str, Any]:
        """执行完整缠论分析。"""
        self.fractals = self._find_fractals()
        self.pivots = self._find_pivots()
        self.strokes = self._build_strokes()
        self.zhongshus = self._find_zhongshus()
        signals = self._extract_signals()
        trend = self._determine_trend()
        summary = self._compute_summary()

        current_price = float(self.df["close"].iloc[-1]) if len(self.df) > 0 else 0.0
        last_stroke = self.strokes[-1] if self.strokes else None
        last_zs = self.zhongshus[-1] if self.zhongshus else None

        position = "中枢震荡"
        if last_zs:
            if current_price > last_zs["zg"]:
                position = "突破中枢"
            elif current_price < last_zs["zd"]:
                position = "跌破中枢"
        elif last_stroke:
            position = f"笔未完成({last_stroke['type']})"

        divergence = None
        if last_stroke:
            if last_stroke.get("qs_beichi"):
                div_type = "底" if last_stroke["type"] == "down" else "顶"
                divergence = f"趋势背驰({div_type})"
            elif last_stroke.get("pz_beichi"):
                div_type = "底" if last_stroke["type"] == "down" else "顶"
                divergence = f"盘整背驰({div_type})"

        return {
            "status": "OK",
            "klines_count": len(self.df),
            "cl_klines_count": len(self.df),
            "fractals": self.fractals,
            "strokes": self.strokes,
            "zhongshus": self.zhongshus,
            "signals": signals,
            "raw_signals": signals,
            "current_trend": trend,
            "position": position,
            "divergence": divergence,
            "current_price": current_price,
            "last_bi": self._format_last_bi(last_stroke) if last_stroke else None,
            "last_zs": self._format_last_zs(last_zs) if last_zs else None,
            "summary": summary,
        }

    def _find_fractals(self) -> List[Dict]:
        """识别顶分型和底分型。"""
        strictness = self.p.get("fractal", {}).get("strictness", 1.0)
        n = len(self.df)
        fractals = []

        for i in range(1, n - 1):
            high_prev = float(self.df["high"].iloc[i - 1])
            high_curr = float(self.df["high"].iloc[i])
            high_next = float(self.df["high"].iloc[i + 1])
            low_prev = float(self.df["low"].iloc[i - 1])
            low_curr = float(self.df["low"].iloc[i])
            low_next = float(self.df["low"].iloc[i + 1])

            is_top = (
                high_curr >= high_prev * strictness
                and high_curr >= high_next * strictness
            )
            is_bottom = (
                low_curr <= low_prev / strictness and low_curr <= low_next / strictness
            )

            if is_top:
                fractals.append(
                    {
                        "type": "ding",
                        "date": str(self.df["date"].iloc[i].date()),
                        "val": round(high_curr, 4),
                        "real": True,
                        "index": i,
                    }
                )
            if is_bottom:
                fractals.append(
                    {
                        "type": "di",
                        "date": str(self.df["date"].iloc[i].date()),
                        "val": round(low_curr, 4),
                        "real": True,
                        "index": i,
                    }
                )

        return fractals

    def _find_pivots(self) -> List[Dict]:
        """识别极值点（笔的端点）。"""
        if not self.fractals:
            return []

        pivots = []
        for f in self.fractals:
            idx = f["index"]
            pivots.append(
                {
                    "date": f["date"],
                    "index": idx,
                    "price": f["val"],
                    "type": f["type"],
                    "macd": float(self.df["macd"].iloc[idx]),
                }
            )

        return pivots

    def _build_strokes(self) -> List[Dict]:
        """构建笔序列，检测背驰。"""
        if len(self.pivots) < 2:
            return []

        strokes = []
        stroke_macd_list = []
        prev_idx = None
        prev_price = None
        prev_type = None

        for i, pivot in enumerate(self.pivots):
            if prev_idx is None:
                prev_idx = pivot["index"]
                prev_price = pivot["price"]
                prev_type = pivot["type"]
                continue

            if pivot["type"] != prev_type:
                min_bars = self.p.get("stroke", {}).get("min_bars", 5)
                bar_count = pivot["index"] - prev_idx

                if bar_count >= min_bars:
                    is_up = pivot["type"] == "ding"
                    high = max(prev_price, pivot["price"])
                    low = min(prev_price, pivot["price"])

                    macd_sum = self._calc_macd_sum(prev_idx, pivot["index"])

                    qs_beichi = self._check_trend_beichi(
                        strokes, is_up, pivot, stroke_macd_list
                    )
                    pz_beichi = self._check_sideways_beichi(
                        strokes, is_up, macd_sum, stroke_macd_list
                    )

                    mmds = self._detect_buy_sell_points(pivot, strokes)
                    mm_score = self._calc_mm_score(mmds, qs_beichi, pz_beichi)

                    strokes.append(
                        {
                            "index": len(strokes),
                            "type": "up" if is_up else "down",
                            "start_date": self.pivots[i - 1]["date"],
                            "end_date": pivot["date"],
                            "start_index": prev_idx,
                            "end_index": pivot["index"],
                            "high": round(high, 4),
                            "low": round(low, 4),
                            "done": True,
                            "td": False,
                            "qs_beichi": qs_beichi,
                            "pz_beichi": pz_beichi,
                            "mmds": mmds,
                            "mm_score": mm_score,
                        }
                    )
                    stroke_macd_list.append(
                        {"type": "up" if is_up else "down", "macd": macd_sum}
                    )

                prev_idx = pivot["index"]
                prev_price = pivot["price"]
                prev_type = pivot["type"]

        return strokes

    def _calc_macd_sum(self, start_idx: int, end_idx: int) -> float:
        """计算区间内 MACD 柱之和。"""
        return float(self.df["macd"].iloc[start_idx : end_idx + 1].sum())

    def _check_trend_beichi(
        self,
        strokes: List[Dict],
        is_up: bool,
        current_pivot: Dict,
        macd_list: List[Dict],
    ) -> bool:
        """检测趋势背驰。"""
        if len(strokes) < 1 or len(macd_list) < 1:
            return False

        last_stroke = strokes[-1]
        last_macd = macd_list[-1]["macd"]

        if is_up and last_stroke["type"] == "down":
            prev_high_idx = last_stroke["end_index"]
            prev_high = float(self.df["high"].iloc[prev_high_idx])
            curr_high = current_pivot["price"]
            if curr_high > prev_high and last_macd > 0:
                current_macd = current_pivot["macd"]
                if current_macd < last_macd * 0.8:
                    return True
        elif not is_up and last_stroke["type"] == "up":
            prev_low_idx = last_stroke["end_index"]
            prev_low = float(self.df["low"].iloc[prev_low_idx])
            curr_low = current_pivot["price"]
            if curr_low < prev_low and last_macd < 0:
                current_macd = current_pivot["macd"]
                if current_macd > last_macd * 0.8:
                    return True

        return False

    def _check_sideways_beichi(
        self,
        strokes: List[Dict],
        is_up: bool,
        current_macd: float,
        macd_list: List[Dict],
    ) -> bool:
        """检测盘整背驰。"""
        if len(strokes) < 1 or len(macd_list) < 1:
            return False

        ratio = self.p.get("beichi", {}).get("pz_area_ratio", 0.6)
        same_type_strokes = [
            m for m in macd_list if m["type"] == ("up" if is_up else "down")
        ]

        if same_type_strokes:
            prev_macd = same_type_strokes[-1]["macd"]
            if prev_macd != 0:
                if abs(current_macd) < abs(prev_macd) * (1 - ratio):
                    return True

        return False

    def _detect_buy_sell_points(self, pivot: Dict, strokes: List[Dict]) -> List[str]:
        """检测买卖点。"""
        mmds = []

        if len(strokes) >= 2:
            last = strokes[-1]
            prev = strokes[-2]

            if pivot["type"] == "di":
                if last["type"] == "down" and prev["type"] == "up":
                    mmds.append("1buy")
                elif last["type"] == "up" and prev["type"] == "down":
                    prev_low_idx = prev["start_index"]
                    curr_low = pivot["price"]
                    prev_low = float(self.df["low"].iloc[prev_low_idx])
                    if curr_low > prev_low:
                        mmds.append("2buy")
            elif pivot["type"] == "ding":
                if last["type"] == "up" and prev["type"] == "down":
                    mmds.append("1sell")
                elif last["type"] == "down" and prev["type"] == "up":
                    prev_high_idx = prev["start_index"]
                    curr_high = pivot["price"]
                    prev_high = float(self.df["high"].iloc[prev_high_idx])
                    if curr_high < prev_high:
                        mmds.append("2sell")

        return mmds

    def _calc_mm_score(
        self,
        mmds: List[str],
        qs_beichi: bool,
        pz_beichi: bool,
    ) -> float:
        """计算买卖点综合评分。"""
        weights = self.p.get("mm_score_weights", DEFAULT_PARAMS["mm_score_weights"])
        score = 0.0
        for m in mmds:
            score += weights.get(m, 0)
        if qs_beichi:
            score += weights.get("qs_beichi", 20)
        if pz_beichi:
            score += weights.get("pz_beichi", 10)
        return max(0.0, min(100.0, score))

    def _find_zhongshus(self) -> List[Dict]:
        """识别中枢。"""
        if len(self.strokes) < 5:
            return []

        zhongshus = []
        used = set()

        for i in range(len(self.strokes) - 2):
            s1 = self.strokes[i]
            s2 = self.strokes[i + 1]
            s3 = self.strokes[i + 2]

            if s1["type"] == s2["type"] or s2["type"] != s3["type"]:
                continue

            h1, l1 = s1["high"], s1["low"]
            h2, l2 = s2["high"], s2["low"]
            h3, l3 = s3["high"], s3["low"]

            overlap_12_h = min(h1, h2)
            overlap_12_l = max(l1, l2)
            if overlap_12_h <= overlap_12_l:
                continue

            overlap_23_h = min(h2, h3)
            overlap_23_l = max(l2, l3)
            if overlap_23_h <= overlap_23_l:
                continue

            zg = min(overlap_12_h, overlap_23_h)
            zd = max(overlap_12_l, overlap_23_l)
            if zg <= zd:
                continue

            gg = max(h1, h2, h3)
            dd = min(l1, l2, l3)

            key = (round(zg, 2), round(zd, 2))
            if key in used:
                continue
            used.add(key)

            zhongshus.append(
                {
                    "index": len(zhongshus),
                    "zg": round(zg, 4),
                    "zd": round(zd, 4),
                    "gg": round(gg, 4),
                    "dd": round(dd, 4),
                    "stroke_indices": [i, i + 1, i + 2],
                }
            )

        return zhongshus

    def _extract_signals(self) -> List[Dict]:
        """提取买卖点信号。"""
        signals = []
        for stroke in self.strokes:
            for mmd in stroke["mmds"]:
                if "buy" in mmd:
                    signals.append(
                        {
                            "date": stroke["end_date"],
                            "type": mmd,
                            "price": stroke["low"],
                            "stroke_index": stroke["index"],
                        }
                    )
                elif "sell" in mmd:
                    signals.append(
                        {
                            "date": stroke["end_date"],
                            "type": mmd,
                            "price": stroke["high"],
                            "stroke_index": stroke["index"],
                        }
                    )
        return signals

    def _determine_trend(self) -> str:
        """判断当前趋势。"""
        if len(self.strokes) < 3:
            return "盘整"
        last = self.strokes[-1]["type"]
        prev = self.strokes[-2]["type"]
        if last == "up" and prev == "down":
            return "上涨"
        elif last == "down" and prev == "up":
            return "下跌"
        return "盘整"

    def _compute_summary(self) -> Dict[str, Any]:
        """计算分析摘要。"""
        buy_count = sum(
            1
            for s in self.strokes
            if any(m in s["mmds"] for m in ["1buy", "2buy", "3buy", "l2buy"])
        )
        sell_count = sum(
            1
            for s in self.strokes
            if any(m in s["mmds"] for m in ["1sell", "2sell", "3sell"])
        )
        div_count = sum(
            1 for s in self.strokes if s.get("qs_beichi") or s.get("pz_beichi")
        )
        active = buy_count + sell_count + div_count
        total = len(self.strokes)

        cfg = self.p.get("signal_strength", DEFAULT_PARAMS["signal_strength"])
        strong_th = cfg.get("strong_threshold", 0.4)
        medium_th = cfg.get("medium_threshold", 0.15)

        if total == 0:
            strength = "weak"
        elif active / total > strong_th:
            strength = "strong"
        elif active / total > medium_th:
            strength = "medium"
        else:
            strength = "weak"

        return {
            "divergence_count": div_count,
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "signal_strength": strength,
            "signals_list": self._extract_signals(),
        }

    def _format_last_bi(self, stroke: Optional[Dict]) -> Optional[Dict]:
        """格式化最后一笔信息。"""
        if not stroke:
            return None
        return {
            "type": stroke["type"],
            "start_date": stroke["start_date"],
            "end_date": stroke["end_date"],
            "high": stroke["high"],
            "low": stroke["low"],
            "qs_beichi": stroke.get("qs_beichi", False),
            "pz_beichi": stroke.get("pz_beichi", False),
            "mmds": stroke.get("mmds", []),
            "mm_score": stroke.get("mm_score", 0.0),
        }

    def _format_last_zs(self, zs: Optional[Dict]) -> Optional[Dict]:
        """格式化最后一个中枢信息。"""
        if not zs:
            return None
        return {
            "zg": zs["zg"],
            "zd": zs["zd"],
            "gg": zs.get("gg"),
            "dd": zs.get("dd"),
        }
