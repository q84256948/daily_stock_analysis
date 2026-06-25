# -*- coding: utf-8 -*-
"""
Value Scenario Prompts for P3.

Prompts for long-term value analysis:
1. Value horizon analysis (1Y/3Y/5Y)
2. Scenario analysis (bull/base/bear)
3. Value anchor determination
"""

VALUE_SCENARIO_ANALYSIS_PROMPT = """## 长期价值情景分析

你是一位专业的价值投资分析师。请根据以下信息分析标的的长期投资价值。

### 标的信息
- 股票代码: {stock_code}
- 股票名称: {stock_name}
- 行业: {industry}

### 基本面数据
- 市盈率(PE): {pe}
- 市净率(PB): {pb}
- 净资产收益率(ROE): {roe}%
- 营收增长率: {revenue_growth}%
- 净利润增长率: {profit_growth}%
- 毛利率: {gross_margin}%
- 行业平均PE: {sector_pe}

### 估值数据
- 当前价格: {current_price}
- 总市值: {market_cap}
- 流通市值: {float_market_cap}
- 52周最高: {high_52w}
- 52周最低: {low_52w}

### 行业空间
{industry_space}

### 竞争格局
{competitive_landscape}

### 分析要求

请输出以下JSON格式的价值情景分析：

```json
{{
    "value_horizons": {{
        "horizon_1y": "1年价值区间(如: 150-180元)",
        "horizon_3y": "3年价值区间",
        "horizon_5y": "5年价值区间"
    }},
    "scenarios": {{
        "bull_case": {{
            "probability": 0.0-0.5,
            "value_anchor": "乐观情景目标价",
            "upside_pct": 0-500,
            "key_assumptions": ["假设1", "假设2"],
            "timeframe_years": 1-5
        }},
        "base_case": {{
            "probability": 0.3-0.6,
            "value_anchor": "基准情景目标价",
            "upside_pct": 0-200,
            "key_assumptions": ["假设1", "假设2"],
            "timeframe_years": 1-5
        }},
        "bear_case": {{
            "probability": 0.1-0.3,
            "value_anchor": "悲观情景目标价",
            "downside_pct": 0-50,
            "key_assumptions": ["假设1", "假设2"],
            "timeframe_years": 1-5
        }}
    }},
    "edge_calculation": {{
        "prior_probability": 0.3-0.7,
        "market_implied_prob": 0.3-0.7,
        "edge": -1.0到1.0,
        "edge_rationale": "赔率计算理由"
    }},
    "catalysts": ["催化剂1", "催化剂2", "催化剂3"],
    "risks": ["风险1", "风险2", "风险3"],
    "value_score": 0-100
}}
```

### 评分标准

**价值评分 (0-100)**:
- 90-100: 极度低估，强烈推荐
- 75-89: 明显低估，较好机会
- 60-74: 略微低估，关注机会
- 50-59: 合理估值
- 40-49: 略微高估
- 25-39: 明显高估
- 0-24: 极度高估

**情景概率分布**:
- 三个情景概率之和 = 1.0
- 基准情景概率通常最高 (0.4-0.6)
- 乐观和悲观情景概率之和 = 1.0 - 基准情景概率

### 输出要求
1. 只输出JSON格式，不要有其他内容
2. 确保所有数值字段在合理范围内
3. catalysts 不超过5条
4. risks 不超过5条
5. 价值区间要基于当前价格和市场共识
"""


VALUE_SUMMARY_PROMPT = """## 价值分析摘要

基于以下价值分析数据，生成一段简洁的投资参考摘要：

### 价值分析数据
{value_data}

### 当前价格
当前价格: {current_price}

### 生成要求

请生成一段80-120字的投资参考摘要，包括：
1. 当前估值水平 (低估/合理/高估)
2. 1年/3年/5年价值区间
3. 主要投资逻辑和催化剂
4. 主要风险因素

### 输出格式
直接输出摘要文本，不要加引号或其他格式。
"""


def build_value_scenario_prompt(
    stock_code: str,
    stock_name: str,
    industry: str = "",
    pe: float = None,
    pb: float = None,
    roe: float = None,
    revenue_growth: float = None,
    profit_growth: float = None,
    gross_margin: float = None,
    sector_pe: float = None,
    current_price: float = None,
    market_cap: float = None,
    float_market_cap: float = None,
    high_52w: float = None,
    low_52w: float = None,
    industry_space: str = "",
    competitive_landscape: str = "",
) -> str:
    """
    Build value scenario analysis prompt with data.

    Args:
        stock_code: Stock code
        stock_name: Stock name
        industry: Industry classification
        pe: P/E ratio
        pb: P/B ratio
        roe: Return on equity
        revenue_growth: Revenue growth rate
        profit_growth: Profit growth rate
        gross_margin: Gross margin
        sector_pe: Sector average P/E
        current_price: Current stock price
        market_cap: Total market cap
        float_market_cap: Float market cap
        high_52w: 52-week high
        low_52w: 52-week low
        industry_space: Industry space description
        competitive_landscape: Competitive landscape description

    Returns:
        Formatted prompt string
    """

    def fmt(val, suffix=""):
        if val is None:
            return "未知"
        if suffix == "%":
            return f"{val:.2f}%"
        if suffix == "亿":
            return f"{val:.2f}亿"
        if suffix == "元":
            return f"{val:.2f}元"
        return str(val)

    industry_space_str = industry_space if industry_space else "行业空间数据暂无"
    competitive_str = (
        competitive_landscape if competitive_landscape else "竞争格局数据暂无"
    )

    return VALUE_SCENARIO_ANALYSIS_PROMPT.format(
        stock_code=stock_code,
        stock_name=stock_name,
        industry=industry or "未知",
        pe=fmt(pe),
        pb=fmt(pb),
        roe=fmt(roe, "%"),
        revenue_growth=fmt(revenue_growth, "%"),
        profit_growth=fmt(profit_growth, "%"),
        gross_margin=fmt(gross_margin, "%"),
        sector_pe=fmt(sector_pe),
        current_price=fmt(current_price, "元"),
        market_cap=fmt(market_cap, "亿"),
        float_market_cap=fmt(float_market_cap, "亿"),
        high_52w=fmt(high_52w, "元"),
        low_52w=fmt(low_52w, "元"),
        industry_space=industry_space_str,
        competitive_landscape=competitive_str,
    )
