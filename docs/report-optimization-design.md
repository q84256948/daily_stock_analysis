# 个股分析报告优化设计（长线产业链投研 + 贝叶斯框架）

> 状态：方案已大调整为长线产业链方向，待实现
> 决策日期：2026-06
> 语言：中文（英文版按需后续同步）
> 方法论参考：[bayesian-supply-chain-investment-research](https://github.com/cc232421/skill-center/tree/main/skills/bayesian-supply-chain-investment-research)（Serenity 方法论 + 贝叶斯）
> 关联模块：`src/analyzer.py`、`src/core/pipeline.py`、`src/agent/`、`src/schemas/`、`data_provider/`、`src/scoring/`（新增）

本文档是个股分析报告内容结构优化的设计真源。实际实现时，每阶段需同步更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 段（扁平格式）与本文件。

> **方向变更说明**：本方案经历一次根本性转向——从「中短线趋势交易（盘中阶段、止损止盈、乖离率）」转向「长线产业链/供应链投研 + 贝叶斯概率框架」。原有「六维线性加权评分」不再作为顶层决策，而是降级为**贝叶斯先验 P(H) 的可解释分解**。

---

## 1. 概述

### 1.1 背景

当前个股分析报告输出统一的「决策仪表盘 JSON」，本质是**短线/趋势交易导向**：盘中阶段决策（`phase_decision`）、狙击点位、止损止盈、乖离率、MA 多头排列。该形态不适合长线产业链投研。

参考 Serenity 投资方法论 + 贝叶斯框架，将报告升级为**长线产业链/供应链投研**：从「今天买还是卖」转向「这家公司是产业链瓶颈/长期赢家吗？市场错判了多少（Edge）？」。

### 1.2 核心理念（对齐 skill）

1. **概率而非信念**：决策基于 `P(H|E) = P(E|H)·P(H)/P(E)`，不是主观打分或看图。
2. **结构锚定先验**：先验 `P(H)` 由产业链物理现实（供应链地图、瓶颈点、产能集中度、替代周期）构建。
3. **认知差 Edge 下注**：`Edge = P(H) − 市场隐含概率`，正 Edge 才值得长线持有。
4. **后验更新 + 轮动**：新证据用似然比持续更新，资金轮动到后验最高的瓶颈点。

### 1.3 目标

五段式长线投研报告：

| 段落 | 内容 |
|------|------|
| ① 投资结论 | 先验 P(H)、产业链定位结论、Edge、长线仓位建议、1/3/5 年价值区间、建仓/加仓记录 |
| ② 产业链解读 | 产业链地图、公司定位、瓶颈点分析、上下游关系、中美双链位置、产业驱动根因 |
| ③ 长期价值与情景 | 产业长期空间、竞争演变、乐观/中性/悲观情景概率、1/3/5 年价值锚、催化与风险 |
| ④ 贝叶斯评分表 | 六维 × 指标 × 权重 × 打分 → 先验 P(H)；市场隐含 → Edge；证据序列 → 后验；仓位 |
| ⑤ 六维详情 | 六维每个细分指标的详细分析 + 证据来源（标注可信度） |

### 1.4 范围

- **P1**：贝叶斯引擎（纯函数）+ 六维评分引擎（纯函数，作先验分解）+ schema 追加 + 自反思台账 + 测试。
- **P2–P4**：产业链数据接入（akshare 概念板块/机构持仓）、中美链、长线价值情景、多 agent、T+N 回测闭环。

---

## 2. 范式转变（短线 → 长线）

| 维度 | 旧（短线趋势） | 新（长线产业链 + 贝叶斯） |
|---|---|---|
| 核心问题 | 今天买还是卖？什么价位？ | 是产业链瓶颈/长期赢家吗？市场错判多少（Edge）？ |
| 决策本质 | 六维线性加权 0-100 | 先验 P(H) + Edge + 后验更新（概率框架） |
| 技术面权重 | 25%（最高之一） | **10%**（降为长线择时买点辅助） |
| 时间维度 | 1天/1周/1月/1季 + 盘中阶段 | 1年/3年/5年价值锚 + 产业周期 |
| 决策输出 | 买卖点位 + 短线止损止盈 | 产业链定位 + Edge + 长线仓位（建仓/加仓/减仓） |
| 止损逻辑 | 跌破技术位 | 后验 P(H|E) < 先验·60% / 强反面证据 / 认知差消失 |
| 新增核心 | — | 产业链定位、瓶颈点、中美平行链、认知差 Edge |

---

## 3. 设计原则与约束

遵循 `AGENTS.md` 与全局编码规则：

| 原则 | 落地 |
|------|------|
| KISS、代码整洁 | 贝叶斯与评分引擎为纯函数模块；新报告段落为追加字段；新数据走现有 fetcher 模式 |
| 高内聚低耦合 | 贝叶斯/评分/产业链/台账各自独立模块；多 agent 下新维度=新专职 agent |
| 100% 测试 | 贝叶斯更新/评分=纯函数；schema=Pydantic；新 fetcher=mock（不联网）；旧报告=兼容回归 |
| 不影响无关功能 | 只追加字段不改语义；新表独立；新 fetcher 独立；前端旧渲染不变 |
| 稳定性优先 | 默认「不配置也可运行」；Feature flag 渐进开关 |

---

## 4. 关键决策（已确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 报告形态 | **向后兼容增强** | 追加新字段，保留所有旧字段，Web/通知/历史/决策信号零改动 |
| 短/长线 | **长线为主 + 技术面择时** | 产业链/基本面/价值为核心选股，技术面降权到 10% 作长线买点择时，弱化盘中/短线止损（改为长线逻辑） |
| 贝叶斯框架 | **顶层，六维作先验分解** | 先验 P(H) 由六维映射，Edge=先验−市场隐含，六维解释「为什么这个概率」，一个统一可回测体系 |
| 中美平行链 | **贯穿产业链 + 宏观维度** | 作为「产业链定位」和「宏观地缘」维度核心子指标（国产替代/制裁风险/双链位置），不单列，保持六维结构 |
| 自反思范围 | **记录 + 预留回测** | 本次做持仓台账 + 概率证据台账，T+N 回测调度为下一阶段 |

---

## 5. 报告数据契约设计（向后兼容）

### 5.1 兼容策略

在现有 `AnalysisReportSchema`（`src/schemas/report_schema.py`）上**追加顶层字段**，不修改/删除任何现有字段。`sentiment_score` / `dashboard` / `operation_advice` / `decision_type` / `phase_decision` 等全部保留。短线字段保留但**前端逐步弱化展示**，长线字段渐进渲染。

### 5.2 新增字段

| 新字段 | 子字段 | 对应段落 |
|--------|--------|----------|
| `research_framework` | `dimensions[]`、`dimension_total`(0-100) | ④ 六维评分（先验分解） |
| `bayesian_framework` | `prior_p`、`market_implied_p`、`edge`、`posterior_p`、`position_suggestion`、`evidence_log[]`、`stop_conditions` | ①④ 贝叶斯顶层 |
| `supply_chain` | `chain_map[]`、`chokepoints[]`、`company_position`、`us_china_chain{role, substitution_progress, sanction_risk, dual_chain}` | ② 产业链解读 |
| `value_scenarios` | `industry_space`、`competitive_evolution`、`scenarios[]`、`horizons{1y,3y,5y}`、`catalysts[]`、`risks[]` | ③ 长期价值与情景 |
| `investment_conclusion` | `prior_p`、`edge`、`position`、`value_range{1y,3y,5y}`、`action`(建仓/加仓/减仓/止损/观察)、`rationale` | ① 投资结论（台账来源） |

**并存**：`sentiment_score`（旧 LLM 主观）与 `bayesian_framework.prior_p`（新产业链锚定概率）并存；`operation_advice`（旧短线建议）与 `investment_conclusion.action`（新长线动作）并存。

`indicators[].basis` = `"rule" | "llm"`，另增 `data_confidence`（高/中/低）标记产业链等 LLM 驱动指标的可信度。

---

## 6. 六维评分框架（产业链导向，作先验分解）

### 6.1 维度与权重（v1，长线口径）

| 维度 | 权重 | 核心问题 | 细分指标 |
|------|------|----------|----------|
| **产业链定位** ⭐ | 25% | 是瓶颈/赢家吗？ | 产业链位置 · 瓶颈属性（专利/产能 CR3/替代周期/认证） · 上下游议价力 · **中美双链位置**（国产替代进度/出口受限） |
| **基本面与价值** | 25% | 长期价值与护城河 | 护城河 · 财务健康 · 成长性 · 长线估值（产业周期位置/反向 DCF） |
| **资金面** | 15% | 长线资金在买吗？ | 机构持仓变化 · 北向 · 融资融券 · 筹码集中度 |
| **技术面** | 10% | 长期趋势 + 买点 | 长期趋势结构 · 关键支撑压力（择时辅助） |
| **情绪与认知差** ⭐ | 15% | 市场隐含 vs 真实 | 卖方一致预期 · 研报评级 · 社交情绪（**核心：反推市场隐含概率**） |
| **宏观与地缘** ⭐ | 10% | 政策与中美博弈 | **中美竞争/制裁风险** · 国产替代政策 · 产业周期 · 流动性 |

权重和 = 100%，每维度内指标权重和 = 100%。权重为 v1 初始猜测，是自反思迭代对象。

### 6.2 中美平行竞争链贯穿点

不单列维度，作为以下指标的子项：
- **产业链定位**：`中美双链位置`（公司在中国链/美国链的位置、国产替代进度、出口受限程度）
- **宏观与地缘**：`中美竞争/制裁风险`（出口管制清单、制裁名单、双链脱钩/重连的受益/受损）

### 6.3 客观维度规则映射（确定性，可回测）

| 维度 | 指标 | 输入 → 0-100 分 |
|------|------|-----------------|
| 资金 | 机构持仓变化 | QFII/基金连续增持=85；减持=30；稳定=55 |
| 资金 | 北向资金 | 持续净流入=80；流出=35 |
| 资金 | 筹码集中度 | 90%集中度<10%=85；<15%=70；>25%=40 |
| 基本面 | 估值（PE 分位/反向 DCF） | 历史<20%分位=85（低估）；>80%=35（高估） |
| 技术 | 长期趋势 | 周线/月线多头+上行=80；下行=25；震荡=55 |
| 技术 | 关键位距离 | 接近长线支撑=75；接近压力=40 |

主观维度（产业链瓶颈属性、护城河、卖方一致预期反推、中美链判断、社交情绪）由 LLM 给分 + 一句话理由，`basis="llm"`。缺失数据 → 中性分 50 + `summary="数据缺失"`，不抛异常。

### 6.4 评分引擎架构（纯函数）

```
src/scoring/
├── __init__.py            # 公开接口
├── contracts.py           # IndicatorInput / IndicatorResult / DimensionScore / FrameworkScore
├── weights.py             # 权重表 + 版本管理（启动校验和=1.0）
├── engine.py              # 六维加权聚合（纯函数）
├── bayesian.py            # 贝叶斯：先验映射 / Edge / 后验更新 / 仓位 / 止损（纯函数）⭐新增
├── normalization.py       # 归一化 / clamp
└── indicators/            # 各维度算分（客观=规则，主观=LLM 输入）
    ├── supply_chain.py    # 产业链定位（多为 LLM 输入）
    ├── fundamental.py     # 估值=规则；护城河/成长=LLM
    ├── capital.py         # 规则：机构/北向/融资/筹码
    ├── technical.py       # 规则：长期趋势/关键位（择时辅助）
    ├── sentiment.py       # 研报=规则聚合；社交=LLM；反推市场隐含
    └── macro.py           # 流动性=规则；中美链/政策=LLM
```

**核心约束**：`src/scoring/` 纯函数，不依赖 LLM/网络/DB。相同输入→相同输出。

---

## 7. 贝叶斯概率框架（顶层）⭐

### 7.1 核心公式

```
P(H|E) = P(E|H) × P(H) / P(E)

赔率形式（实用，纯函数易实现）：
O(H|E) = O(H) × LR       其中 O(H)=P(H)/(1−P(H)),  LR=P(E|H)/P(E|¬H)
P(H|E) = O(H|E) / (1 + O(H|E))
```

`P(H)` 语义：公司成为产业链长期赢家 / 关键瓶颈的概率。

### 7.2 先验 P(H) 构建（六维 → P(H) 映射，纯函数）

六维加权总分（0-100）→ 先验 P(H)（0-1）分段映射，对齐 skill 的瓶颈分级：

| 六维总分 | 先验 P(H) | 含义（对齐 skill） |
|----------|-----------|--------------------|
| ≥85 | 0.8–1.0 | 极端瓶颈/长期赢家（单一来源、专利锁定） |
| 70–85 | 0.6–0.8 | 强瓶颈（CR3>70%、高资本开支） |
| 55–70 | 0.4–0.6 | 中等（存在替代但成本高） |
| 40–55 | 0.2–0.4 | 弱（竞争分散） |
| <40 | 0.0–0.2 | 非瓶颈/商品化 |

该映射为纯函数 `map_prior(dimension_total) -> float`，可 100% 测试。

### 7.3 市场隐含概率与 Edge

- **市场隐含概率**：由估值（PE 分位/反向 DCF）+ 卖方一致预期 + 股价表现反推；半规则 + LLM 辅助，`basis` 标注。
- **Edge** = `prior_p − market_implied_p`（纯函数）。

### 7.4 后验更新（似然比，纯函数）

证据分类 → 似然比 LR（对齐 skill 速查表）：

| 证据强度 | LR | 典型证据 |
|----------|-----|----------|
| 强正面 | 5–10 | 大客户订单、独家供应协议、竞争者退出、财报超预期且符瓶颈逻辑 |
| 弱正面 | 2–3 | 行业需求向好、小批量订单、管理层正面指引 |
| 中性 | ~1 | 无重大新闻、股价技术性波动 |
| 弱反面 | 0.3–0.5 | 季度略低预期、新竞争者进入、客户分散供应商 |
| 强反面 | 0.1–0.2 | 技术路线颠覆、核心专利无效、主客切换、监管/制裁 |

`update_posterior(prior_p, lr) -> posterior_p`（纯函数，赔率形式），100% 可测。

### 7.5 仓位映射（纯函数，对齐 skill）

| Edge | 建议仓位 | 信心 |
|------|----------|------|
| >50% | 5–8% | 高（核心仓） |
| 30–50% | 3–5% | 中（标准仓） |
| 10–30% | 1–3% | 观察 |
| <10% | 0–1% | 观察为主 |

**约束**：单赛道集中 ≤ 40%（`suggest_position` 需结合组合现有集中度，组合层校验）。

### 7.6 止损规则（长线逻辑，纯函数判定，对齐 skill）

满足任一即触发（区别于短线技术位止损）：
1. 后验 `P(H|E) < prior_p × 0.6`
2. 强反面证据（技术路线颠覆 / 核心专利无效 / 重大制裁）
3. 认知差消失（`market_implied_p ≥ prior_p`）

---

## 8. 产业链与供应链分析框架

### 8.1 供应链地图（下游 → 上游逐层拆解）

```
下游应用 → OEM/系统集成 → 中游制造 → 上游关键组件 → 原材料/设备
```

由 LLM 基于行业知识 + 财报主营业务 + akshare 概念板块构建，输出 `supply_chain.chain_map[]`。

### 8.2 瓶颈点（Chokepoint）识别

对每个链层评估（LLM 驱动，标注 `data_confidence`）：
- **专利垄断**：核心专利壁垒
- **产能集中**：CR3/CR5 市场份额
- **地理风险**：产地区域集中度
- **技术壁垒**：工艺难度、资本开支门槛
- **替代难度**：客户切换成本、认证周期

### 8.3 中美平行竞争链分析

输出 `supply_chain.us_china_chain`：
- `role`：公司在中国链 / 美国链 / 双链节点的位置
- `substitution_progress`：国产替代进度（若在替代链）
- `sanction_risk`：出口管制 / 制裁风险（若依赖美国技术/市场）
- `dual_chain`：脱钩/重连的受益 or 受损判断

### 8.4 数据现实约束（诚实说明）⚠️

| 数据 | 来源 | 可信度 |
|------|------|--------|
| 国产替代/产业链概念分类 | akshare `stock_board_concept_em` | 高（免费 API） |
| 机构持仓 | `stock_report_fund_hold` / `qfiy_hold` | 高 |
| 财报（供应商/客户集中度） | 现有 fundamental | 高 |
| 专利垄断、产能 CR3、BOM | **LLM 知识 + 财报文本**（无免费实时 API） | 中 |
| 出口管制清单、制裁名单 | **LLM 知识 + 新闻**（无稳定免费源） | 中低 |

**结论**：产业链维度高度依赖 LLM（主观），客观规则算分主要落在资金/技术指标/估值。每个指标标注 `basis` 与 `data_confidence`，回测时按可信度分组分析。

---

## 9. 报告五段（长线版）

| 段 | 字段 | 内容 |
|---|---|---|
| ① 投资结论 | `investment_conclusion` + `bayesian_framework` | 先验 P(H)、产业链定位一句话、Edge、长线仓位、1/3/5 年价值区间、动作（建仓/加仓/减仓/止损/观察）、理由 |
| ② 产业链解读 | `supply_chain` | 供应链地图、公司定位、瓶颈点矩阵、上下游议价、中美双链位置、产业驱动根因（趋势/政策/技术变革） |
| ③ 长期价值与情景 | `value_scenarios` | 产业长期空间、竞争格局演变、乐观/中性/悲观情景（概率+价值锚）、1/3/5 年价值、催化与风险事件 |
| ④ 贝叶斯评分表 | `research_framework` + `bayesian_framework` | 六维 × 指标 × 权重 × 打分 → 先验 P(H)；市场隐含 → Edge；证据序列 → 后验；仓位 |
| ⑤ 六维详情 | `dimensions[].indicators[].detail` | 每个细分指标详细分析 + 证据来源 + 可信度 |

---

## 10. 自反思记录系统

### 10.1 三张台账（独立新表）

**`position_ledger`（长线持仓台账）**

| 字段 | 说明 |
|------|------|
| `id`, `report_id`, `stock_code`, `market` | 关联 |
| `action` | 建仓/加仓/减仓/止损/观察 |
| `prior_p`, `edge`, `position_size` | 决策时概率与仓位 |
| `value_anchor_1y/3y/5y` | 价值锚 |
| `created_at`, `status`(open/closed/stop_hit) | 状态 |
| `realized_pnl`, `evaluated_at` | 回测填 |

**`belief_ledger`（概率与证据台账）** ⭐ 新增

| 字段 | 说明 |
|------|------|
| `id`, `report_id`, `stock_code` | 关联 |
| `prior_p`, `market_implied_p`, `edge` | 先验/隐含/Edge 快照 |
| `evidence_seq` (JSON) | 证据序列 `[{evidence, strength, lr, posterior_p, date}]` |
| `posterior_p`, `score_version`, `weight_snapshot` | 后验与版本 |
| `created_at`, `future_returns` (JSON) | 回测填 |

**`score_ledger`（六维评分台账，先验分解快照）**

| 字段 | 说明 |
|------|------|
| `id`, `report_id`, `stock_code`, `dimension_total`, `score_version`, `dimension_scores` (JSON), `weight_snapshot` (JSON), `created_at` | 六维快照 |

### 10.2 写入流程

报告生成成功后 best-effort 写入三张台账（失败不阻塞主流程）。走现有 `_ensure_*_columns` 建表模式（不引入 Alembic）。

### 10.3 回测接口（预留，下一阶段）

T+N 调度任务（长线周期：月/季）：
- **先验准确度**：高 P(H) 标的是否真成瓶颈/赢家
- **Edge 实现**：正 Edge 是否跑赢基准
- **事件预测**：产业链事件是否被先验/后验预测
- **复盘指标**：胜率、盈亏比、夏普比率

---

## 11. 新数据维度与数据源

| 维度数据 | 来源 | 现状 |
|----------|------|------|
| 国产替代/产业链概念 | akshare `stock_board_concept_em` | 未接 |
| 机构持仓 | `stock_report_fund_hold` / `qfiy_hold` | 未接 |
| 北向 / 融资融券 | `stock_hsgt_*` / `stock_margin_*` | 未接 |
| 财报供应商/客户集中度 | 现有 fundamental | 已有（待结构化） |
| 专利 / 产能 CR3 / BOM | LLM 知识 + 财报文本 | 无免费 API |
| 出口管制 / 制裁 | LLM 知识 + 新闻 | 无稳定免费源 |

接入策略：免费 API 项封装为新 fetcher 方法或独立 `data_provider/supply_chain/` 模块，走现有注册与熔断；LLM 驱动项在 agent/prompt 内完成，标注可信度。

---

## 12. 提示词与 Agent 改造

### 12.1 经典路径（`src/analyzer.py`）

| 改动点 | 内容 |
|--------|------|
| `SYSTEM_PROMPT` | 追加：产业链分析指令、贝叶斯评分（主观维度给分组件）、长线价值情景、中美链视角。**不动现有 JSON schema 块** |
| `_format_prompt` | 追加产业链/概念板块/机构持仓数据表格（P2 接入后） |
| `_check_content_integrity` | 新增 `bayesian_framework.prior_p` / `research_framework.dimensions` 必填校验 |

经典路径 P1 先行：报告生成后调 `research_scoring_service` → 六维算分 → `bayesian` 模块聚合先验/Edge/后验 → 填字段 → 写台账。

### 12.2 多 agent 路径（`src/agent/`，P3）

新增专职 agent（高内聚）：
- `supply_chain_agent`（产业链地图 + 瓶颈 + 中美链）
- `value_agent`（长线价值 + 情景）

`decision_agent` 聚合 → 输出 `bayesian_framework` + `investment_conclusion`。

---

## 13. 测试策略与测试报告

### 13.1 测试矩阵

| 模块 | 测试方式 | 覆盖目标 |
|------|----------|----------|
| `src/scoring/bayesian.py`（纯函数） | 先验映射 / Edge / 后验更新（似然比）/ 仓位 / 止损 全场景 | **100%** |
| `src/scoring/` 六维引擎（纯函数） | 给定输入→期望分数/加权 | **100%** |
| 权重配置 | 和=100%、版本切换、边界 | 100% |
| `research_framework` / `bayesian_framework` / `supply_chain` schema | Pydantic 校验 | 100% |
| `position_ledger` / `belief_ledger` / `score_ledger` repo | CRUD（mock db） | 100% |
| 新 fetcher 方法 | mock akshare（不联网） | 100%；真实调用标 `@network` |
| 向后兼容 | 旧报告（无新字段）解析/渲染回归 | 不崩 |
| 提示词构造 | prompt 快照：产业链/贝叶斯数据正确拼入 | 100% |

### 13.2 贝叶斯引擎关键测试用例

| 测试 | 断言 |
|------|------|
| `test_map_prior` | 总分 90→P(H)≥0.8；50→0.2–0.4；边界连续性 |
| `test_update_posterior` | 先验 0.6 + LR=8 → 后验≈0.92；LR=0.125 → ≈0.16（对齐 skill 速查表） |
| `test_edge` | prior−implied 正负与边界 |
| `test_position_mapping` | Edge 55%→5–8%；5%→0–1% |
| `test_stop_conditions` | 后验<先验·60%触发；认知差消失触发 |
| `test_odds_conversion` | P↔O 往返一致 |

### 13.3 测试报告产出

```bash
pytest tests/test_scoring tests/test_bayesian tests/test_*_ledger_repo \
  test_research_framework_schema test_bayesian_framework_schema \
  --cov=src/scoring \
  --cov=src/repositories/position_ledger_repo \
  --cov=src/repositories/belief_ledger_repo \
  --cov=src/repositories/score_ledger_repo \
  --cov-fail-under=100 \
  --cov-report=term-missing --cov-report=xml
```

产出 coverage xml + 终端报告，附 PR 描述。

---

## 14. 影响面与兼容性保证

- **现有字段零改动** → Web/通知/历史/决策信号提取不受影响。
- **新表独立** → 不动 `analysis_history` / `decision_signals`。
- **新 fetcher 方法独立** → 不改现有 fetcher。
- **前端渐进** → 后端先给新字段，旧渲染不变，前端逐步弱化短线要素、渲染长线段落。
- **Feature flag** `RESEARCH_FRAMEWORK_ENABLED` / `BAYESIAN_FRAMEWORK_ENABLED`（默认渐进），关闭等价回滚。

---

## 15. 分阶段交付路线图

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P1**（基础） | 贝叶斯引擎（纯函数）+ 六维评分引擎 + schema 追加 + 三台账 + Feature flag + 100% 测试 | 报告有先验/Edge/仓位，数据开始记录 |
| **P2**（产业链数据） | akshare 概念板块/机构持仓/北向/融资接入 + 产业链 LLM 分析 + 中美链 | 产业链维度充实 |
| **P3**（价值与 agent） | 长线价值情景段 + 多 agent（supply_chain/value）+ 提示词 | 五段完整 |
| **P4**（可选） | 社交情绪/专利数据 + T+N 回测闭环（先验准确度/Edge 实现） | 自反思完整闭环 |

**起点为 P1**：贝叶斯 + 评分引擎纯函数，最易 100% 测试、零风险。

### P1 有序实现步骤（TDD）

1. 建 `src/scoring/` 骨架（`contracts` + `weights` + `engine` + `bayesian` + `normalization`），先写测试再实现。
2. 贝叶斯纯函数：`map_prior` / `update_posterior` / `edge` / `position_mapping` / `stop_conditions`（对齐 skill 速查表数值，TDD）。
3. 六维客观维度规则算分（`indicators/capital | fundamental | technical`）。
4. `research_framework` / `bayesian_framework` schema + 校验测试。
5. 三张台账表 + repo（mock 测试）。
6. `research_scoring_service` 编排：接入报告生成，写台账；产业链/价值主观维度 P1 占位，P2/P3 充实。
7. Feature flag + 兼容回归测试。
8. 文档同步：本文件、`docs/CHANGELOG.md` `[Unreleased]`、`.env.example`（新增开关配置）。

---

## 16. 风险与回滚

| 风险 | 应对 |
|------|------|
| 产业链数据缺免费 API，高度依赖 LLM | 客观算分落在资金/技术/估值；产业链标注 `data_confidence`，回测按可信度分组 |
| LLM 生成先验不稳定 | 先验锚定产业链物理现实（地图/瓶颈/CR3），禁止仅凭新闻/社交生成先验 |
| 长线回测周期长 | 先记录，回测分阶段（月/季周期） |
| 报告变长 token 成本 | 评分/贝叶斯用规则（省 token），LLM 只给主观维度 + 综合段 |
| 主观维度 P1 数据不足 | 先占位中性分，P2/P3 充实，不影响 P1 闭环与测试 |

**回滚**：`BAYESIAN_FRAMEWORK_ENABLED=false` → 不生成贝叶斯/产业链字段、不写台账，新表空表不影响现有查询，等价完全回滚。

---

## 17. 禁止事项（对齐 skill 方法论）

- ❌ 不基于新闻或社交情绪生成先验（先验必须锚定产业链物理现实）
- ❌ 无量化概率表（先验/Edge）不给出仓位建议
- ❌ 不忽略反面证据或强行乐观（后验须如实更新）
- ❌ 单一赛道集中 > 40% 仓位
- ❌ 概率 ≠ 确定性（禁止将后验 P(H|E) 表述为「一定会发生」）
- ❌ 长线止损不得用短线技术位（须用后验/认知差逻辑）

---

## 18. 附录：模块结构

```
src/scoring/                       纯函数评分 + 贝叶斯引擎（零外部依赖）
├── contracts.py / weights.py / engine.py / normalization.py
├── bayesian.py                    ⭐ 先验映射/Edge/后验更新/仓位/止损
└── indicators/ (supply_chain, fundamental, capital, technical, sentiment, macro)

src/schemas/
├── research_framework.py          六维评分 schema
├── bayesian_framework.py          ⭐ 贝叶斯 schema
└── supply_chain.py                ⭐ 产业链 schema

src/repositories/
├── position_ledger_repo.py        ⭐ 长线持仓台账
├── belief_ledger_repo.py          ⭐ 概率与证据台账
└── score_ledger_repo.py           六维评分台账

src/services/research_scoring_service.py  编排：六维→先验→Edge→后验→台账

data_provider/supply_chain/        P2: akshare 概念板块/机构持仓
src/agent/agents/supply_chain_agent.py  P3: 产业链 agent
src/agent/agents/value_agent.py         P3: 长线价值 agent
```

依赖方向（单向无环）：

```
report 生成 → research_scoring_service → src/scoring（纯函数：六维 + 贝叶斯）
                                  → repositories（三台账）
                                  → data_provider（取数，P2）
```
