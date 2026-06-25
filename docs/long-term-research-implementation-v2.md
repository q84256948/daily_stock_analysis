# 五段式长线产业链投研报告 - 完整实施方案

> 版本：v2.0（审计调整版）
> 日期：2026-06-23
> 状态：可执行

---

## 一、方案概述

### 1.1 核心目标

将个股分析报告从「短线趋势交易」升级为「长线产业链/供应链投研 + 贝叶斯概率框架」：

| 维度 | 旧版 | 新版 |
|------|------|------|
| 核心问题 | 今天买还是卖？ | 是产业链瓶颈/长期赢家吗？市场错判多少？ |
| 决策本质 | 六维线性加权 0-100 | 先验 P(H) + Edge + 后验更新 |
| 技术面权重 | 25% | 10%（降为长线择时辅助） |
| 时间维度 | 1天/1周/1月 | 1年/3年/5年价值锚 |

### 1.2 五段式报告结构

| 段落 | 内容 | 核心字段 |
|------|------|----------|
| ① 投资结论 | 先验 P(H)、Edge、仓位建议、1/3/5年价值区间 | `investment_conclusion` |
| ② 产业链解读 | 供应链地图、瓶颈点、中美双链 | `supply_chain` |
| ③ 长期价值与情景 | 产业空间、竞争演变、乐观/中性/悲观情景 | `value_scenarios` |
| ④ 贝叶斯评分表 | 六维 × 权重 × 打分 → P(H)；市场隐含 → Edge | `bayesian_framework` |
| ⑤ 六维详情 | 每个指标详细分析 + 证据来源 + 可信度 | `research_framework` |

---

## 二、架构设计

### 2.1 目录结构

```
src/
├── scoring/                              # 纯函数评分 + 贝叶斯引擎
│   ├── __init__.py                       # 公开接口
│   ├── contracts.py                       # 数据契约 (IndicatorInput, DimensionScore, etc.)
│   ├── weights.py                        # 六维权重配置 + 版本校验
│   ├── engine.py                         # 六维加权聚合引擎
│   ├── bayesian.py                       # 贝叶斯核心 (先验/Edge/后验/仓位/止损)
│   ├── normalization.py                   # 归一化/Clamp工具
│   └── indicators/                       # 各维度评分实现
│       ├── supply_chain.py               # 产业链定位 (LLM驱动)
│       ├── fundamental.py                 # 基本面 (估值=规则, 护城河=LLM)
│       ├── capital.py                    # 资金面 (规则: 机构/北向/融资/筹码)
│       ├── technical.py                   # 技术面 (规则: 长期趋势)
│       ├── sentiment.py                  # 情绪面 (研报=规则聚合, 社交=LLM)
│       └── macro.py                      # 宏观面 (流动性=规则, 中美链=LLM)
│
├── schemas/                              # Schema定义
│   ├── research_framework.py             # 六维评分 Schema
│   ├── bayesian_framework.py             # 贝叶斯框架 Schema
│   ├── supply_chain.py                  # 产业链 Schema
│   ├── value_scenarios.py               # 价值情景 Schema
│   └── investment_conclusion.py          # 投资结论 Schema
│
├── repositories/                         # 数据访问层
│   ├── position_ledger_repo.py          # 长线持仓台账
│   ├── belief_ledger_repo.py            # 概率与证据台账
│   └── score_ledger_repo.py             # 六维评分台账
│
└── services/
    └── research_scoring_service.py       # 投研评分编排服务

data_provider/
└── supply_chain_fetcher.py               # P2: 产业链数据源

src/agent/agents/
├── supply_chain_agent.py                 # P3: 产业链Agent
└── value_agent.py                       # P3: 长线价值Agent
```

### 2.2 数据流

```
报告生成 (analyzer.py)
       ↓
ResearchScoringService.process()
       ↓
┌──────────────────────────────────────────┐
│  1. 客观评分 (规则函数)                    │
│     - capital.py: 机构持仓/北向/融资        │
│     - technical.py: 长期趋势/关键位        │
│     - fundamental.py: 估值PE分位          │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  2. 主观评分 (LLM输入)                    │
│     - supply_chain.py: 产业链定位         │
│     - sentiment.py: 社交情绪/市场隐含       │
│     - macro.py: 中美链/政策               │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  3. 六维聚合 (engine.py)                 │
│     - 权重校验: sum(weights) == 1.0     │
│     - 空值处理: 默认中性分50               │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  4. 贝叶斯计算 (bayesian.py)              │
│     - 先验映射: dimension_total → P(H)   │
│     - Edge: prior_p - market_implied_p   │
│     - 后验更新: update_posterior()        │
│     - 仓位建议: map_position()            │
│     - 止损检查: check_stop_conditions()   │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  5. 台账持久化                            │
│     - position_ledger: 持仓记录           │
│     - belief_ledger: 概率演化             │
│     - score_ledger: 六维快照             │
└──────────────────────────────────────────┘
```

---

## 三、核心模块详细设计

### 3.1 贝叶斯引擎 (`src/scoring/bayesian.py`)

```python
# -*- coding: utf-8 -*-
"""
贝叶斯概率引擎 - 纯函数，无外部依赖

核心函数：
- map_prior(): 六维总分 → 先验概率
- calculate_edge(): 先验 - 市场隐含
- update_posterior(): 后验更新 (似然比)
- map_position(): Edge → 仓位建议
- check_stop_conditions(): 长线止损检查
"""

from dataclasses import dataclass
from typing import Optional

# ============== 数据结构 ==============

@dataclass(frozen=True)
class BayesianResult:
    """贝叶斯计算结果"""
    prior_p: float           # 先验概率 P(H)
    market_implied_p: float  # 市场隐含概率
    edge: float              # Edge = 先验 - 市场隐含
    posterior_p: float        # 后验概率 P(H|E)
    position_suggestion: str  # 仓位建议 (如 "3-5%")
    stop_conditions: dict     # 止损条件触发状态
    
    def __post_init__(self):
        # 防御性校验
        assert 0 <= self.prior_p <= 1, f"prior_p must be in [0,1], got {self.prior_p}"
        assert 0 <= self.market_implied_p <= 1, f"market_implied_p must be in [0,1]"
        assert 0 <= self.posterior_p <= 1, f"posterior_p must be in [0,1]"


# ============== 核心函数 ==============

def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """数值边界钳制，防止浮点误差"""
    return max(min_val, min(max_val, value))


def odds(p: float) -> float:
    """
    概率 → 赔率
    O = P / (1 - P)
    
    Args:
        p: 概率 [0, 1)
    
    Returns:
        赔率 (odds)
    
    Raises:
        ValueError: 当 P >= 1
    """
    if p >= 1:
        raise ValueError(f"Cannot compute odds for p >= 1, got {p}")
    if p < 0:
        return 0.0  # P < 0 视为确定性不发生
    return p / (1 - p)


def probability(odds_val: float) -> float:
    """
    赔率 → 概率
    P = O / (1 + O)
    
    Args:
        odds_val: 赔率 >= 0
    
    Returns:
        概率 [0, 1]
    """
    if odds_val < 0:
        raise ValueError(f"Odds must be >= 0, got {odds_val}")
    if odds_val == float('inf'):
        return 1.0
    return odds_val / (1 + odds_val)


def map_prior(dimension_total: float) -> float:
    """
    六维加权总分 → 先验概率 P(H)
    
    分段映射表：
    | 六维总分 | 先验 P(H) | 含义             |
    |----------|------------|------------------|
    | ≥85      | 0.80–1.00 | 极端瓶颈/长期赢家 |
    | 70–85    | 0.60–0.80 | 强瓶颈           |
    | 55–70    | 0.40–0.60 | 中等             |
    | 40–55    | 0.20–0.40 | 弱               |
    | <40      | 0.00–0.20 | 非瓶颈/商品化     |
    
    Args:
        dimension_total: 六维加权总分 [0, 100]
    
    Returns:
        先验概率 P(H) [0, 1]
    
    Examples:
        >>> map_prior(90)
        0.933...
        >>> map_prior(50)
        0.333...
        >>> map_prior(30)
        0.15
    """
    if dimension_total >= 85:
        # [85, 100] → [0.80, 1.00], 线性插值
        ratio = (dimension_total - 85) / 15.0
        result = 0.80 + ratio * 0.20
    elif dimension_total >= 70:
        # [70, 85) → [0.60, 0.80)
        ratio = (dimension_total - 70) / 15.0
        result = 0.60 + ratio * 0.20
    elif dimension_total >= 55:
        # [55, 70) → [0.40, 0.60)
        ratio = (dimension_total - 55) / 15.0
        result = 0.40 + ratio * 0.20
    elif dimension_total >= 40:
        # [40, 55) → [0.20, 0.40)
        ratio = (dimension_total - 40) / 15.0
        result = 0.20 + ratio * 0.20
    else:
        # [0, 40) → [0.00, 0.20)
        result = dimension_total / 40.0 * 0.20
    
    return _clamp(result, 0.0, 1.0)


def calculate_edge(prior_p: float, market_implied_p: float) -> float:
    """
    计算认知差 Edge
    
    Edge = P(H) - P_market
    
    Args:
        prior_p: 先验概率 [0, 1]
        market_implied_p: 市场隐含概率 [0, 1]
    
    Returns:
        Edge (-1 到 1), 正值表示正向Edge
    
    Examples:
        >>> calculate_edge(0.7, 0.5)
        0.2
        >>> calculate_edge(0.3, 0.6)
        -0.3
    """
    return prior_p - market_implied_p


def update_posterior(prior_p: float, lr: float) -> float:
    """
    贝叶斯后验更新 (赔率形式)
    
    O(H|E) = O(H) × LR
    P(H|E) = O(H|E) / (1 + O(H|E))
    
    似然比 (Likelihood Ratio) 参考：
    | 证据强度   | LR范围  | 典型证据                    |
    |------------|---------|-----------------------------|
    | 强正面     | 5–10    | 大客户独家订单、竞争者退出    |
    | 弱正面     | 2–3     | 行业需求向好、小批量订单     |
    | 中性       | ~1       | 无重大新闻、技术性波动        |
    | 弱反面     | 0.3–0.5 | 季度略低预期、新竞争者进入    |
    | 强反面     | 0.1–0.2 | 技术路线颠覆、核心专利无效    |
    
    Args:
        prior_p: 先验概率 (0, 1)
        lr: 似然比 (Likelihood Ratio) > 0
    
    Returns:
        后验概率 P(H|E) [0, 1]
    
    Examples:
        >>> update_posterior(0.6, 8.0)
        0.923...
        >>> update_posterior(0.6, 0.125)
        0.161...
    """
    if lr <= 0:
        raise ValueError(f"LR must be > 0, got {lr}")
    
    prior_odds = odds(prior_p)
    posterior_odds = prior_odds * lr
    posterior_p = probability(posterior_odds)
    
    return _clamp(posterior_p, 0.0, 1.0)


def map_position(edge: float) -> tuple[str, str]:
    """
    Edge → 仓位建议
    
    | Edge范围    | 仓位建议  | 信心等级 |
    |-------------|-----------|----------|
    | >50% (>0.5) | 5-8%     | 高       |
    | 30-50%      | 3-5%     | 中       |
    | 10-30%      | 1-3%     | 低       |
    | <10% (<0.1) | 0-1%     | 观察     |
    
    Args:
        edge: Edge值 (-1 到 1)
    
    Returns:
        (仓位建议, 信心等级)
    
    Examples:
        >>> map_position(0.55)
        ('5-8%', '高')
        >>> map_position(0.2)
        ('1-3%', '低')
    """
    if edge > 0.5:
        return "5-8%", "高"
    elif edge > 0.3:
        return "3-5%", "中"
    elif edge > 0.1:
        return "1-3%", "低"
    else:
        return "0-1%", "观察"


def check_stop_conditions(
    prior_p: float,
    posterior_p: float,
    market_implied_p: float,
    strong_negative_evidence: bool = False,
) -> dict:
    """
    长线止损条件检查
    
    触发任一条件即应考虑止损：
    1. 后验跌破先验的60%阈值
    2. 强反面证据出现
    3. 认知差消失 (市场隐含 ≥ 先验)
    
    注意：长线止损使用后验/认知差逻辑，不使用短线技术位
    
    Args:
        prior_p: 先验概率
        posterior_p: 后验概率
        market_implied_p: 市场隐含概率
        strong_negative_evidence: 是否存在强反面证据
    
    Returns:
        dict with stop conditions status
    """
    return {
        "posterior_below_prior_threshold": posterior_p < prior_p * 0.6,
        "strong_negative_evidence": strong_negative_evidence,
        "edge_disappeared": market_implied_p >= prior_p,
        "should_stop": (
            posterior_p < prior_p * 0.6
            or strong_negative_evidence
            or market_implied_p >= prior_p
        )
    }


# ============== 组合校验 ==============

def validate_position_with_concentration(
    suggested_position: str,
    current_concentration: float,
    sector_limit: float = 0.4
) -> tuple[bool, Optional[str]]:
    """
    结合赛道集中度校验仓位建议
    
    单赛道集中度 ≤ 40% 约束
    
    Args:
        suggested_position: 建议仓位 (如 "5-8%")
        current_concentration: 当前赛道集中度 [0, 1]
        sector_limit: 赛道集中度上限 (默认40%)
    
    Returns:
        (是否通过, 警告信息)
    """
    # 解析建议仓位为数值
    position_map = {
        "0-1%": 0.005,
        "1-3%": 0.02,
        "3-5%": 0.04,
        "5-8%": 0.065,
    }
    new_position = position_map.get(suggested_position, 0.01)
    
    # 检查集中度
    if current_concentration + new_position > sector_limit:
        adjusted = sector_limit - current_concentration
        adjusted_str = f"{max(0, adjusted * 100):.1f}%"
        return False, (
            f"超出赛道集中度限制({sector_limit*100:.0f}%), "
            f"建议仓位调整为 {adjusted_str} 以下"
        )
    
    return True, None


# ============== 入口函数 ==============

def calculate_bayesian(
    dimension_total: float,
    market_implied_p: float,
    lr: float = 1.0,
    strong_negative_evidence: bool = False,
    current_concentration: float = 0.0,
) -> BayesianResult:
    """
    贝叶斯计算完整入口
    
    一站式计算：先验 → Edge → 后验 → 仓位 → 止损
    
    Args:
        dimension_total: 六维加权总分 [0, 100]
        market_implied_p: 市场隐含概率 [0, 1]
        lr: 似然比 (默认1.0=无新证据)
        strong_negative_evidence: 是否存在强反面证据
        current_concentration: 当前赛道集中度 [0, 1]
    
    Returns:
        BayesianResult
    """
    prior_p = map_prior(dimension_total)
    edge = calculate_edge(prior_p, market_implied_p)
    posterior_p = update_posterior(prior_p, lr)
    position_suggestion, _ = map_position(edge)
    
    stop_conditions = check_stop_conditions(
        prior_p, posterior_p, market_implied_p, strong_negative_evidence
    )
    
    # 集中度校验
    valid, warning = validate_position_with_concentration(
        position_suggestion, current_concentration
    )
    if warning:
        stop_conditions["concentration_warning"] = warning
    
    return BayesianResult(
        prior_p=prior_p,
        market_implied_p=market_implied_p,
        edge=edge,
        posterior_p=posterior_p,
        position_suggestion=position_suggestion,
        stop_conditions=stop_conditions
    )
```

### 3.2 六维评分引擎 (`src/scoring/engine.py`)

```python
# -*- coding: utf-8 -*-
"""
六维评分引擎 - 纯函数，无外部依赖

职责：
1. 权重校验：确保 sum(weights) == 1.0
2. 空值处理：缺失数据默认中性分50
3. 加权聚合：六维 → 总分
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# ============== 数据结构 ==============

@dataclass(frozen=True)
class IndicatorScore:
    """单个指标评分"""
    name: str
    score: float                           # [0, 100]
    weight: float                           # [0, 1], 维度内权重
    basis: str = "rule"                    # "rule" | "llm"
    confidence: Optional[str] = None        # "high" | "medium" | "low"
    summary: Optional[str] = None          # 评分理由

@dataclass(frozen=True)
class DimensionScore:
    """单个维度评分"""
    dimension: str                          # 维度名称
    weight: float                          # 权重 [0, 1]
    score: float                          # 维度得分 [0, 100]
    indicators: tuple[IndicatorScore, ...] # 指标列表

@dataclass(frozen=True)
class FrameworkScore:
    """六维投研框架总分"""
    dimension_total: float                 # 六维加权总分 [0, 100]
    dimensions: tuple[DimensionScore, ...] # 六维详情
    version: str = "v1"                   # 评分版本
    warnings: tuple[str, ...] = ()        # 警告信息


# ============== 权重校验 ==============

WEIGHT_EPSILON = 1e-6  # 浮点容差

def validate_weights(weights: List[float]) -> None:
    """
    校验权重和是否为1.0
    
    Args:
        weights: 权重列表
    
    Raises:
        ValueError: 当权重和不为1.0
    """
    weight_sum = sum(weights)
    if abs(weight_sum - 1.0) > WEIGHT_EPSILON:
        raise ValueError(
            f"Weights must sum to 1.0, got {weight_sum}. "
            f"Diff: {abs(weight_sum - 1.0):.6f}"
        )


def validate_weights_safe(weights: List[float]) -> tuple[bool, Optional[str]]:
    """
    安全版权重校验，返回校验结果而非抛出异常
    
    Returns:
        (是否通过, 错误信息)
    """
    weight_sum = sum(weights)
    if abs(weight_sum - 1.0) > WEIGHT_EPSILON:
        return False, (
            f"Weights must sum to 1.0, got {weight_sum:.6f}. "
            f"Difference: {abs(weight_sum - 1.0):.6f}"
        )
    return True, None


# ============== 空值处理 ==============

DEFAULT_NEUTRAL_SCORE = 50.0  # 中性分
DEFAULT_WEIGHT = 1.0 / 6.0   # 六维平均权重

def fill_missing_score(score: Optional[float], default: float = DEFAULT_NEUTRAL_SCORE) -> float:
    """
    填充缺失分数
    
    缺失数据 → 中性分50，不抛异常
    
    Args:
        score: 原始分数，None表示缺失
        default: 默认分数
    
    Returns:
        填充后的分数
    """
    if score is None or not (0 <= score <= 100):
        return default
    return score


# ============== 评分聚合 ==============

def aggregate_dimension(
    indicators: List[Dict[str, Any]],
    default_score: float = DEFAULT_NEUTRAL_SCORE
) -> tuple[float, List[IndicatorScore]]:
    """
    聚合单个维度的指标分数
    
    Args:
        indicators: 指标列表, 每项包含 name, score, weight, basis, confidence, summary
        default_score: 缺失数据的默认分数
    
    Returns:
        (维度得分, 指标评分列表)
    """
    if not indicators:
        return default_score, []
    
    # 解析指标
    parsed = []
    total_weight = 0.0
    
    for ind in indicators:
        score = fill_missing_score(ind.get("score"))
        weight = ind.get("weight", 1.0 / len(indicators))
        total_weight += weight
        
        parsed.append(IndicatorScore(
            name=ind.get("name", "unknown"),
            score=score,
            weight=weight,
            basis=ind.get("basis", "rule"),
            confidence=ind.get("confidence"),
            summary=ind.get("summary"),
        ))
    
    # 归一化权重
    if total_weight > 0:
        for i, p in enumerate(parsed):
            parsed[i] = IndicatorScore(
                name=p.name,
                score=p.score,
                weight=p.weight / total_weight,
                basis=p.basis,
                confidence=p.confidence,
                summary=p.summary,
            )
    
    # 加权求和
    dimension_score = sum(p.score * p.weight for p in parsed)
    
    return dimension_score, parsed


def aggregate_framework(
    dimensions: List[Dict[str, Any]],
    version: str = "v1"
) -> FrameworkScore:
    """
    聚合六维为总分
    
    Args:
        dimensions: 六维列表, 每项包含:
            - dimension: str 维度名称
            - weight: float 权重 [0, 1]
            - score: float 维度得分 [0, 100] (可选, 缺失用50)
            - indicators: List[Dict] 指标列表 (可选)
        version: 评分版本
    
    Returns:
        FrameworkScore
    
    Raises:
        ValueError: 权重和不等于1.0
    
    Examples:
        >>> result = aggregate_framework([
        ...     {"dimension": "产业链定位", "weight": 0.25, "score": 80},
        ...     {"dimension": "基本面", "weight": 0.25, "score": 70},
        ...     {"dimension": "资金面", "weight": 0.15, "score": 65},
        ...     {"dimension": "技术面", "weight": 0.10, "score": 75},
        ...     {"dimension": "情绪面", "weight": 0.15, "score": 60},
        ...     {"dimension": "宏观面", "weight": 0.10, "score": 55},
        ... ])
        >>> result.dimension_total
        70.75
    """
    # 提取权重
    weights = [d.get("weight", DEFAULT_WEIGHT) for d in dimensions]
    
    # 校验权重
    valid, error = validate_weights_safe(weights)
    if not valid:
        raise ValueError(error)
    
    # 处理维度
    parsed_dims = []
    total = 0.0
    warnings = []
    
    for dim in dimensions:
        dimension_name = dim.get("dimension", "unknown")
        weight = dim.get("weight", DEFAULT_WEIGHT)
        
        # 如果有指标列表，聚合指标
        if "indicators" in dim and dim["indicators"]:
            dim_score, indicators = aggregate_dimension(dim["indicators"])
        else:
            # 直接使用提供的分数
            dim_score = fill_missing_score(dim.get("score"))
            indicators = ()
        
        total += dim_score * weight
        
        parsed_dims.append(DimensionScore(
            dimension=dimension_name,
            weight=weight,
            score=dim_score,
            indicators=tuple(indicators),
        ))
        
        # 检查数据缺失
        if dim.get("score") is None and not dim.get("indicators"):
            warnings.append(f"维度 '{dimension_name}' 数据缺失，使用中性分 {DEFAULT_NEUTRAL_SCORE}")
    
    return FrameworkScore(
        dimension_total=total,
        dimensions=tuple(parsed_dims),
        version=version,
        warnings=tuple(warnings),
    )


# ============== 六维默认权重 ==============

DEFAULT_DIMENSION_WEIGHTS = {
    "产业链定位": 0.25,
    "基本面与价值": 0.25,
    "资金面": 0.15,
    "技术面": 0.10,
    "情绪与认知差": 0.15,
    "宏观与地缘": 0.10,
}

def get_default_weights() -> Dict[str, float]:
    """获取六维默认权重"""
    return dict(DEFAULT_DIMENSION_WEIGHTS)

def get_weight_sum() -> float:
    """获取权重总和（应为1.0）"""
    return sum(DEFAULT_DIMENSION_WEIGHTS.values())
```

### 3.3 数据持久化 (`src/repositories/position_ledger_repo.py`)

```python
# -*- coding: utf-8 -*-
"""
长线持仓台账 Repository

职责：
1. CRUD操作
2. 数据库索引优化
3. 外键关联校验
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Session

from src.storage import Base, get_db


# ============== ORM模型 ==============

class PositionLedger(Base):
    """长线持仓台账"""
    
    __tablename__ = 'position_ledger'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键关联
    report_id = Column(
        Integer,
        ForeignKey('analysis_history.id', ondelete='CASCADE'),
        nullable=True,  # 允许为空（独立记录时）
        index=True
    )
    
    # 股票信息
    stock_code = Column(String(10), nullable=False, index=True)
    market = Column(String(8), nullable=True)  # cn/hk/us
    
    # 投资决策
    action = Column(String(20), nullable=False)  # 建仓/加仓/减仓/止损/观察
    position_size = Column(String(10), nullable=True)  # "3-5%"
    
    # 概率快照
    prior_p = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)
    posterior_p = Column(Float, nullable=True)
    
    # 价值锚
    value_anchor_1y = Column(String(50), nullable=True)
    value_anchor_3y = Column(String(50), nullable=True)
    value_anchor_5y = Column(String(50), nullable=True)
    
    # 状态
    status = Column(String(16), nullable=False, default='open')  # open/closed/stop_hit
    
    # 审计字段
    rationale = Column(String(500), nullable=True)  # 决策理由
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 回测字段
    realized_pnl = Column(Float, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    
    # 索引定义
    __table_args__ = (
        Index('ix_position_ledger_stock_created', 'stock_code', 'created_at'),
        Index('ix_position_ledger_status', 'status'),
        Index('ix_position_ledger_report', 'report_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'report_id': self.report_id,
            'stock_code': self.stock_code,
            'market': self.market,
            'action': self.action,
            'position_size': self.position_size,
            'prior_p': self.prior_p,
            'edge': self.edge,
            'posterior_p': self.posterior_p,
            'value_anchor_1y': self.value_anchor_1y,
            'value_anchor_3y': self.value_anchor_3y,
            'value_anchor_5y': self.value_anchor_5y,
            'status': self.status,
            'rationale': self.rationale,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'realized_pnl': self.realized_pnl,
            'evaluated_at': self.evaluated_at.isoformat() if self.evaluated_at else None,
        }


# ============== Repository ==============

class PositionLedgerRepo:
    """持仓台账数据访问"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, data: Dict[str, Any]) -> PositionLedger:
        """创建持仓记录"""
        record = PositionLedger(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record
    
    def get_by_id(self, id: int) -> Optional[PositionLedger]:
        """根据ID查询"""
        return self.db.query(PositionLedger).filter(PositionLedger.id == id).first()
    
    def get_by_stock(self, stock_code: str, status: Optional[str] = None) -> List[PositionLedger]:
        """根据股票代码查询"""
        query = self.db.query(PositionLedger).filter(PositionLedger.stock_code == stock_code)
        if status:
            query = query.filter(PositionLedger.status == status)
        return query.order_by(PositionLedger.created_at.desc()).all()
    
    def get_open_positions(self) -> List[PositionLedger]:
        """获取所有未平仓记录"""
        return self.db.query(PositionLedger).filter(
            PositionLedger.status == 'open'
        ).order_by(PositionLedger.created_at.desc()).all()
    
    def get_concentration_by_sector(self) -> Dict[str, float]:
        """获取各赛道集中度（简化版，需接入板块数据）"""
        open_positions = self.get_open_positions()
        concentration = {}
        total = len(open_positions)
        
        if total == 0:
            return concentration
        
        for pos in open_positions:
            # TODO: 需要接入板块数据，这里简化处理
            sector = "default"
            concentration[sector] = concentration.get(sector, 0) + 1
        
        # 转为比例
        return {k: v / total for k, v in concentration.items()}
    
    def update_status(self, id: int, status: str, realized_pnl: Optional[float] = None) -> bool:
        """更新持仓状态"""
        record = self.get_by_id(id)
        if not record:
            return False
        
        record.status = status
        if realized_pnl is not None:
            record.realized_pnl = realized_pnl
        record.evaluated_at = datetime.now()
        
        self.db.commit()
        return True
    
    def delete(self, id: int) -> bool:
        """删除记录"""
        record = self.get_by_id(id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
```

### 3.4 前端组件 (`apps/dsa-web/src/components/report/InvestmentConclusionView.tsx`)

```typescript
// -*- coding: utf-8 -*-
/**
 * 投资结论展示组件
 * 
 * 特性：
 * 1. 旧报告兼容：字段缺失时显示占位符
 * 2. Edge负值处理：红色标识负向Edge
 * 3. 响应式布局
 */

import React, { useMemo } from 'react';

interface InvestmentConclusionViewProps {
  data?: {
    prior_p?: number;
    edge?: number;
    position?: string;
    value_range_1y?: string;
    value_range_3y?: string;
    value_range_5y?: string;
    rationale?: string;
    action?: string;
  };
}

// Edge颜色映射
const getEdgeColor = (edge?: number): string => {
  if (edge === undefined || edge === null) return 'text-muted-text';
  if (edge > 0.3) return 'text-green-500';      // 正向高Edge
  if (edge > 0.1) return 'text-green-400';    // 正向低Edge
  if (edge > -0.1) return 'text-yellow-500';   // 接近中性
  if (edge > -0.3) return 'text-orange-500';    // 负向低Edge
  return 'text-red-500';                          // 负向高Edge
};

// Edge背景色映射
const getEdgeBgColor = (edge?: number): string => {
  if (edge === undefined || edge === null) return 'bg-muted/10';
  if (edge > 0.3) return 'bg-green-500/10';
  if (edge > 0.1) return 'bg-green-400/10';
  if (edge > -0.1) return 'bg-yellow-500/10';
  if (edge > -0.3) return 'bg-orange-500/10';
  return 'bg-red-500/10';
};

// 操作动作颜色
const getActionBadgeStyles = (action?: string): string => {
  const styles: Record<string, string> = {
    '建仓': 'bg-green-500/20 text-green-500 border border-green-500/30',
    '加仓': 'bg-green-500/20 text-green-500 border border-green-500/30',
    '持有': 'bg-blue-500/20 text-blue-500 border border-blue-500/30',
    '观察': 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30',
    '减仓': 'bg-orange-500/20 text-orange-500 border border-orange-500/30',
    '止损': 'bg-red-500/20 text-red-500 border border-red-500/30',
  };
  return styles[action || ''] || 'bg-gray-500/20 text-gray-500 border border-gray-500/30';
};

// 空值占位符
const Placeholder = ({ text = '-' }: { text?: string }) => (
  <span className="text-muted-text/50">{text}</span>
);

export const InvestmentConclusionView: React.FC<InvestmentConclusionViewProps> = ({ data }) => {
  // 空数据检查
  const hasData = useMemo(() => data && (
    data.prior_p !== undefined ||
    data.edge !== undefined ||
    data.action
  ), [data]);

  if (!hasData) {
    return (
      <div className="rounded-lg border border-dashed border-subtle p-4 text-center">
        <p className="text-sm text-muted-text">暂无投资结论</p>
        <p className="text-xs text-muted-text/50 mt-1">
          启用长线投研框架后可查看
        </p>
      </div>
    );
  }

  const {
    prior_p,
    edge,
    position,
    value_range_1y,
    value_range_3y,
    value_range_5y,
    rationale,
    action = '观察',
  } = data || {};

  return (
    <div className="space-y-4">
      {/* 核心数据行 */}
      <div className="flex flex-wrap items-center gap-4">
        {/* 先验概率 */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-text">先验 P(H):</span>
          <span className="font-medium">
            {prior_p !== undefined ? (
              `${(prior_p * 100).toFixed(1)}%`
            ) : (
              <Placeholder text="-" />
            )}
          </span>
        </div>

        {/* Edge值 - 带颜色标识 */}
        <div 
          className={`flex items-center gap-2 px-3 py-1 rounded-lg ${getEdgeBgColor(edge)}`}
        >
          <span className="text-sm text-muted-text">Edge:</span>
          <span className={`font-medium font-mono ${getEdgeColor(edge)}`}>
            {edge !== undefined ? (
              `${edge >= 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`
            ) : (
              <Placeholder text="-" />
            )}
          </span>
        </div>

        {/* 操作动作 */}
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${getActionBadgeStyles(action)}`}>
          {action || '观察'}
        </span>

        {/* 仓位建议 */}
        {position && (
          <span className="text-sm text-muted-text">
            建议仓位: <span className="font-medium">{position}</span>
          </span>
        )}
      </div>

      {/* 价值区间 */}
      <div className="grid grid-cols-3 gap-2">
        <ValueRangeCard
          label="1年"
          value={value_range_1y}
        />
        <ValueRangeCard
          label="3年"
          value={value_range_3y}
        />
        <ValueRangeCard
          label="5年"
          value={value_range_5y}
        />
      </div>

      {/* 理由 */}
      {rationale && (
        <div className="rounded-lg bg-muted/5 p-3">
          <p className="text-sm text-muted-text leading-relaxed">
            {rationale}
          </p>
        </div>
      )}
    </div>
  );
};

// 价值区间卡片组件
const ValueRangeCard: React.FC<{
  label: string;
  value?: string;
}> = ({ label, value }) => (
  <div className="rounded-lg bg-muted/5 p-3 text-center">
    <div className="text-xs text-muted-text mb-1">{label}</div>
    <div className="font-medium text-sm">
      {value || <Placeholder text="待评估" />}
    </div>
  </div>
);

export default InvestmentConclusionView;
```

---

## 四、Schema 设计

### 4.1 贝叶斯框架 Schema (`src/schemas/bayesian_framework.py`)

```python
# -*- coding: utf-8 -*-
"""
贝叶斯概率框架 Schema

定义贝叶斯计算相关的数据结构
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator

class EvidenceItem(BaseModel):
    """证据项"""
    evidence: str = Field(..., description="证据内容")
    strength: Literal["strong_positive", "weak_positive", "neutral", 
                      "weak_negative", "strong_negative"] = Field(
        ..., description="证据强度"
    )
    lr: float = Field(..., ge=0, description="似然比")
    posterior_p: float = Field(..., ge=0, le=1, description="更新后后验概率")
    date: str = Field(..., description="证据日期 (ISO格式)")
    
    @field_validator('lr')
    @classmethod
    def validate_lr(cls, v):
        if v <= 0:
            raise ValueError(f"LR must be > 0, got {v}")
        return v

class StopConditions(BaseModel):
    """止损条件"""
    posterior_below_prior_threshold: bool = Field(
        False, description="后验跌破先验×60%阈值"
    )
    strong_negative_evidence: bool = Field(
        False, description="强反面证据出现"
    )
    edge_disappeared: bool = Field(
        False, description="认知差消失"
    )
    concentration_warning: Optional[str] = Field(
        None, description="集中度警告信息"
    )
    should_stop: bool = Field(
        False, description="综合判断是否应止损"
    )

class BayesianFramework(BaseModel):
    """贝叶斯概率框架"""
    prior_p: float = Field(
        ..., ge=0, le=1, description="先验概率 P(H)"
    )
    market_implied_p: float = Field(
        ..., ge=0, le=1, description="市场隐含概率"
    )
    edge: float = Field(
        ..., ge=-1, le=1, description="Edge = 先验 - 市场隐含"
    )
    posterior_p: float = Field(
        ..., ge=0, le=1, description="后验概率 P(H|E)"
    )
    position_suggestion: str = Field(
        ..., description="仓位建议 (如 '3-5%')"
    )
    confidence: Literal["高", "中", "低", "观察"] = Field(
        "观察", description="信心等级"
    )
    evidence_log: List[EvidenceItem] = Field(
        default_factory=list, description="证据序列"
    )
    stop_conditions: Optional[StopConditions] = Field(
        None, description="止损条件"
    )
    
    @field_validator('edge')
    @classmethod
    def validate_edge(cls, v, info):
        # 确保 edge = prior_p - market_implied_p 逻辑一致
        # 允许小误差 (浮点精度)
        return round(v, 6)
```

### 4.2 其他 Schema

```python
# src/schemas/research_framework.py

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class IndicatorScore(BaseModel):
    """单个指标评分"""
    name: str = Field(..., description="指标名称")
    score: float = Field(..., ge=0, le=100, description="评分 0-100")
    weight: float = Field(..., ge=0, le=1, description="维度内权重")
    basis: Literal["rule", "llm"] = Field("rule", description="评分依据")
    confidence: Optional[Literal["high", "medium", "low"]] = Field(
        None, description="数据可信度"
    )
    summary: Optional[str] = Field(None, description="评分理由")

class DimensionScore(BaseModel):
    """单个维度评分"""
    dimension: str = Field(..., description="维度名称")
    weight: float = Field(..., ge=0, le=1, description="权重")
    score: float = Field(..., ge=0, le=100, description="维度得分")
    indicators: List[IndicatorScore] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list, description="警告信息")

class ResearchFramework(BaseModel):
    """六维投研框架"""
    dimension_total: float = Field(..., ge=0, le=100, description="六维总分")
    dimensions: List[DimensionScore] = Field(default_factory=list)
    scoring_version: str = Field("v1", description="评分版本")
    warnings: List[str] = Field(default_factory=list)


# src/schemas/supply_chain.py

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class ChainNode(BaseModel):
    """产业链节点"""
    level: str = Field(..., description="层级")
    companies: List[str] = Field(default_factory=list)
    concentration: Optional[str] = Field(None)

class Chokepoint(BaseModel):
    """瓶颈点"""
    type: Literal["patent", "capacity", "geo", "tech", "cert"] = Field(...)
    description: str = Field(...)
    confidence: Literal["high", "medium", "low"] = Field("medium")

class USChinaChain(BaseModel):
    """中美双链"""
    role: str = Field(..., description="角色")
    substitution_progress: Optional[str] = Field(None)
    sanction_risk: Optional[str] = Field(None)
    dual_chain_impact: Optional[str] = Field(None)

class SupplyChain(BaseModel):
    """产业链分析"""
    chain_map: List[ChainNode] = Field(default_factory=list)
    chokepoints: List[Chokepoint] = Field(default_factory=list)
    company_position: str = Field(...)
    upstream: List[str] = Field(default_factory=list)
    downstream: List[str] = Field(default_factory=list)
    bargaining_power: Optional[str] = Field(None)
    us_china_chain: Optional[USChinaChain] = Field(None)


# src/schemas/value_scenarios.py

from typing import List, Optional
from pydantic import BaseModel, Field

class Scenario(BaseModel):
    """情景"""
    type: Literal["optimistic", "neutral", "pessimistic"] = Field(...)
    probability: float = Field(..., ge=0, le=1)
    value_anchor: Optional[float] = Field(None)
    description: Optional[str] = Field(None)

class ValueHorizons(BaseModel):
    """价值区间"""
    horizon_1y: Optional[str] = Field(None)
    horizon_3y: Optional[str] = Field(None)
    horizon_5y: Optional[str] = Field(None)

class ValueScenarios(BaseModel):
    """长期价值与情景"""
    industry_space: Optional[str] = Field(None)
    competitive_evolution: Optional[str] = Field(None)
    scenarios: List[Scenario] = Field(default_factory=list)
    horizons: Optional[ValueHorizons] = Field(None)
    catalysts: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


# src/schemas/investment_conclusion.py

from typing import Optional
from pydantic import BaseModel, Field

class InvestmentConclusion(BaseModel):
    """投资结论"""
    prior_p: Optional[float] = Field(None, ge=0, le=1)
    market_implied_p: Optional[float] = Field(None, ge=0, le=1)
    edge: Optional[float] = Field(None, ge=-1, le=1)
    position: str = Field("观察", description="仓位建议")
    value_range_1y: Optional[str] = Field(None)
    value_range_3y: Optional[str] = Field(None)
    value_range_5y: Optional[str] = Field(None)
    rationale: Optional[str] = Field(None)
    action: Literal["建仓", "加仓", "持有", "减仓", "止损", "观察"] = Field("观察")
```

---

## 五、API 设计

### 5.1 新增端点

| 端点 | 方法 | 用途 | 阶段 |
|------|------|------|------|
| `/api/v1/positions` | GET | 查询持仓台账 | P1 |
| `/api/v1/positions` | POST | 创建持仓记录 | P1 |
| `/api/v1/positions/{id}` | PATCH | 更新持仓状态 | P1 |
| `/api/v1/positions/concentration` | GET | 获取赛道集中度 | P2 |
| `/api/v1/beliefs/{stock_code}` | GET | 查询概率演化历史 | P2 |
| `/api/v1/research/validate` | POST | 验证仓位（含集中度） | P1 |

### 5.2 API Schema

```python
# api/v1/schemas/research.py

from typing import List, Optional
from pydantic import BaseModel, Field

class PositionCreateRequest(BaseModel):
    """创建持仓记录"""
    report_id: Optional[int] = None
    stock_code: str
    market: Optional[str] = None
    action: str
    position_size: Optional[str] = None
    prior_p: Optional[float] = None
    edge: Optional[float] = None
    posterior_p: Optional[float] = None
    value_anchor_1y: Optional[str] = None
    value_anchor_3y: Optional[str] = None
    value_anchor_5y: Optional[str] = None
    rationale: Optional[str] = None

class PositionUpdateRequest(BaseModel):
    """更新持仓状态"""
    status: Optional[str] = None
    realized_pnl: Optional[float] = None

class PositionResponse(BaseModel):
    """持仓记录响应"""
    id: int
    stock_code: str
    action: str
    status: str
    prior_p: Optional[float]
    edge: Optional[float]
    position_size: Optional[str]
    created_at: str

class PositionListResponse(BaseModel):
    """持仓列表响应"""
    items: List[PositionResponse]
    total: int
    open_count: int

class ConcentrationResponse(BaseModel):
    """集中度响应"""
    sectors: dict[str, float]  # 赛道 -> 集中度
    max_concentration: float
    warnings: List[str]

class ValidatePositionRequest(BaseModel):
    """验证仓位请求"""
    suggested_position: str
    stock_code: str

class ValidatePositionResponse(BaseModel):
    """验证仓位响应"""
    valid: bool
    adjusted_position: Optional[str]
    warning: Optional[str]
```

---

## 六、Feature Flag 配置

```bash
# .env.example 新增

# 长线投研框架开关
RESEARCH_FRAMEWORK_ENABLED=true

# 贝叶斯框架开关
BAYESIAN_FRAMEWORK_ENABLED=true

# 产业链数据开关
SUPPLY_CHAIN_DATA_ENABLED=false

# 多Agent开关
MULTI_AGENT_ENABLED=false
```

---

## 七、测试策略

### 7.1 贝叶斯引擎测试 (`tests/test_scoring/test_bayesian.py`)

```python
import pytest
from src.scoring.bayesian import (
    map_prior, calculate_edge, update_posterior,
    map_position, check_stop_conditions, calculate_bayesian,
    odds, probability, _clamp
)

class TestMapPrior:
    """先验映射测试"""
    
    def test_extreme_bottleneck(self):
        """极端瓶颈: 总分90 → P(H)约0.93"""
        result = map_prior(90)
        assert 0.90 <= result <= 1.0
    
    def test_strong_bottleneck(self):
        """强瓶颈: 总分75 → P(H)约0.67"""
        result = map_prior(75)
        assert 0.60 <= result <= 0.80
    
    def test_medium(self):
        """中等: 总分60 → P(H)约0.47"""
        result = map_prior(60)
        assert 0.40 <= result <= 0.60
    
    def test_weak(self):
        """弱: 总分45 → P(H)约0.27"""
        result = map_prior(45)
        assert 0.20 <= result <= 0.40
    
    def test_non_bottleneck(self):
        """非瓶颈: 总分20 → P(H)约0.10"""
        result = map_prior(20)
        assert 0.0 <= result <= 0.20
    
    def test_boundary_100(self):
        """边界: 总分100 → P(H)=1.0 (不超限)"""
        result = map_prior(100)
        assert result == 1.0
    
    def test_boundary_0(self):
        """边界: 总分0 → P(H)=0"""
        result = map_prior(0)
        assert result == 0.0
    
    def test_float_precision(self):
        """浮点精度: 连续性"""
        p85 = map_prior(85)
        p85_1 = map_prior(85.1)
        assert abs(p85_1 - p85) < 0.02  # 相邻值差异小

class TestOddsProbability:
    """赔率/概率转换测试"""
    
    def test_odds_roundtrip(self):
        """往返一致性"""
        original = 0.6
        o = odds(original)
        p = probability(o)
        assert abs(p - original) < 1e-10
    
    def test_zero_probability(self):
        """P=0 → O=0"""
        assert odds(0) == 0
    
    def test_one_probability_error(self):
        """P=1 抛出异常"""
        with pytest.raises(ValueError):
            odds(1)
    
    def test_infinite_odds(self):
        """O=∞ → P=1"""
        assert probability(float('inf')) == 1.0

class TestUpdatePosterior:
    """后验更新测试"""
    
    def test_strong_positive_evidence(self):
        """强正面: 先验0.6 + LR=8 → 后验约0.92"""
        prior = 0.6
        lr = 8.0
        posterior = update_posterior(prior, lr)
        assert 0.90 <= posterior <= 0.95
    
    def test_strong_negative_evidence(self):
        """强反面: 先验0.6 + LR=0.125 → 后验约0.16"""
        prior = 0.6
        lr = 0.125
        posterior = update_posterior(prior, lr)
        assert 0.14 <= posterior <= 0.18
    
    def test_neutral_evidence(self):
        """中性: 先验不变"""
        prior = 0.6
        posterior = update_posterior(prior, 1.0)
        assert abs(posterior - prior) < 1e-10
    
    def test_lr_zero_error(self):
        """LR=0 抛出异常"""
        with pytest.raises(ValueError):
            update_posterior(0.5, 0)

class TestEdge:
    """Edge计算测试"""
    
    def test_positive_edge(self):
        assert calculate_edge(0.7, 0.5) == 0.2
    
    def test_negative_edge(self):
        assert calculate_edge(0.3, 0.6) == -0.3
    
    def test_zero_edge(self):
        assert calculate_edge(0.5, 0.5) == 0.0

class TestPosition:
    """仓位映射测试"""
    
    @pytest.mark.parametrize("edge,expected", [
        (0.55, ("5-8%", "高")),
        (0.40, ("3-5%", "中")),
        (0.20, ("1-3%", "低")),
        (0.05, ("0-1%", "观察")),
        (-0.20, ("0-1%", "观察")),
    ])
    def test_position_mapping(self, edge, expected):
        assert map_position(edge) == expected

class TestStopConditions:
    """止损条件测试"""
    
    def test_posterior_below_threshold(self):
        """后验跌破先验60%"""
        result = check_stop_conditions(0.6, 0.3, 0.5)
        assert result["posterior_below_prior_threshold"] is True
        assert result["should_stop"] is True
    
    def test_strong_negative(self):
        """强反面证据"""
        result = check_stop_conditions(0.6, 0.5, 0.4, strong_negative_evidence=True)
        assert result["strong_negative_evidence"] is True
        assert result["should_stop"] is True
    
    def test_edge_disappeared(self):
        """认知差消失"""
        result = check_stop_conditions(0.6, 0.5, 0.7)
        assert result["edge_disappeared"] is True
        assert result["should_stop"] is True
    
    def test_no_stop(self):
        """无止损信号"""
        result = check_stop_conditions(0.6, 0.55, 0.4)
        assert result["should_stop"] is False

class TestCalculateBayesian:
    """完整贝叶斯计算测试"""
    
    def test_full_calculation(self):
        """完整流程"""
        result = calculate_bayesian(
            dimension_total=75,
            market_implied_p=0.4,
            lr=5.0,
            strong_negative_evidence=False,
            current_concentration=0.1
        )
        
        assert 0.6 <= result.prior_p <= 0.8
        assert result.edge > 0.2  # 正向Edge
        assert 0.6 <= result.posterior_p <= 1.0
        assert result.position_suggestion in ["3-5%", "5-8%"]
        assert result.stop_conditions["should_stop"] is False
```

### 7.2 六维引擎测试

```python
# tests/test_scoring/test_engine.py

import pytest
from src.scoring.engine import (
    validate_weights, validate_weights_safe,
    aggregate_framework, aggregate_dimension,
    DEFAULT_NEUTRAL_SCORE
)

class TestValidateWeights:
    """权重校验测试"""
    
    def test_valid_weights(self):
        """合法权重和1.0"""
        validate_weights([0.25, 0.25, 0.15, 0.10, 0.15, 0.10])  # 不抛异常
    
    def test_invalid_weights(self):
        """非法权重和"""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_weights([0.3, 0.3, 0.15, 0.10, 0.10, 0.10])
    
    def test_safe_validation_valid(self):
        """安全校验-合法"""
        valid, error = validate_weights_safe([0.5, 0.5])
        assert valid is True
        assert error is None
    
    def test_safe_validation_invalid(self):
        """安全校验-非法"""
        valid, error = validate_weights_safe([0.3, 0.3])
        assert valid is False
        assert "must sum to 1.0" in error

class TestAggregateFramework:
    """框架聚合测试"""
    
    def test_basic_aggregation(self):
        """基本聚合"""
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)
        assert result.dimension_total == 70.0
    
    def test_missing_score_uses_neutral(self):
        """缺失分数使用中性分"""
        dimensions = [
            {"dimension": "A", "weight": 0.5, "score": 80},
            {"dimension": "B", "weight": 0.5},  # 缺失
        ]
        result = aggregate_framework(dimensions)
        assert result.dimension_total == 65.0  # (80+50)/2
        assert "数据缺失" in result.warnings[0]
    
    def test_with_indicators(self):
        """带指标列表"""
        dimensions = [
            {
                "dimension": "A",
                "weight": 0.5,
                "indicators": [
                    {"name": "a1", "score": 80, "weight": 0.6},
                    {"name": "a2", "score": 70, "weight": 0.4},
                ]
            },
            {"dimension": "B", "weight": 0.5, "score": 60},
        ]
        result = aggregate_framework(dimensions)
        # A维度: 80*0.6 + 70*0.4 = 76
        assert result.dimensions[0].score == 76.0
        # 总分: 76*0.5 + 60*0.5 = 68
        assert result.dimension_total == 68.0
    
    def test_invalid_weights_error(self):
        """非法权重抛出异常"""
        dimensions = [
            {"dimension": "A", "weight": 0.7, "score": 80},
            {"dimension": "B", "weight": 0.2, "score": 60},
        ]
        with pytest.raises(ValueError):
            aggregate_framework(dimensions)
```

---

## 八、实施计划

### 8.1 P1 阶段 (基础框架)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| Schema 定义 | 0.5d | 5个Schema + 验证 |
| 贝叶斯引擎 | 1d | 纯函数 + 100%测试 |
| 六维引擎 | 1d | 纯函数 + 100%测试 |
| 客观评分规则 | 1d | 3个维度规则 |
| 台账表 + Repo | 1d | CRUD + 索引 |
| 编排服务 | 0.5d | 集成到报告生成 |
| API端点 | 0.5d | 持仓CRUD + 验证 |
| 回归测试 | 0.5d | 旧报告兼容 |
| 文档 | 0.5d | CHANGELOG + .env.example |

**P1 交付**: 报告有先验/Edge/仓位，数据开始记录

### 8.2 P2 阶段 (产业链数据)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 产业链数据源 | 1d | akshare概念板块 |
| 机构持仓数据 | 1d | 基金/QFII |
| 北向/融资 | 1d | 沪深港通 |
| 产业链Prompt | 1d | ②段内容 |
| 主观评分 | 1d | 3维度LLM评分 |
| 前端展示 | 1d | ②段UI |

**P2 交付**: 产业链维度充实

### 8.3 P3 阶段 (多Agent)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| supply_chain_agent | 1d | 专职产业链Agent |
| value_agent | 1d | 专职价值Agent |
| 价值情景Prompt | 0.5d | ③段内容 |
| 五段完整集成 | 1d | Prompt + 编排 |
| 前端五段UI | 1d | 完整五段 |

**P3 交付**: 五段完整

---

## 九、审计问题修复清单

| 问题编号 | 描述 | 修复状态 |
|----------|------|----------|
| B1 | 浮点数边界clamp | ✅ 已修复 (`_clamp`函数) |
| B3 | 权重校验缺失 | ✅ 已修复 (`validate_weights`) |
| B4 | 空值处理缺失 | ✅ 已修复 (`fill_missing_score`) |
| C2 | 台账表索引缺失 | ✅ 已修复 (复合索引) |
| C3 | 外键关联校验 | ✅ 已修复 (ondelete='CASCADE') |
| D3 | 旧报告UI兼容 | ✅ 已修复 (hasData检查) |
| D4 | Edge负值处理 | ✅ 已修复 (颜色映射) |
| E1 | 组合集中度校验 | ✅ 已新增 (`validate_position_with_concentration`) |
| E2 | API端点设计 | ✅ 已新增 (5个端点) |

---

## 十、回滚方案

关闭 Feature Flag 等价完全回滚：

```bash
RESEARCH_FRAMEWORK_ENABLED=false
BAYESIAN_FRAMEWORK_ENABLED=false
```

新表空表不影响现有查询，无破坏性变更。
