# 个股分析报告优化设计（五段式 + 六维评分 + 自反思）

> 状态：方案已审计并收敛，待实现
> 决策日期：2026-06
> 语言：中文（英文版按需后续同步）
> 关联模块：`src/analyzer.py`、`src/core/pipeline.py`、`src/agent/`、`src/schemas/`、`data_provider/`

本文档是个股分析报告内容结构优化的设计真源。实际实现时，每阶段需同步更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 段（扁平格式）与本文件。

---

## 1. 概述

### 1.1 背景

当前个股分析报告输出统一的「决策仪表盘 JSON」（由 `src/analyzer.py` 的 `SYSTEM_PROMPT` 与 `src/agent/` 的多 agent 提示词定义）。现有报告在技术面、消息面、资金流、筹码维度已有覆盖，但存在三类缺口：

- 缺少**可解释的加权总分**（现有 `sentiment_score` 为 LLM 主观拍定，难以解释权重来源，也难以按维度回测）；
- 缺少**结构化的盘面解读与多时间维度走势预测**；
- 缺少**操作与评分的记录系统**（无法支撑「评分↔未来涨跌」自反思闭环）。

### 1.2 目标

将个股分析报告升级为**五段式结构**，并建立可量化、可记录、可回测的投研评分框架：

| 段落 | 内容 |
|------|------|
| ① 结论 | 总评分（六维加权）、当下买/卖/具体价位、操作建议（每次记录） |
| ② 盘面解读 | 上涨/下跌/震荡结构判定、根因（宏观/微观事件）、影响传导 |
| ③ 走势预测 | 未来重要事件、潜在利好利空、情景概率、1天/1周/1月/1季走势与目标价区间 |
| ④ 六维加权打分表 | 六维度 × 细分指标，每个指标含权重、一句话总结、打分，加权得总分 |
| ⑤ 六维详情 | 六大维度每个细分指标的详细分析 |

### 1.3 范围

- **本次（P1）**：最小六维评分引擎（纯函数）+ 报告 schema 追加 + 复用现有历史/信号链路写入评分快照 + 测试。
- **后续（P2–P4）**：akshare 新数据接口、盘面解读与走势预测段、缠论与社交情绪、T+N 回测闭环。

---

## 2. 现状与差距

| 目标段落 | 现有报告现状 | 缺口 |
|----------|--------------|------|
| ① 结论（总评分+操作+记录） | `core_conclusion` + `battle_plan` + `sentiment_score`（LLM 主观） + `decision_signals` | 无可解释加权总分；评分无快照 |
| ② 盘面解读（结构+根因+传导） | 仅 `trend_prediction`（一句话） | 无结构判定；无根因；无影响传导 |
| ③ 走势预测（事件+情景+多时间维度） | `short/medium_term_outlook`（两档，粗） | 无多时间维度目标价；无情景概率；无事件预案 |
| ④ 六维加权打分表 | 无 | 全新：六维 × 细分指标 × 权重 × 打分 |
| ⑤ 六维详情 | 部分：技术面、消息面、资金流、筹码 | 缺宏观、情绪面、缠论、股权高管、龙虎榜、研报 |
| 自反思（记录+回测） | `analysis_history` + `decision_signals` + `BacktestEngine` | 缺少六维评分快照；缺少评分维度与未来涨跌的统计入口 |

---

## 3. 设计原则与约束

遵循 `AGENTS.md` 与全局编码规则：

| 原则 | 落地 |
|------|------|
| KISS、代码整洁 | 评分引擎为纯函数模块；新报告段落为追加字段；新数据源走现有 fetcher 模式 |
| 高内聚低耦合 | 评分框架独立于报告生成；P1 复用现有历史/信号/回测链路；新数据维度后续再接 |
| 测试聚焦真实风险 | 评分纯函数强覆盖；schema 与持久化覆盖关键兼容路径；旧报告=兼容回归 |
| 不影响无关功能 | 只追加字段不改语义；P1 不新增并行操作台账；前端旧渲染不变 |
| 稳定性优先 | 默认「不配置也可运行」；Feature flag 渐进开关 |

---

## 4. 关键决策（已确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 报告形态 | **向后兼容增强** | 在现有 Dashboard 追加新字段，保留所有旧字段，Web/通知/历史/决策信号零改动，符合兼容性原则，风险最低 |
| 评分方式 | **混合（客观规则 + 主观 LLM）** | 客观维度规则算分（确定性、省 token、可回测），主观维度 LLM 给分；这是自反思能回测优化权重的前提 |
| 自反思范围 | **记录 + 复用现有回测入口** | P1 不新建操作台账；评分快照写入现有报告载荷与 `decision_signals.metadata/evidence`，后续按需要再拆专表 |

---

## 5. 报告数据契约设计

### 5.1 向后兼容策略

在现有 `AnalysisReportSchema`（`src/schemas/report_schema.py`）上**追加顶层字段**，不修改、不删除任何现有字段。现有 `stock_name` / `sentiment_score` / `dashboard` / `operation_advice` / `decision_type` 等全部保留，确保 Web 渲染、通知、历史、决策信号提取零改动。

### 5.2 新增字段

| 新字段 | 子字段 | 对应段落 |
|--------|--------|----------|
| `research_framework` | `total_score`(0-100)、`score_version`、`score_basis`、`dimensions[]` | ④ + ① 总分来源 |
| `dimensions[]` | `name`、`weight`、`score`、`summary`、`indicators[]` | 六维 |
| `indicators[]` | `name`、`weight`、`score`、`summary`、`detail`、`basis` | 细分指标（对应 ⑤ 详情） |
| `market_structure` | `structure`、`root_cause`、`impact_magnitude`、`outlook_impact` | ② 盘面解读 |
| `outlook_forecast` | `horizons{1d,1w,1M,1Q}`、`scenarios[]`、`upcoming_events[]` | ③ 走势预测 |
| `action_plan` | `action`、`entry_zone`、`stop_loss`、`take_profit`、`position_size`、`rationale` | ① 操作（P2+ 可选增强；P1 复用现有 `battle_plan` / `decision_signals`） |

**并存说明**：`sentiment_score`（旧，LLM 主观）与 `research_framework.total_score`（新，加权）并存，前端可逐步切换展示。

`indicators[].basis` 取值 `"rule" | "llm"`，标记该分由规则还是 LLM 给出，回测时可分组分析哪类更准。

---

## 6. 六维评分框架

### 6.1 维度与初始权重（v1）

| 维度 | 权重 | 细分指标（权重） |
|------|------|------------------|
| 宏观 | 15% | 宏观流动性（50%）· 风险偏好（50%） |
| 基本面 | 20% | 大盘板块对比龙头（25%）· 股权高管（15%）· 业务财务健康（35%）· 估值（25%） |
| 资金面 | 20% | 资金流向（40%）· 机构/大户持仓（35%）· 筹码结构（25%） |
| 技术面 | 25% | 缠论结构（40%）· 支撑压力位（30%）· 技术指标（30%） |
| 情绪面 | 10% | 研报平台评价（50%）· 社交情绪（50%） |
| 消息面 | 10% | 真实影响消息（50%）· 未来事件+预案（50%） |

权重和 = 100%，每维度内指标权重和 = 100%。权重为 v1 初始猜测，是自反思迭代的对象，不追求一次完美。

### 6.2 评分引擎架构（纯函数）

```
src/scoring/
├── __init__.py            # 公开接口：compute_framework_score
├── contracts.py           # 数据契约：IndicatorResult / DimensionScore / FrameworkScore
├── weights.py             # 权重表 + 版本管理（纯数据，启动校验权重和=1.0）
├── engine.py              # 加权聚合（纯函数）
├── normalization.py       # 分数归一化 / clamp 工具
└── indicators/            # P2+ 按数据成熟度拆分；P1 可先内聚在少量文件中
    ├── technical.py       # 规则：MACD / RSI / 均线 / 支撑压力
    ├── capital.py         # 规则：资金流 / 筹码 / 机构持仓
    ├── fundamental.py     # 估值=规则；业务财务=LLM 输入
    ├── macro.py           # 流动性=规则；风险偏好=LLM 输入
    ├── sentiment.py       # 研报=规则聚合；社交=LLM 输入
    └── news.py            # LLM 输入
```

**核心约束**：`src/scoring/` 为纯函数模块，不依赖 LLM、不依赖网络、不依赖 DB。相同输入→相同输出，无副作用。这是 100% 覆盖与可回测的根基。

核心函数契约：

```
aggregate_dimension(indicators, weights) -> DimensionScore
compute_framework_score(dimensions, weights) -> FrameworkScore
```

### 6.3 客观维度规则映射（确定性）

| 维度 | 指标 | 输入 → 0-100 分 |
|------|------|-----------------|
| 技术 | 均线排列 | 多头+发散=90；多头粘合=70；缠绕=50；空头=20 |
| 技术 | MACD | 金叉+零轴上=85；金叉零轴下=60；死叉=25 |
| 技术 | RSI | 50-70 健康多头=75；超买>80 降权=55；超卖<20 反弹预期=60 |
| 技术 | 支撑压力距离 | 接近支撑(<2%)=80；接近压力=40；中间=55 |
| 资金 | 主力净流入 | 5日持续净流入=85；流出=25；中性=55 |
| 资金 | 筹码集中度 | 90%集中度<10%=85；<15%=70；>25%=40 |
| 资金 | 获利比 | 30-70%=80；>90%=45；<10%=50 |
| 基本面 | 估值（PE 分位） | 历史<20%分位=85（低估）；>80%=35（高估） |

每条规则是 `indicators/*.py` 中的一个纯函数。**缺失数据 → 返回中性分 50 + `summary="数据缺失"`，不抛异常**（保证报告不崩）。

### 6.4 主观维度 LLM 契约

主观维度（宏观综合 / 业务财务 / 社交情绪 / 消息影响 / 缠论结构）由 LLM 在报告生成时给出 `{score, summary}`，评分引擎只负责**聚合**——引擎不调用 LLM。边界清晰，`basis` 字段区分来源。

P1 不强制接入 LLM 主观评分。数据缺失或主观维度未启用时，返回中性分 50，并在指标中标记 `basis="missing"` 或 `data_available=false`。这样先建立可解释总分和持久化快照，避免同一阶段同时改 prompt、schema、保存、回测和 agent。

### 6.5 权重版本化

- `weights.py` 按 `score_version` 加载权重表，启动校验权重和 = 1.0。
- 权重可经 `config_registry` 覆盖（走现有配置入口，不新增平行实现）。
- 报告载荷与信号元数据存储 `weight_snapshot`，回测时按版本分组统计「评分↔涨跌」相关性，验证不了则迭代 v2。

---

## 7. 自反思记录系统

### 7.1 P1 持久化策略：复用现有链路

P1 不新增 `action_ledger`。现有 `decision_signal_extractor` 已经从报告提取 `action`、`entry_low/high`、`stop_loss`、`target_price`、`score`、`evidence`，且 `BacktestEngine` 已能基于操作建议、止损止盈和未来 K 线做收益评估。重复建操作台账会形成并行事实源。

P1 写入位置：

| 写入位置 | 内容 | 用途 |
|----------|------|------|
| `analysis_history` 的原始报告载荷 | 完整 `research_framework`，含 `total_score`、`score_version`、`dimensions`、`weight_snapshot` | 历史报告展示、后续评分统计 |
| `decision_signals.metadata` | `framework_score`、`score_version`、六维分数摘要 | 操作信号列表与回测聚合 |
| `decision_signals.evidence` | 完整或裁剪后的评分依据 | 回溯单次建议的依据 |

`decision_signals.score` P1 暂不直接替换为 `research_framework.total_score`，继续保持旧 `sentiment_score` 语义，避免 API/Web/回测统计突然切换口径。前端或 API 后续切换展示时再明确迁移。

### 7.2 暂缓新表

`score_ledger` 不是 P1 必需项。只有当以下条件出现时再拆独立表：

- 从 `analysis_history` / `decision_signals` 的 JSON 字段统计评分明显变慢；
- 需要高频按 `score_version`、维度分、未来收益做 SQL 聚合；
- 需要独立生命周期管理评分样本，而不是跟随报告历史。

若后续新增 `score_ledger`，字段可为：

| 字段 | 说明 |
|------|------|
| `id`, `report_id`, `stock_code`, `market` | 关联 |
| `total_score`, `score_version` | 总分与版本 |
| `dimension_scores` (JSON) | 六维分数快照 |
| `weight_snapshot` (JSON) | 权重快照 |
| `created_at` | 生成时间 |
| `future_returns` (JSON) | 1d/1w/1M 实际涨跌 |

### 7.3 写入流程

报告生成成功后，先把 `research_framework` 附加到 result，再保存历史记录。历史保存成功后，现有 `decision_signal_extractor` 在构建 payload 时把评分摘要写入 `metadata/evidence`。信号写入失败继续 best-effort，不阻塞主流程。

### 7.4 回测接口（复用现有能力）

P1 不新增 T+N 调度。后续统计「评分↔未来涨跌」时，优先复用 `BacktestEngine` 与现有回测结果；需要新增的只是按 `framework_score` / `score_version` / 六维分数分桶统计。

---

## 8. 新数据维度与数据源接入

六维度所需新数据，**优先用 akshare 现成免费接口**（已在依赖、A 股覆盖最全、零成本）：

| 维度数据 | akshare 接口 | 现状 |
|----------|--------------|------|
| 宏观流动性 | `macro_china_money_supply`（M2）、`macro_china_shrzgm`（社融） | 未接 |
| 北向资金 | `stock_hsgt_north_net_flow_in` | 未接 |
| 融资融券 | `stock_margin_*` | 未接 |
| 股东/高管 | `stock_gdfx_free_holding_detail_em` | 未接 |
| 龙虎榜 | `stock_lhb_detail_em` | 未接 |
| 研报评级 | `stock_research_report_em` | 未接 |
| 社交情绪（雪球/微博/贴吧） | 需爬虫 | 无（P4） |
| 缠论 K 线结构 | 需自研算法 / 第三方库 | 无（P4） |

**接入策略**：前 6 项封装为新的 fetcher 方法或独立 `data_provider/macro/`、`data_provider/sentiment/` 模块，走现有 fetcher 注册与熔断模式。社交爬虫与缠论算法列为 P4，不阻塞主报告。

---

## 9. 提示词与 Agent 改造

### 9.1 经典路径（`src/analyzer.py`）

| 改动点 | 内容 |
|--------|------|
| `SYSTEM_PROMPT` | P1 不强制改；P2 再追加：要求 LLM 对主观维度给 `{score, summary}`，并追加盘面结构、走势预测指令 |
| `_format_prompt` | 追加新数据表格（宏观/龙虎榜/研报，P2 接入后） |
| `_check_content_integrity` | 仅在 `SCORE_FRAMEWORK_ENABLED=true` 且评分服务成功时校验 `research_framework.dimensions`；旧报告和关闭开关时不得失败 |

经典路径 P1 先行：报告生成后调 `research_scoring_service` 聚合已有客观数据 + 缺失维度中性分 → 填 `research_framework` → 随历史报告与 `decision_signals` 写入快照。

### 9.2 多 agent 路径（`src/agent/`，P3）

新增两个专职 agent（高内聚，不塞进现有 agent）：

- `macro_agent`（宏观流动性 + 风险偏好）
- `sentiment_agent`（研报 + 社交情绪）

`decision_agent` 聚合六维 → 输出 `research_framework`。agent 链中 macro/sentiment 为可选阶段（类似 specialist 插入）。

---

## 10. 测试策略与测试报告

### 10.1 测试矩阵

| 模块 | 测试方式 | 覆盖目标 |
|------|----------|----------|
| `src/scoring/`（纯函数） | 纯单测：给定输入→期望分数/加权总分 | **100%** |
| 权重配置 | 单测：权重和=100%、版本切换、边界 | 100% |
| `research_framework` schema | Pydantic 校验：合法/非法 JSON、旧报告兼容、关闭开关兼容 | 关键路径覆盖 |
| `decision_signals` 快照写入 | payload 构造单测：metadata/evidence 含评分摘要；写入失败不阻塞 | 关键路径覆盖 |
| 新 fetcher 方法（P2） | mock akshare 返回（不联网）→ 字段标准化 | 关键路径覆盖；真实调用标 `@pytest.mark.network` |
| 向后兼容 | 旧报告（无 `research_framework`）解析/渲染回归测 | 确保旧报告不崩 |
| 提示词构造 | P2 再做 prompt 快照测：六维数据正确拼入 | P2 覆盖 |

### 10.2 100% 覆盖范围

强制 100%：`src/scoring/`（纯函数）。schema、历史保存、`decision_signals` 快照写入走关键路径测试，不为追求覆盖率新增低价值测试。

### 10.3 测试用例清单

| 测试文件 | 断言内容 |
|----------|----------|
| `test_weights.py` | 六维权重和=1.0；v1 存在；非法配置报错；指标权重和=1 |
| `test_normalization.py` | 归一化映射；越界 clamp [0,100]；None 处理 |
| `test_engine.py` | 加权聚合数值；空 dimensions；全 0/全 100 边界；四舍五入；权重缺失报错 |
| `test_indicators_technical.py` | 均线多头/空头/缠绕；MACD 金叉/死叉/零轴；RSI 超买超卖；支撑压力距离；缺失→中性 50 |
| `test_indicators_capital.py` | 主力净流入方向→分；筹码集中度阈值；获利比区间；缺失→中性 |
| `test_indicators_valuation.py` | PE 分位低估/高估/中位；负 PE 处理 |
| `test_research_framework_schema.py` | 合法 JSON 通过；类型错失败；维度数=6；权重和校验；`extra=allow` 与旧报告兼容 |
| `test_decision_signal_framework_snapshot.py` | payload metadata/evidence 写入 `framework_score`、`score_version`、六维摘要；旧报告无评分时不变 |
| `test_legacy_report_compat.py` | 旧报告（无 research_framework）解析+渲染不崩 |
| `test_prompt_framework_section.py`（P2） | 六维数据正确拼入 prompt |
| `test_research_scoring_service.py` | 编排：客观算分+缺失维度中性分+附加 result；信号快照失败不阻塞 |
| `test_macro_fetcher.py`（P2） | mock akshare→字段标准化；真实调用标 `@network` |

### 10.4 测试报告产出

```bash
pytest tests/test_scoring test_research_framework_schema test_decision_signal_framework_snapshot \
  --cov=src/scoring \
  --cov-fail-under=100 \
  --cov-report=term-missing --cov-report=xml
```

产出 coverage xml + 终端报告，附在 PR 描述（符合 `AGENTS.md` 报告变更需附证据）。

---

## 11. 影响面与兼容性保证

- **现有字段零改动** → Web/通知/历史/决策信号提取不受影响。
- **P1 复用现有表** → 不新增并行操作台账；评分快照随报告和信号保存。
- **新 fetcher 方法独立** → 不改现有 fetcher 行为。
- **前端渐进** → 后端先给 `research_framework` 数据，旧渲染不变，前端后续适配新段落。
- **Feature flag** `SCORE_FRAMEWORK_ENABLED`（默认渐进），关闭时不生成 `research_framework`、不写评分快照，等价回滚。

---

## 12. 分阶段交付路线图

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P1**（基础） | 最小六维评分引擎（纯函数，已有客观数据规则算分，缺失维度中性分）+ schema 追加 + 历史/信号评分快照 + Feature flag + 评分引擎 100% 测试 | 报告有可解释加权总分，数据开始记录 |
| **P2**（数据） | akshare 新接口（宏观/北向/融资/龙虎榜/股东/研报）+ LLM 主观维度打分 + 提示词改造 | 六维内容充实 |
| **P3**（预测） | 盘面解读段 + 走势预测段（多时间维度+情景）+ 多 agent 新增 macro/sentiment | 五段完整 |
| **P4**（可选） | 缠论算法 + 社交情绪爬虫 + T+N 回测调度（自反思闭环） | 自反思完整闭环 |

**起点为 P1**：评分引擎是地基，纯函数最易 100% 测试、零风险。先有可解释评分，再逐步填数据与预测段。

### P1 有序实现步骤（TDD）

1. 建 `src/scoring/` 骨架（`contracts` + `weights` + `engine` + `normalization`），先写测试再实现（RED→GREEN）。
2. 客观维度规则算分先覆盖现有数据可稳定提供的指标；缺失维度返回中性分并标记缺失原因。
3. `research_framework` schema（Pydantic）+ 校验测试。
4. `research_scoring_service` 编排：接入报告生成（经典 analyzer），把 `research_framework` 附加到 result。
5. 扩展 `decision_signal_extractor`：把评分摘要写入 `metadata/evidence`，不替换 `score` 字段语义。
6. Feature flag + 兼容回归测试。
7. 文档同步：本文件、`docs/CHANGELOG.md` `[Unreleased]`、`.env.example`（新增 `SCORE_FRAMEWORK_ENABLED` 等配置项）。

---

## 13. 风险与回滚

| 风险 | 应对 |
|------|------|
| 报告变长 → token 成本 + LLM 完整性下降 | 评分用规则（省 token），LLM 只给主观维度+综合段；必要时评分与报告生成拆两轮 |
| LLM 评分一致性差 | 坚持客观维度规则化，否则无法回测 |
| akshare 接口易被封 | 复用现有熔断 + 子进程超时模式，不重复造 |
| 回测需时间积累 | 先记录，回测分阶段，本次不做闭环 |
| 主观维度 P1 数据不足 | 先给中性分+标记，P2 数据接入后充实，不影响 P1 闭环与测试 |
| 新旧评分口径混用 | P1 保持 `decision_signals.score` 使用旧 `sentiment_score`，新分数只写 `framework_score` 元数据 |

**回滚**：`SCORE_FRAMEWORK_ENABLED=false` → 不生成 `research_framework`、不写评分快照；已保存历史中的追加字段不会影响旧解析，等价回滚。

---

## 14. 附录：模块结构

```
src/scoring/                       纯函数评分引擎（零外部依赖）
├── contracts.py / weights.py / engine.py / normalization.py
└── indicators/                    P2+ 按数据成熟度拆分

src/schemas/research_framework.py  六维评分 schema（Pydantic）
src/services/research_scoring_service.py  编排：取数→客观算分→附加评分快照

data_provider/macro_fetcher.py     P2: akshare 宏观/北向/融资
data_provider/sentiment_fetcher.py P2/P4: 研报/社交
src/agent/agents/macro_agent.py    P3: 宏观 agent
src/agent/agents/sentiment_agent.py P3: 情绪 agent
```

依赖方向（单向无环）：

```
report 生成 → research_scoring_service → src/scoring（纯函数）
                                  → analysis_history（完整报告快照）
                                  → decision_signals（评分摘要/evidence）
                                  → data_provider（取数，P2）
```
