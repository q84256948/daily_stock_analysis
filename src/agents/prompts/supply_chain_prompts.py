# -*- coding: utf-8 -*-
from typing import Any, Optional
"""
Supply Chain Analysis Prompts for P2.

Prompts for supply chain positioning analysis:
1. Chain position analysis
2. Moat assessment
3. US-China dual chain risk
4. Customer concentration
"""

SUPPLY_CHAIN_ANALYSIS_PROMPT = """## 产业链定位分析

你是一位专业的产业链分析师。请根据以下信息分析标的的产业链定位和竞争优势。

### 标的信息
- 股票代码: {stock_code}
- 股票名称: {stock_name}
- 行业: {industry}
- 主营业务: {main_business}

### 概念板块数据
{concept_board_data}

### 机构持仓数据
{institutional_data}

### 北向资金数据
{northbound_data}

### 分析要求

请输出以下JSON格式的产业链分析：

```json
{{
    "chain_position": "upstream|bottleneck|midstream|downstream|commodity",
    "chain_position_rationale": "判断理由",
    "moat_type": "patent|technology|brand|network|switching_cost|license|regulatory|multiple",
    "moat_strength": "strong|moderate|weak|none",
    "moat_rationale": "护城河分析理由",
    "customer_concentration_hhi": 0.0-1.0,
    "customer_concentration_rationale": "客户集中度分析",
    "us_china_risk": "high|medium|low|none",
    "us_china_risk_rationale": "中美链风险分析",
    "chokepoint_type": "patent|capacity|geo|tech|cert|network|none",
    "overall_supply_chain_score": 0-100,
    "key_insights": ["关键洞察1", "关键洞察2"],
    "risks": ["风险1", "风险2"]
}}
```

### 评分标准

**产业链位置评分**:
- bottleneck (卡脖子): 90-100分 - 掌握核心技术/材料，不可替代
- upstream (上游): 80-89分 - 原材料或核心零部件供应商
- midstream (中游): 60-79分 - 加工制造环节
- downstream (下游): 40-59分 - 终端产品/服务
- commodity (大宗商品): 10-39分 - 高度同质化竞争

**护城河评分**:
- strong: 基础分 × 1.0 - 专利/技术/品牌/网络效应明显
- moderate: 基础分 × 0.7 - 有一定壁垒但可复制
- weak: 基础分 × 0.4 - 壁垒较弱
- none: 基础分 × 0.1 - 无护城河

**中美链风险评分**:
- none: 100分 - 完全内循环
- low: 80分 - 影响可控
- medium: 50分 - 需关注
- high: 25分 - 高度依赖或受制

### 输出要求
1. 只输出JSON格式，不要有其他内容
2. 确保所有字段都有值
3. chain_position_rationale 不超过100字
4. key_insights 不超过3条
5. risks 不超过3条
"""


SUPPLY_CHAIN_SUMMARY_PROMPT = """## 产业链分析摘要

基于以下产业链分析数据，生成一段简洁的投资参考摘要：

### 产业链分析数据
{chain_data}

### 生成要求

请生成一段50-80字的投资参考摘要，包括：
1. 产业链位置和定位
2. 主要护城河类型
3. 需要关注的风险

### 输出格式
直接输出摘要文本，不要加引号或其他格式。
"""


def build_supply_chain_prompt(
    stock_code: str,
    stock_name: str,
    industry: str = "",
    main_business: str = "",
    concept_boards: Optional[list[Any]] = None,
    institutional_data: Optional[dict[str, Any]] = None,
    northbound_data: Optional[dict[str, Any]] = None,
) -> str:
    """
    Build supply chain analysis prompt with data.

    Args:
        stock_code: Stock code
        stock_name: Stock name
        industry: Industry classification
        main_business: Main business description
        concept_boards: List of concept boards from data provider
        institutional_data: Institutional holdings data
        northbound_data: Northbound flow data

    Returns:
        Formatted prompt string
    """
    concept_str = "暂无概念板块数据"
    if concept_boards:
        boards_str = "\n".join(
            [
                f"- {b.get('name', '')}: 涨跌幅 {b.get('change_pct', 0):.2f}%"
                for b in concept_boards[:5]
            ]
        )
        concept_str = f"所属概念板块:\n{boards_str}"

    institutional_str = "暂无机构持仓数据"
    if institutional_data:
        holders = institutional_data.get("holders", [])
        inst_ratio = institutional_data.get("institutional_ratio", 0)
        holders_str = "\n".join(
            [
                f"- {h.get('name', '')}: 持股比例 {h.get('hold_ratio', 0):.2f}%, 变化 {h.get('change', 0):+.2f}%"
                for h in holders[:5]
            ]
        )
        institutional_str = f"""机构持仓情况:
- 机构总持股比例: {inst_ratio:.2f}%
{holders_str}"""

    northbound_str = "暂无北向资金数据"
    if northbound_data:
        flow_20d = northbound_data.get("northbound_flow_20d", 0)
        flow_str = "净流入" if flow_20d > 0 else "净流出"
        northbound_str = f"""北向资金:
- 近20日{flow_str}: {abs(flow_20d):.2f}亿元"""

    return SUPPLY_CHAIN_ANALYSIS_PROMPT.format(
        stock_code=stock_code,
        stock_name=stock_name,
        industry=industry or "未知",
        main_business=main_business or "未知",
        concept_board_data=concept_str,
        institutional_data=institutional_str,
        northbound_data=northbound_str,
    )
