# 政策与公告双维度排雷 — 实现方案 (V1 MVP, 审计优化版)

> 状态：方案已确认（2026-06-26）+ 已通过代码审计优化（2026-06-26），待实现。
> 审计基线：对照 `deep_research` / `supply_chain` / `zhengxi` 三个同类功能的真实代码，核实持久化、PDF、run_agent_loop、评分工具、测试设施。
> 落盘：`docs/policy-minesweeper-plan.md`。

---

## 0. 审计与优化摘要（本次更新核心）

对照仓库真实代码审计后，对原方案做的**简化与加固**（KISS / 高内聚低耦合 / 100% 可测 / 零无关影响）：

| # | 原方案 | 优化后 | 依据 |
|---|---|---|---|
| 1 | α/β/Ω 各建独立 ToolRegistry（3 个） | **1 个 feature 级共享 registry**，行为分离靠 prompt | `build_supply_chain_executor` 就是 1 registry/feature；评分工具对 α/β 可见无害 |
| 2 | 3 个 prompt 文件（alpha/beta/omega_prompt.md） | **1 个 system_prompt.md**（共享方法论+评分契约+合规），角色差异作为 executor 内常量 | 方法论单一真源=高内聚 |
| 3 | scorecard.json + importlib 间接层（仿 supply_chain） | **普通可导入模块 + 模块级常量权重**，无 json、无 importlib | supply_chain 的 importlib 是为加载外部 skill 脚本；本功能原生，无需该间接层 |
| 4 | 独立 `PolicyMinesweeperValidator` 类 + retry-with-hints | **去掉 validator 类与重试**，靠评分工具确定性输出做结构保证 + 失败降级 | supply_chain 无 validator 类；MVP 不做重试（YAGNI） |
| 5 | run_agent_loop 局部 import（仿 deep_research） | **依赖注入 `loop_runner`**（`__init__` 默认 `run_agent_loop`） | deep_research 局部 import 难单测；DI 让编排+降级 100% 可测，无需脆弱 monkeypatch |
| 6 | 持久化表述模糊 | 明确：**新增 `PolicyMinesweeperReport` 表**，create_all 幂等（`IF NOT EXISTS`），**必须在该调用前 import 新 model**（同 position/score/belief ledger） | storage.py:1237-1245 核实 |
| 7 | horizon 权重埋在 prompt | **horizon 作为 `score(payload, horizon)` 确定性输入** | 纯函数可测，不依赖 LLM 纪律 |
| 8 | 测试一笔带过 | **5 个后端测试文件 + 3 个前端测试文件 + 覆盖率报告**，按新模块范围量化 100% | 仓库无 `--cov` 配置，需加 `pytest-cov`/`@vitest/coverage-v8`（dev-only 增量） |
| 9 | 文件数 ~10+ | **后端 5 个新文件 + 1 data 文件 + 前端 3 个 + 挂载点** | 砍掉 validator/retry/json/2 个 prompt 文件 |

**不变的核心决策**（上一轮已确认，本次保留）：同级顶级菜单 `/policy-minesweeper`；表单流（镜像深度投研）；真·三 Agent 并行裁决；指令式仓位输出（加仓/增持/减持/回避/清仓）+ 强制免责声明；复用 SearchService；复用现有 LLM 配置；PDF 复用 md2pdf。

---

## 1. 产品定位 & MVP 范围

**一句话**：用户输入 A 股代码/名称 + 时间窗口 → α 扫描公司公告/经营事件、β 分析国家政策/产业政策与公司业务的互动，两者**并行** → Ω 综合裁决，输出**利好/利空方向 + -100~+100 综合评分 + 5 档等级 + 预期冲击区间 + 证据链 + 情景分析 + 仓位指令**的结构化排雷报告。

| MVP 内 (做) | MVP 外 (Phase 2) |
|---|---|
| 公告/政策事件识别+分类+方向判定 | 历史事件 Base Rate DB / CAR 回归 |
| 政策-业务暴露度定性映射 | Neo4j 政策-业务知识图谱 |
| -100~+100 六维加权评分 + 5 档 | 完整 DCF/WACC 量化 |
| 预期冲击区间（按等级静态经验区间，标注非预测） | XGBoost CAR 预测 / FinBERT |
| α/β/Ω 三 Agent 并行 + 证据链接 + 日期 | 一致预期/期权隐含波动率超预期量化 |
| 3 档情景分析 + 仓位指令 + 强制免责声明 | 巨潮/交易所/部委一手 fetcher |

> **诚实声明**：V2.0 PRD 的 Base Rate DB / 知识图谱 / DCF / CAR-XGBoost / FinBERT 在 MVP 无法落地（无一手数据/训练语料）。预期冲击区间是按等级的**静态经验区间**（非模型预测），明确标注。

---

## 2. 总体架构（优化后）

```
用户输入 A股代码/名称 + 时间窗口(short/medium/long)
              │
              ▼
   policy_minesweeper_service.generate_report()
        规范化代码 → 查名 → build_policy_minesweeper_executor()
              │
              ▼
   PolicyMinesweeperExecutor.generate(loop_runner 可注入)
              │  1 个共享 ToolRegistry（wengu 子集 + score_policy_minesweeper）
       ┌──────┴───────┐   ThreadPoolExecutor(max_workers=2)
       ▼              ▼   两个 loop_runner(...) 并行
   ┌───────┐      ┌───────┐
   │ α 公告 │      │ β 政策 │   共用 registry + 角色差异在 prompt（system_prompt.md + 内联角色常量）
   │ 扫描器 │      │ 分析师 │   max_steps≤10 / wall_clock≤300s
   └───┬───┘      └───┬───┘
       │ α报告        │ β报告
       │ micro_score  │ macro_score + 暴露度映射
       └──────┬───────┘
              ▼   注入两份报告
        ┌──────────┐
        │ Ω 综合裁决│  loop_runner(...) max_steps≤6 / wall_clock≤240s
        │ 调 score_ │  → scorecard.score(payload, horizon) 确定性合成
        │ policy_   │     （-100~+100 / 5 档 / 仓位指令 / 预期冲击 / markdown）
        │ minesweeper│
        └─────┬────┘
              ▼   失败→降级(见§8)，无 validator 类、无重试
        SSE 流式返回 → 写 .md + SQLite + 推 done
```

**关键**：α/β/Ω **都是无状态 loop_runner 调用**，不碰 `conversation_manager`（form-flow 非对话），无会话竞争。`loop_runner` 默认 `run_agent_loop`，测试注入 fake → 编排逻辑 100% 可测。

---

## 3. 已确认决策

| 决策点 | 选择 |
|---|---|
| 菜单位置 | 新增同级顶级菜单项 `/policy-minesweeper`（导航扁平，不引入子菜单） |
| 交互形态 | 表单流（镜像 深度投研 `DeepResearchPage`，无 Zustand store） |
| Agent 架构 | 真·三 Agent 并行（α/β `ThreadPoolExecutor(2)` → Ω 合成） |
| ToolRegistry | **1 个 feature 级共享 registry**（审计优化，原 3 个） |
| Prompt 资产 | **1 个 `system_prompt.md` + 内联角色常量**（审计优化，原 3 个文件） |
| 数据源 | 复用 `SearchService` web 搜索 + 政策/公告 query 调优 |
| 评分 | 确定性评分工具（LLM 评因子 → `scorecard.score()` 合成），原生可导入模块 |
| 校验/重试 | **无 validator 类、无重试**，确定性输出 + 降级（审计优化） |
| 可测试性 | **DI 注入 `loop_runner`**（审计优化） |
| 仓位建议 | 指令式：加仓/增持/减持/回避/清仓（用户坚持）+ 强制免责声明 |
| LLM 配置 | 复用现有 agent 配置（同郑希） |
| PDF | 复用共享 `md2pdf.markdown_to_pdf_file` |
| 时间窗口默认 | medium（1-4 周） |
| 英文菜单名 | `Policy & Filing Minesweeper` |

---

## 4. 后端实现

### 4.1 Scorecard — `src/services/policy_minesweeper_scorecard.py`（纯函数，原生模块）
镜像 `serenity_scorecard.score()` 的"LLM 评因子→确定性合成"模型，但**原生可导入**（无 importlib、无 json）：

```python
# 模块级常量（权重/档位/预期冲击区间），score() 纯函数
DIMENSION_WEIGHTS = {  # 六维，和=1.0
    "event_importance": 0.20, "policy_exposure": 0.20, "earnings_impact": 0.25,
    "valuation_impact": 0.15, "price_sensitivity": 0.10, "time_urgency": 0.10,
}
HORIZON_BLEND = {  # α/β 在综合分中的再权重
    "short":  {"alpha": 0.70, "beta": 0.30},
    "medium": {"alpha": 0.50, "beta": 0.50},
    "long":   {"alpha": 0.30, "beta": 0.70},
}
TIERS = [  # (lo, hi, emoji, label_zh, action)
    (70, 100, "🟢", "强利好", "加仓"),
    (30, 69,  "🟡", "中等利好", "增持"),
    (-30, 29, "⚪", "中性", "持有/观望"),
    (-69, -30,"🟠", "中等利空", "减持"),
    (-100,-70,"🔴", "强利空", "清仓/回避"),
]
EXPECTED_CAR = { ... }  # 按档位的静态经验区间（标注非预测）

def score(payload: dict, horizon: str) -> dict:
    # 1) 六维加权 → dimension_composite（clamp [-100,100]）
    # 2) alpha_score/beta_score 按 HORIZON_BLEND 再权重 → blend
    # 3) final = 0.5*dimension_composite + 0.5*blend（可调，纯函数可测）
    # 4) 查 TIERS → tier/action；查 EXPECTED_CAR → 冲击区间
    # 返回 {final, tier, action, expected_car, dimension_details, ...}

def to_markdown(result: dict) -> str: ...   # 渲染结构化报告
```

等级 / 仓位指令 / 预期冲击映射：

| 综合分 | 等级 | 仓位指令 | 1日AR | 3日CAR | 10日CAR |
|---|---|---|---|---|---|
| +70~+100 | 🟢 强利好 | **加仓** | +2~+5% | +3~+8% | +5~+12% |
| +30~+70 | 🟡 中等利好 | **增持** | +0.5~+2% | +1~+3% | +2~+5% |
| -30~+30 | ⚪ 中性 | 持有/观望 | ±0.5% | ±1% | ±2% |
| -70~-30 | 🟠 中等利空 | **减持** | -0.5~-2% | -1~-3% | -2~-5% |
| -100~-70 | 🔴 强利空 | **清仓/回避** | -2~-5% | -3~-8% | -5~-15% |

> 预期冲击为静态经验区间，报告内标注"历史经验区间，非精确预测"。

### 4.2 Tool — `src/agent/tools/policy_minesweeper_tools.py`
单工具 `score_policy_minesweeper`，镜像 `score_supply_chain_bottleneck`：handler 规范化 LLM 入参（六维评分 + alpha_score + beta_score + 情景 + 置信度 + horizon）→ 调 `scorecard.score()` + `to_markdown()` 返回。`ALL_POLICY_MINESWEEPER_TOOLS = [score_policy_minesweeper_tool]`。

### 4.3 Executor — `src/agent/policy_minesweeper_executor.py`（**novel**：并行编排 + DI）
```python
class PolicyMinesweeperExecutor:
    def __init__(self, tool_registry, llm_adapter, *,
                 max_steps_ab=10, max_steps_omega=6,
                 wall_ab=300.0, wall_omega=240.0,
                 loop_runner=None, prompt_loader=None):
        self._loop = loop_runner or _default_loop   # DI：默认 run_agent_loop
        self._load_prompt = prompt_loader or _load_system_prompt
        ...

    def generate(self, stock_code, stock_name, horizon, progress_callback=None):
        # 1) base = self._load_prompt()（system_prompt.md）；α/β/Ω 消息 = base + 内联角色常量 + 股票/窗口
        # 2) cb_a, cb_b = _tagged("α", cb), _tagged("β", cb)
        # 3) ThreadPoolExecutor(2): fut_a/fut_b = pool.submit(self._loop, messages=..., registry=self._reg,
        #                          llm_adapter=..., max_steps=..., max_wall_clock_seconds=...,
        #                          progress_callback=cb_a/cb_b)
        #    α_result, β_result = fut_a.result(), fut_b.result()   # 异常→降级
        # 4) Ω 消息 = base_omega + α报告 + β报告 + horizon；ω_result = self._loop(...)
        # 5) return PolicyMinesweeperResult(...)   # 无 validator、无重试
```
**降级**（§8）：α/β/Ω 任一失败都不整体失败。`_default_loop` 内做 `from src.agent.runner import run_agent_loop` 局部 import，但**通过 `self._loop` 调用** → 测试注入 fake 即绕过真实 loop（避免 deep_research 那种局部 import 难测的反模式）。

**线程安全**：α/β 各有独立 messages（无共享可变状态）；共用 `llm_adapter`（litellm 无状态可并发）；progress_callback 跨线程走 endpoint 已有的 `run_coroutine_threadsafe` 桥（安全）。

### 4.4 Factory — `src/agent/factory.py` 新增 `build_policy_minesweeper_executor(config)`
镜像 `build_supply_chain_executor`（factory.py:492-504 模板）：新建 `ToolRegistry` → 复制 wengu 子集工具（`search_stock_news`/`search_comprehensive_intel`/`get_stock_info`/`get_realtime_quote`/`get_sector_rankings`）→ 注册 `ALL_POLICY_MINESWEEPER_TOOLS` → 构造 executor（**不传 loop_runner，用默认**）。硬编码 `max_steps_ab=10 / max_steps_omega=6`、wall clock 300/240（不读共享的 `config.agent_max_steps`）。

### 4.5 Service — `src/services/policy_minesweeper_service.py`（克隆 `deep_research_service.py`）
`generate_report(raw_code, raw_name, horizon, progress_callback)`：规范化 A 股码 → 查名 → 唯一 `report_id` → `executor.generate(...)` → 写 `.md` 到 `reports/policy_minesweeper/` → `get_db().save_policy_minesweeper_report(...)` → 裁剪（默认 200）。`get_pdf_path()` 懒生成：`md2pdf.markdown_to_pdf_file(md, pdf_path)` → `set_policy_minesweeper_pdf_path(...)`（镜像 deep_research `_generate_pdf`）。

### 4.6 Endpoint — `api/v1/endpoints/policy_minesweeper.py`（克隆 `deep_research.py`）
前缀 `/policy-minesweeper`，`router.py` + `endpoints/__init__.py` 注册：
- `POST /generate/stream`（SSE，A 股码同步校验 400，`loop.run_in_executor` 跑 service，progress→Queue，30s 心跳）
- `GET /reports` / `GET /reports/{id}` / `DELETE /reports/{id}` / `GET /reports/{id}/pdf`（`asyncio.to_thread` 包 md2pdf，同 deep_research）

Request：
```python
class PolicyMinesweeperRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    analysis_horizon: str = "medium"
```
`report_id` 白名单复用 `^\d{6}_\d{12}(_\d+)?$`。

### 4.7 持久化 — `src/storage.py`（既有文件，增量）
新增 `PolicyMinesweeperReport` 模型（列镜像 `DeepResearchReport`：id/stock_code/stock_name/created_at/md_path/pdf_path/status/composite_score/verdict/alpha_score/beta_score/confidence/horizon/total_steps/total_tokens/provider）+ CRUD（save/get_reports/get/set_pdf_path/delete/prune）。
> **关键**：`Base.metadata.create_all` 是 `IF NOT EXISTS` 幂等，加新表不碰既有表；**必须把新 model 在 storage.py:1237 `create_all` 调用前 import**（同 position/score/belief ledger 的处理）。

---

## 5. 前端实现（apps/dsa-web/）

| 新增文件 | 作用 | 来源 |
|---|---|---|
| `src/api/policyMinesweeper.ts` | fetch SSE 客户端 | 克隆 `deepResearch.ts` |
| `src/hooks/usePolicyMinesweeper.ts` | 状态机 + SSE 解析 + 90s watchdog | 克隆 `useDeepResearch.ts` |
| `src/pages/PolicyMinesweeperPage.tsx` | 两栏（历史 + 表单/进度/报告） | 克隆 `DeepResearchPage.tsx` |

挂载点（既有文件，增量）：`App.tsx`（lazy + `<Route>`）、`SidebarNav.tsx`（1 nav 项，紧邻 deep-research）、`i18n/uiText.ts`（`layout.nav.policyMinesweeper` zh/en）。

表单：`StockAutocomplete`（form 模式）+ 时间窗口选择器（默认 medium）+ 生成按钮。进度区渲染 `progressSteps`（α/β/Ω 分阶段高亮）。报告区：`ReportMarkdownBody` + 等级/综合分/置信度/仓位指令 banner + PDF/复制/重新生成。无 store（同 deep-research）。

---

## 6. 数据源策略 & 局限

- **MVP**：α/β 全靠 `SearchService`（Bocha/Tavily/Brave 等）。`search_comprehensive_intel` 的 `announcements`/`risk_check` 维度给 α，`industry` + β prompt 政策 query 给 β。
- **局限**（文档如实标注）：无一手公告/政策数据；召回依赖搜索引擎；时效性/完整性不保证。证据**必须带链接 + 日期**，无法核验标注"待核验"。
- **Phase 2**：cninfo/gov 一手 fetcher、Base Rate DB。

---

## 7. 合规红线

用户决定（2026-06-26）：**指令式**仓位输出（加仓/增持/减持/回避/清仓），不软化。底线保留：
- 报告末尾**强制、不可移除**免责声明："本分析基于公开信息，历史表现不代表未来，**不构成投资建议**，买卖由你自己决定。"
- 证据标出处 + 日期；"预期冲击区间"标注"历史经验区间，非精确预测"；无法核验标注"待核验"。
- 诚实红线靠 prompt（同郑希结论：现有框架无代码层出处追踪，工具返回值带 source/quote 引导）。

> 注：供应链功能此前"禁买卖指令"；本功能按用户明确指示采用指令式 + 强制免责声明。两功能策略不同，以各自确认为准。

---

## 8. 并行编排 — 降级 & 边界

- **α 或 β 失败/超时**：不整体失败。降级为"单维度结论 + 标注另一维度缺失"，Ω prompt 告知缺失维度，置信度下调并显式标注。
- **Ω 失败**：返回失败 + 已有 α/β 原始报告（用户至少看到两维度分析）。
- **超时**：α/β 各 ≤300s，Ω ≤240s；SSE 30s 心跳 watchdog（同 deep_research）；nginx 需 `proxy_read_timeout ≥ 960s` + 关 `proxy_buffering`（同供应链，docs 标注）。
- **Token 成本**：α(≤10)+β(≤10)+Ω(≤6) ≈ 问股 3-5 倍（远低于供应链 40 步）。无配额，文档标注。

---

## 9. 测试策略与测试报告（对应要求 #3 #5）

### 9.1 范围与度量
- **目标**：新增代码 100% 行覆盖（后端 Python + 前端 TS）。既有代码零回归（全量 pytest + 前端 lint/build + vitest）。
- **度量**（仓库当前无 `--cov` 配置，需加 dev-only 增量依赖）：
  - 后端：`pytest-cov`，按新模块范围出 `term-missing` 报告。
  - 前端：`@vitest/coverage-v8`，按新文件出报告（仓库已有 vitest 实践 ~40 个测试文件，但 CI web-gate 只跑 lint+build，不 gate vitest——本次新增测试并说明 CI 现状）。
- **mock 风格**：遵循仓库既有做法——`monkeypatch`/`MagicMock`/`tmp_path` 内联，**不新建 conftest fixture 库**（仓库 conftest 故意只做 asyncio patch）。

### 9.2 后端测试矩阵（5 个文件，全部保留）

| 测试文件 | 被测模块 | 关键用例（断言） |
|---|---|---|
| `tests/test_policy_minesweeper_scorecard.py` | scorecard 纯函数 | 六维加权合成正确；clamp ±100 边界；horizon→blend 权重（short/medium/long）；tier/action 查表（5 档全覆盖）；expected_car 查表；`to_markdown` 含等级/指令/免责；缺维度容错 |
| `tests/test_policy_minesweeper_tools.py` | `score_policy_minesweeper` handler | 入参规范化；正常→调 scorecard→返回 markdown/final/action；scorecard 异常→返回 error+input_echo 不抛 |
| `tests/test_policy_minesweeper_executor.py` | executor 编排+降级（**注入 fake loop_runner**） | α/β/Ω 全成功→合成；α 失败β 成功→降级标注；β 失败α 成功→降级；αβ 都失败→Ω 仍尝试或返回原始；Ω 失败→返回 α/β 报告；progress_callback 被 α/β/Ω 各自 tag 触发；horizon 正确传入 score 调用；超时路径 |
| `tests/test_policy_minesweeper_service.py` | service 持久化（mock executor + tmp_path + 临时 DB） | 规范化代码；report_id 唯一化；写 .md 成功/空内容；save/get/list/delete/prune；PDF 懒生成（mock md2pdf）→ set_pdf_path |
| `tests/test_policy_minesweeper_api.py` | endpoint（TestClient + mock service） | SSE `/generate/stream` 事件序列（thinking/tool_start/tool_done/done）+ A 股码校验 400；CRUD 4 端点；PDF 端点（mock md2pdf 返回 path/None 两路）；会话/前缀不影响其他端点 |

### 9.3 前端测试矩阵（3 个文件，全部保留）

| 测试文件 | 被测 | 关键用例 |
|---|---|---|
| `src/api/__tests__/policyMinesweeper.test.ts` | api 客户端 | URL/方法/payload 正确；SSE 行解析（data: 行→事件）；abort 信号透传；错误解析 |
| `src/hooks/__tests__/usePolicyMinesweeper.test.tsx` | hook 状态机 | idle→generating→done/error 转移；progressSteps 累积；90s watchdog 触发 abort；done 事件取 report/reportId；cancel/reset |
| `src/pages/__tests__/PolicyMinesweeperPage.test.tsx` | page 渲染 | 表单输入+生成触发；历史列表加载/选择/删除；报告渲染含等级/指令 banner；进度区渲染；i18n key 存在（zh/en） |

### 9.4 测试报告（实现后产出）
新增 dev 依赖后执行，报告作为交付物（保留）：

```bash
# 后端：新模块 100% 覆盖报告
pytest tests/test_policy_minesweeper_scorecard.py tests/test_policy_minesweeper_tools.py \
       tests/test_policy_minesweeper_executor.py tests/test_policy_minesweeper_service.py \
       tests/test_policy_minesweeper_api.py \
       --cov=src.agent.policy_minesweeper_executor \
       --cov=src.services.policy_minesweeper_scorecard \
       --cov=src.services.policy_minesweeper_service \
       --cov=src.agent.tools.policy_minesweeper_tools \
       --cov-report=term-missing \
       --cov-report=html:docs/_coverage/policy_minesweeper

# 后端：全量零回归
python -m pytest -m "not network"

# 前端：新文件覆盖 + 全量
cd apps/dsa-web && npm test -- policyMinesweeper --coverage
npm run lint && npm run build
```

**报告产物**（交付时填入实际值）：
| 项 | 目标 | 实际（待填） |
|---|---|---|
| 后端新模块行覆盖 | 100% | ___ |
| 后端全量 pytest | 全绿，零回归 | ___ passed |
| 前端新文件行覆盖 | 100% | ___ |
| 前端 lint/build | 通过 | ___ |
| `python -m py_compile <改动py>` | 通过 | ✅ |
| `./scripts/ci_gate.sh` | 通过 | ___ |
| `python scripts/check_ai_assets.py` | 通过 | ___ |
| 端到端真 LLM + UI 截图 | 手工（CLAUDE.md 要求附图） | 待 |

> 100% 排除项：真正不可达的防御性分支（如 `if False` 兜底），在报告里逐条注明理由。

---

## 10. 不影响其他功能的保证（对应要求 #4）

| 改动面 | 性质 | 风险控制 |
|---|---|---|
| `src/storage.py`（+ model + CRUD） | 增量 | `create_all` 幂等不碰既有表；新 model 在调用前 import；既有 CRUD 函数零改动 |
| `src/agent/factory.py`（+ 1 builder） | 增量 | 新 builder 独立；不动既有 builder；新 ToolRegistry 不污染 `get_tool_registry()` 全局单例 |
| `api/v1/endpoints/{__init__.py,router.py}` | 增量 import + include_router | 仅追加，不动既有路由 |
| `run_agent_loop` / `llm_adapter` / `conversation_manager` / `deep_research` / `zhengxi` / `supply_chain` / 问股 | **不改** | 零影响 |
| 前端 `App.tsx`/`SidebarNav.tsx`/`i18n/uiText.ts` | 增量（1 route/nav/2 keys） | 仅追加；lint+build+既有 page 测试须全绿 |
| dev 依赖 `pytest-cov` / `@vitest/coverage-v8` | dev-only 增量 | 不进运行时；加到 `requirements*.txt`/`package.json` devDependencies |

**回归底线**：全量 pytest（224 文件）+ 三同类功能（问股/郑希/供应链）测试全绿 + 前端 lint/build。任一回归即阻断。

---

## 11. 任务阶段分解

| 阶段 | 内容 | 验证（TDD：先红后绿） |
|---|---|---|
| 0 | dev 依赖（pytest-cov / @vitest/coverage-v8）+ data/policy_minesweeper/system_prompt.md | 文件就位 |
| 1 | scorecard 纯函数 + 单元测试 | `test_..._scorecard.py` 100% |
| 2 | tool handler + 测试 | `test_..._tools.py` 100% |
| 3 | executor（DI loop_runner）+ 编排/降级测试 | `test_..._executor.py` 100%（含所有降级分支） |
| 4 | service + storage + 持久化测试 | `test_..._service.py` 100% |
| 5 | endpoint + API 测试 + router 注册 | `test_..._api.py` 100% + SSE 烟测 |
| 6 | factory builder + 全量回归 | py_compile + ci_gate + 全量 pytest 零回归 |
| 7 | 前端 api/hook/page + 3 个 vitest 测试 + nav/route/i18n | 新文件 100% + lint + build |
| 8 | 测试报告（§9.4）+ 文档（用户文档 + CHANGELOG + .env.example）+ 端到端截图 | 报告产出 |

---

## 12. 风险点 & 回滚

| 风险 | 缓解 |
|---|---|
| 并行编排是仓库首次（线程/降级） | α/β 无状态独立 messages；DI 注入便于单测所有分支；先验三同类功能回归零影响 |
| 无一手数据，召回不稳 | prompt 调优 + 待核验标注 + Phase 2 fetcher |
| Token 成本上升 | 每循环 max_steps/wall_clock 上限；文档标注 |
| 指令式仓位合规风险 | 强制不可移除免责声明 + 出处/日期标注（用户已确认指令式） |
| storage 加表 | create_all 幂等 + 调用前 import，既有 DB 升级安全 |
| 前端 vitest 非 CI gate | 新增测试本地跑 + 报告；可选二期把 `npm test` 纳入 web-gate（触及 CI，本次不做） |

**回滚**：删新增文件 + 还原挂载点（factory/router×2/storage import/App/SidebarNav/i18n + 2 dev 依赖）。无数据迁移、无 schema 破坏性变更。

---

## 13. 文件清单

**新增（后端）**
- `src/services/policy_minesweeper_scorecard.py`
- `src/agent/tools/policy_minesweeper_tools.py`
- `src/agent/policy_minesweeper_executor.py`
- `src/services/policy_minesweeper_service.py`
- `api/v1/endpoints/policy_minesweeper.py`

**新增（前端）**
- `apps/dsa-web/src/api/policyMinesweeper.ts`
- `apps/dsa-web/src/hooks/usePolicyMinesweeper.ts`
- `apps/dsa-web/src/pages/PolicyMinesweeperPage.tsx`

**新增（测试，全部保留）**
- `tests/test_policy_minesweeper_scorecard.py`
- `tests/test_policy_minesweeper_tools.py`
- `tests/test_policy_minesweeper_executor.py`
- `tests/test_policy_minesweeper_service.py`
- `tests/test_policy_minesweeper_api.py`
- `apps/dsa-web/src/api/__tests__/policyMinesweeper.test.ts`
- `apps/dsa-web/src/hooks/__tests__/usePolicyMinesweeper.test.tsx`
- `apps/dsa-web/src/pages/__tests__/PolicyMinesweeperPage.test.tsx`

**新增（数据/文档）**
- `data/policy_minesweeper/system_prompt.md`
- `docs/policy-minesweeper.md`（用户文档）+ 本方案 + CHANGELOG + .env.example（若有配置）

**改动（挂载点，增量）**
- `src/storage.py`（+ model + CRUD + create_all 前 import）
- `src/agent/factory.py`（+ builder）
- `api/v1/endpoints/__init__.py` + `api/v1/router.py`
- `apps/dsa-web/src/{App.tsx, components/layout/SidebarNav.tsx, i18n/uiText.ts}`
- `requirements*.txt`（+ pytest-cov dev）+ `apps/dsa-web/package.json`（+ @vitest/coverage-v8 dev）
