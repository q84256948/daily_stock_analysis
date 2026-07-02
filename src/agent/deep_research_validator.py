# -*- coding: utf-8 -*-
"""深度投研报告 · 质量校验器（三层防线的 L2 检测层）。

对 Agent 产出的 Markdown 报告做结构化质量校验：
1. 五层穿透完整性：每层是否同时满足「关键词内容覆盖」+「必要工具调用覆盖」。
2. 结论前置：每个一级章节首句是否为结论句。
3. 三情景概率和：是否落在 [95%, 105%] 容差区间。

校验结果驱动 executor 的 L3 兜底（失败→追加提示重生成；再失败→标注降级）。
校验本身是只读的纯函数，不抛异常，不阻塞主流程。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# 每层要求：关键词（内容覆盖，命中其一即可）+ 工具组（每组任一即可，所有组都要满足）。
# 与 system_prompt.md 第二章「强制工具调用检查点」保持一致。
_LAYER_REQUIREMENTS: Dict[str, Dict[str, object]] = {
    "宏观": {
        "keywords": ["市场", "大盘", "指数", "宏观", "流动性", "ERP", "政策", "社融", "PPI"],
        "tool_groups": [{"get_market_indices"}, {"search_comprehensive_intel"}],
    },
    "产业": {
        "keywords": ["产业", "行业", "供应链", "竞争", "壁垒", "市占", "生命周期", "格局"],
        "tool_groups": [{"get_sector_rankings"}, {"search_comprehensive_intel"}],
    },
    "财务": {
        "keywords": ["营收", "利润", "ROE", "毛利率", "现金流", "杜邦", "资产负债", "净利率"],
        "tool_groups": [{"get_stock_info"}],
    },
    "估值": {
        "keywords": ["估值", "PE", "PB", "DCF", "SOTP", "目标价", "安全边际", "情景", "PEG", "EV/EBITDA"],
        "tool_groups": [],  # 估值层无强制工具，靠内容关键词
    },
    "博弈": {
        "keywords": ["筹码", "均线", "K线", "量能", "资金流", "主力", "催化", "股东户数", "融资余额"],
        "tool_groups": [{"analyze_trend", "get_chip_distribution", "get_capital_flow"}],
    },
}

# 一级章节标题（用于结论前置校验）
_REQUIRED_SECTIONS = [
    "投资结论",
    "宏观与政策环境",
    "产业与赛道",
    "公司分析",
    "财务质量",
    "估值与目标价",
    "博弈与节奏",
    "风险提示",
]


@dataclass(frozen=True)
class ValidationResult:
    """质量校验结果（不可变）。"""

    passed: bool
    score: int  # 0-100
    missing_layers: List[str] = field(default_factory=list)
    missing_tool_groups: List[str] = field(default_factory=list)
    missing_sections: List[str] = field(default_factory=list)
    conclusion_count: int = 0
    probability_sum: float = 0.0
    details: List[str] = field(default_factory=list)
    pe_contradictions: List[PeContradiction] = field(default_factory=list)


def _extract_called_tools(tool_calls_log: List[Dict[str, object]]) -> Set[str]:
    """从工具调用日志提取已调用的工具名集合。"""
    called: Set[str] = set()
    for entry in tool_calls_log or []:
        name = entry.get("tool") if isinstance(entry, dict) else None
        if isinstance(name, str) and name:
            called.add(name)
    return called


def _check_layer(
    layer: str,
    requirement: Dict[str, object],
    markdown: str,
    called_tools: Set[str],
) -> Dict[str, object]:
    """检查单层覆盖情况。返回 {content_ok, tools_ok, missing_groups}。"""
    keywords: List[str] = list(requirement.get("keywords") or [])  # type: ignore[arg-type]
    content_ok = any(kw in markdown for kw in keywords)

    tool_groups: List[Any] = list(requirement.get("tool_groups") or [])  # type: ignore[arg-type]
    missing_groups: List[str] = []
    tools_ok = True
    if tool_groups:
        for group in tool_groups:
            if not (group & called_tools):
                tools_ok = False
                missing_groups.append(layer)

    return {
        "content_ok": content_ok,
        "tools_ok": tools_ok,
        "missing_groups": missing_groups,
    }


def _count_conclusions(markdown: str) -> int:
    """统计结论前置标记数量（【结论】）。"""
    return len(re.findall(r"【结论】", markdown))


def _count_validation_markers(markdown: str) -> tuple[Any, ...]:
    """统计双源验证标注：返回 (verified✓, conflict⚠)。

    温和信息性统计，不参与 passed/score 判定（避免 LLM 未严格遵循格式时误判）。
    """
    verified = len(re.findall(r"✓", markdown))
    conflict = len(re.findall(r"⚠", markdown))
    return verified, conflict


def _check_probability_sum(markdown: str) -> float:
    """提取三情景概率并求和。

    匹配情景表/正文中形如「牛市 | 25%」「概率：50%」的数字。
    容错：取前 3 个最可能的概率值求和（牛市/基准/熊市）。
    """
    # 优先匹配「情景 ... XX%」表格行
    table_probs = re.findall(r"(?:牛市|基准|熊市|base|bull|bear)[^\d]{0,20}?(\d{1,3})\s*%", markdown, re.IGNORECASE)
    if len(table_probs) >= 3:
        vals = [int(p) for p in table_probs[:3]]
        return float(sum(vals))
    # 兜底：匹配所有百分号数字，取前 3 个
    all_probs = re.findall(r"(\d{1,3})\s*%", markdown)
    if len(all_probs) >= 3:
        vals = [int(p) for p in all_probs[:3]]
        return float(sum(vals))
    return 0.0


# ---------------------------------------------------------------------------
# PE 估值口径一致性检测
#
# 防止「溢价抬升至 X-Y x PE」但 X-Y 明显低于当前 PE(TTM) 的自相矛盾：报告头部
# 声明的【当前 PE(TTM)】是估值基准锚点，溢价/抬升情景的 PE 区间上限必须 ≥ 当前 PE。
# 本检测是只读、非阻断的 L2 质量信号：仅写入 details + pe_contradictions，不改变
# passed/score（避免误判触发不必要的重生成，影响无关报告）。
# ---------------------------------------------------------------------------

# 当前 PE(TTM) 提取模式（仅识别 TTM 限定口径，避免误抓正文中的情景 PE）。
# 按优先级匹配，命中其一即返回。
_CURRENT_PE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"PE\s*[\(（]\s*TTM\s*[\)）][：:\s]*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"市盈率\s*[\(（]\s*TTM\s*[\)）][：:\s]*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"PE\s+TTM[：:\s]*([0-9]+(?:\.[0-9]+)?)"),
)

# 估值区间提取模式：区间位于 PE 之前，如 '120-130x PE' / '120~130倍PE' / '120至130 PE'。
_PE_BAND_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–—~～至到]\s*(\d+(?:\.\d+)?)\s*[x×倍]*\s*PE")

# 溢价/抬升类表述：此类情景的 PE 区间上限应 ≥ 当前 PE(TTM)，否则为估值口径矛盾。
_PREMIUM_VERBS: tuple[str, ...] = ("溢价", "抬升", "拔估值", "估值扩张", "估值提升", "冲高", "享受")

# 回归/消化类表述：此类情景的 PE 低于当前 PE(TTM) 是合理的，不算矛盾。
_REVERSION_VERBS: tuple[str, ...] = ("回归", "消化", "回落", "压缩", "杀估值", "均值回归", "下杀")

# 在 PE 区间前回看的字符窗口长度（用于判定该区间所属的估值表述类型）。
_PE_CONTEXT_WINDOW = 50


@dataclass(frozen=True)
class PeContradiction:
    """PE 估值口径矛盾（溢价/抬升情景 PE 上限低于当前 PE(TTM)）。"""

    current_pe: float
    scenario_pe_high: float
    sentence: str
    detail: str


def _extract_current_pe(markdown: str) -> Optional[float]:
    """从报告头部提取当前 PE(TTM)。仅识别 TTM 限定口径，未声明则返回 None。"""
    for pattern in _CURRENT_PE_PATTERNS:
        match = pattern.search(markdown)
        if match:
            return float(match.group(1))
    return None


def _find_pe_bands(markdown: str) -> List[tuple[int, float, float]]:
    """提取估值区间 'low-high x PE'。返回 [(起始位置, 区间下限, 区间上限), ...]。"""
    return [
        (match.start(), float(match.group(1)), float(match.group(2)))
        for match in _PE_BAND_RE.finditer(markdown)
    ]


def _detect_pe_premium_contradictions(
    markdown: str, current_pe: Optional[float]
) -> List[PeContradiction]:
    """检测『溢价/抬升』情景 PE 区间上限低于当前 PE(TTM) 的估值口径矛盾。"""
    if current_pe is None:
        return []

    contradictions: List[PeContradiction] = []
    for pos, _low, high in _find_pe_bands(markdown):
        window = markdown[max(0, pos - _PE_CONTEXT_WINDOW):pos]
        # 显式回归/消化表述 → PE 低于当前是合理的，跳过
        if any(verb in window for verb in _REVERSION_VERBS):
            continue
        # 溢价/抬升表述且区间上限 < 当前 PE → 估值口径矛盾
        if any(verb in window for verb in _PREMIUM_VERBS) and high < current_pe:
            contradictions.append(
                PeContradiction(
                    current_pe=current_pe,
                    scenario_pe_high=high,
                    sentence=window + markdown[pos:pos + 20],
                    detail=(
                        f"『溢价/抬升』情景 PE 上限 {high:g}x 低于当前 PE(TTM) "
                        f"{current_pe:g}x：估值口径矛盾（溢价情景 PE 应 ≥ 当前 PE，"
                        "或改用『回归/消化』表述并说明 EPS 增速如何吸收估值下降）"
                    ),
                )
            )
    return contradictions


class DeepResearchValidator:
    """深度投研报告质量校验器。"""

    def validate(
        self,
        markdown: str,
        tool_calls_log: Optional[List[Dict[str, object]]] = None,
    ) -> ValidationResult:
        """校验报告。纯函数，不抛异常。"""
        if not markdown or not markdown.strip():
            return ValidationResult(
                passed=False,
                score=0,
                missing_layers=list(_LAYER_REQUIREMENTS.keys()),
                details=["报告内容为空"],
            )

        called_tools = _extract_called_tools(tool_calls_log or [])
        details: List[str] = []
        missing_layers: List[str] = []
        missing_tool_groups: List[str] = []
        layer_score = 0.0

        for layer, requirement in _LAYER_REQUIREMENTS.items():
            check = _check_layer(layer, requirement, markdown, called_tools)
            # 估值层无工具组，满分靠内容；其余层内容+工具各占一半
            tool_groups: List[Any] = list(requirement.get("tool_groups") or [])  # type: ignore[arg-type]
            if tool_groups:
                layer_point = 0.0
                layer_incomplete = False
                if check["content_ok"]:
                    layer_point += 10.0
                else:
                    layer_incomplete = True  # 内容关键词缺失也算该层不完整
                if check["tools_ok"]:
                    layer_point += 10.0
                else:
                    layer_incomplete = True
                    missing_tool_groups.extend(check["missing_groups"])  # type: ignore[reportArgumentType]
                if layer_incomplete:
                    missing_layers.append(layer)
            else:
                layer_point = 20.0 if check["content_ok"] else 0.0
                if not check["content_ok"]:
                    missing_layers.append(layer)
            layer_score += layer_point

            if not check["content_ok"] or not check["tools_ok"]:
                reasons = []
                if not check["content_ok"]:
                    reasons.append("内容关键词缺失")
                if not check["tools_ok"]:
                    reasons.append("必要工具未调用")
                details.append(f"{layer}层：{'; '.join(reasons)}")

        # 章节完整性
        missing_sections = [s for s in _REQUIRED_SECTIONS if s not in markdown]

        # 结论前置
        conclusion_count = _count_conclusions(markdown)
        # 概率和
        probability_sum = _check_probability_sum(markdown)

        # 综合评分（层覆盖 100 分为基准，章节/结论/概率作为修正）
        score = int(round(layer_score))
        # 章节缺失扣分（每缺一章 -3，最多 -15）
        score -= min(len(missing_sections) * 3, 15)
        # 结论不足扣分（期望 >=7 个【结论】，每少 1 个 -2，最多 -10）
        if conclusion_count < 7:
            score -= min((7 - conclusion_count) * 2, 10)
        score = max(0, min(100, score))

        passed = (
            not missing_layers
            and not missing_tool_groups
            and len(missing_sections) <= 1
            and conclusion_count >= 5
        )

        if missing_sections:
            details.append(f"缺失章节：{', '.join(missing_sections)}")
        if conclusion_count < 7:
            details.append(f"结论前置标记仅 {conclusion_count} 个（期望 ≥7）")
        if probability_sum > 0 and not (95.0 <= probability_sum <= 105.0):
            details.append(f"三情景概率和为 {probability_sum:.0f}%（期望 100%）")

        # 双源验证标注统计（信息性，不扣分；LLM 按 system_prompt 标 ✓/⚠）
        verified, conflict = _count_validation_markers(markdown)
        if verified or conflict:
            details.append(f"双源验证标注：✓×{verified}（验证通过）/ ⚠×{conflict}（冲突已披露）")

        # PE 估值口径一致性检测（非阻断 L2 信号：只记入 details，不改变 passed/score）
        current_pe = _extract_current_pe(markdown)
        pe_contradictions = _detect_pe_premium_contradictions(markdown, current_pe)
        if pe_contradictions:
            details.append(
                f"估值口径矛盾：{len(pe_contradictions)} 处『溢价/抬升』情景 PE 上限低于当前 PE(TTM) {current_pe:g}x"
            )

        return ValidationResult(
            passed=passed,
            score=score,
            missing_layers=missing_layers,
            missing_tool_groups=missing_tool_groups,
            missing_sections=missing_sections,
            conclusion_count=conclusion_count,
            probability_sum=probability_sum,
            details=details,
            pe_contradictions=pe_contradictions,
        )
