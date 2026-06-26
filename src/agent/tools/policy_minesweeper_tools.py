# -*- coding: utf-8 -*-
"""政策与公告双维度排雷专属工具集。

当前仅 1 个工具：``score_policy_minesweeper``（包装
``src.services.policy_minesweeper_scorecard`` 的确定性评分卡）。其余数据/情报
工具（行情/新闻/基本面/板块）**复用问股的全局 ToolRegistry**，通过
``build_policy_minesweeper_executor`` 在 factory 里合并注册（见 factory.py）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.agent.tools.registry import ToolDefinition, ToolParameter
from src.services import policy_minesweeper_scorecard as _scorecard

logger = logging.getLogger(__name__)

# 六维方向评分（各 -100 强利空 ~ +100 强利好）；key 与 scorecard 保持一致
DIMENSION_HINTS: Dict[str, str] = {
    "event_importance": "事件重要性（利好+ / 利空-）",
    "policy_exposure": "政策相关度/暴露度",
    "earnings_impact": "盈利影响",
    "valuation_impact": "估值影响",
    "price_sensitivity": "股价敏感度（市值/流动性/Beta）",
    "time_urgency": "时间紧迫度",
}


def _handle_score_policy_minesweeper(
    stock_code: str,
    stock_name: str,
    horizon: str = "medium",
    dimensions: Optional[Dict[str, Any]] = None,
    alpha_score: Optional[float] = None,
    beta_score: Optional[float] = None,
    dominant_factor: str = "",
    confidence: Optional[float] = None,
    scenarios: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """对一只 A 股做"政策与公告双维度排雷"打分（综合分 -100~+100）。"""
    payload = {
        "stock_code": stock_code or "",
        "stock_name": stock_name or "",
        "dimensions": dimensions or {},
        "alpha_score": alpha_score,
        "beta_score": beta_score,
        "dominant_factor": dominant_factor or "",
        "confidence": confidence,
        "scenarios": scenarios or {},
        "evidence": evidence or [],
    }
    try:
        result = _scorecard.score(payload, horizon)
    except Exception as exc:  # noqa: BLE001 - 评分卡纯函数，任何异常都回退为错误而非崩
        logger.error("policy minesweeper scorecard failed for %s: %s", stock_code, exc, exc_info=True)
        return {"error": f"打分失败: {exc}", "input_echo": payload}

    return {
        "stock_code": result["stock_code"],
        "stock_name": result["stock_name"],
        "verdict": f"{result['emoji']} {result['label']}",
        "final": result["final"],
        "action": result["action"],
        "expected_car": result["expected_car"],
        "score_report_markdown": _scorecard.to_markdown(result),
        "usage_note": (
            "以上为政策与公告双维度排雷打分结果，衡量政策/公告对股价的利好利空冲击，"
            "非精确预测；预期冲击为历史经验区间。引用请保留证据来源与日期。"
            "不构成投资建议，买卖由你自己决定。"
        ),
    }


score_policy_minesweeper_tool = ToolDefinition(
    name="score_policy_minesweeper",
    description=(
        "对一只 A 股做『政策与公告双维度排雷』打分（综合分 -100 强利空 ~ +100 强利好）。"
        "输入：六维方向评分（事件重要性/政策相关度/盈利影响/估值影响/股价敏感度/"
        "时间紧迫度，各 -100~+100）、α 公司层面分、β 政策层面分、时间窗口"
        "（short/medium/long）。返回综合分、5 档等级、仓位指令、预期冲击区间与 "
        "Markdown 报告。用于『排雷 300750』『政策公告对 XX 是利好还是利空』类问题。"
    ),
    parameters=[
        ToolParameter(name="stock_code", type="string",
                      description="A 股代码（如 300750）", required=True),
        ToolParameter(name="stock_name", type="string",
                      description="公司名称", required=True),
        ToolParameter(name="horizon", type="string",
                      description="时间窗口：short(1-5日)/medium(1-4周)/long(1-6月)",
                      required=False, enum=["short", "medium", "long"], default="medium"),
        ToolParameter(
            name="dimensions", type="object",
            description="六维方向评分（各 -100~+100），key 固定："
            + "；".join(f"{k}({h})" for k, h in DIMENSION_HINTS.items()),
            required=True,
        ),
        ToolParameter(name="alpha_score", type="number",
                      description="公司层面（α 公告扫描）综合分 -100~+100，可选",
                      required=False, default=None),
        ToolParameter(name="beta_score", type="number",
                      description="政策层面（β 政策分析）综合分 -100~+100，可选",
                      required=False, default=None),
        ToolParameter(name="dominant_factor", type="string",
                      description="主导因子说明（如『宏观压制 > 公司利好』），可选",
                      required=False, default=""),
        ToolParameter(name="confidence", type="number",
                      description="置信度 0~1，可选", required=False, default=None),
        ToolParameter(
            name="scenarios", type="object",
            description="情景分析：{optimistic/base_case/pessimistic: {assumption, score}}，可选",
            required=False, default=None,
        ),
        ToolParameter(
            name="evidence", type="array",
            description="证据列表，每项 {claim, source, date, strength(primary/media/analysis/social/rumor)}，可选",
            required=False, default=None,
        ),
    ],
    handler=_handle_score_policy_minesweeper,
    category="analysis",
)


ALL_POLICY_MINESWEEPER_TOOLS = [score_policy_minesweeper_tool]
