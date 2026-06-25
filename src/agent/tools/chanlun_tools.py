# -*- coding: utf-8 -*-
"""缠论分析工具集。"""

from typing import Any, Dict, List

from src.agent.tools.registry import ToolDefinition, ToolParameter


def _handle_analyze_chanlun(
    symbol: str, market: str = "A", lookback_days: int = 365
) -> Dict[str, Any]:
    """对股票进行缠论技术分析。"""
    from src.services.chanlun_service import ChanlunService

    service = ChanlunService()
    return service.analyze(symbol=symbol, market=market, lookback_days=lookback_days)


analyze_chanlun_tool = ToolDefinition(
    name="analyze_chanlun",
    description=(
        "缠论技术分析工具。对股票进行完整的缠论日线分析。\n\n"
        "输入股票代码和市场，返回缠论结构化分析结果：\n"
        "- 分型（顶/底分型）\n"
        "- 笔（上涨/下跌笔，含背驰检测）\n"
        "- 中枢（震荡区间）\n"
        "- 买卖点（1买/2买/3买/1卖/2卖/3卖）\n"
        "- 趋势判断与评分\n\n"
        "适用于分析个股日线走势，判断当前趋势、位置、背驰和买卖点信号。"
    ),
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="股票代码：A股6位数字如600519、000001；港股4-5位如0700；美股字母如AAPL",
            required=True,
        ),
        ToolParameter(
            name="market",
            type="string",
            description="市场：A=A股，HK=港股，US=美股，CRYPTO=加密货币",
            required=False,
            default="A",
        ),
        ToolParameter(
            name="lookback_days",
            type="integer",
            description="回溯分析的天数（默认365）",
            required=False,
            default=365,
        ),
    ],
    handler=_handle_analyze_chanlun,
    category="analysis",
)

ALL_CHANLUN_TOOLS: List[ToolDefinition] = [analyze_chanlun_tool]
