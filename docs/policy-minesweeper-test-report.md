# 政策与公告双维度排雷 — 测试报告

> 报告日期：2026-06-26
> 范围：政策与公告排雷模块全链路（后端 scorecard → tool → executor → service → storage → endpoint → factory；前端 api → hook → page）。
> 要求：所有新增功能代码 100% 覆盖、不依赖真实 LLM/网络、不影响无关功能。

## 1. 覆盖率总览（后端）

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|------|-------|-------|-------|
| `src/services/policy_minesweeper_scorecard.py` | 107 | 0 | **100%** |
| `src/services/policy_minesweeper_service.py` | 164 | 0 | **100%** |
| `src/agent/tools/policy_minesweeper_tools.py` | 51 | 0 | **100%** |
| `src/agent/policy_minesweeper_executor.py` | 125 | 0 | **100%** |
| **合计（可直接 scope 的 4 个模块）** | **447** | **0** | **100%** |

补充说明（共享文件，PM 新增部分由专属测试覆盖）：
- `src/agent/factory.py::build_policy_minesweeper_executor`（新增函数，619 行起）— 100% 覆盖（`--cov` Missing 列中该函数行段零 miss）。
- `src/storage.py` 新增 `PolicyMinesweeperReport` 模型 + 6 个 CRUD 方法 — 由 `test_policy_minesweeper_storage.py` 18 用例覆盖（真实内存 SQLite）。
- `api/v1/endpoints/policy_minesweeper.py` — 由 `test_policy_minesweeper_api.py` 18 用例覆盖（TestClient，覆盖 SSE 400/success/error + CRUD 4 端点 + 路径穿越白名单）。该模块 `--cov` 测量受 conftest × 全量 endpoints 包导入的环境交互影响（numpy ImportError，非本模块代码问题），故以 18/18 测试通过率 + 所委托 service 100% 覆盖为保证。

## 2. 后端测试用例清单（7 文件 / 169 用例，全过）

| 测试文件 | 用例数 | 覆盖重点 |
|---------|-------|---------|
| `test_policy_minesweeper_scorecard.py` | 35 | 六维加权 / 时间窗 blend / 5 档分级 / Markdown 渲染（含证据原文地址 url 链接）/ clamp / 防御分支 |
| `test_policy_minesweeper_tools.py` | 31 | score 工具 handler 入参规整 / 返回契约 / 容错 / 证据 url 端到端 / **公司公告检索（query 构造/provider 选择/源分类/handler 全路径 DI/元数据）** |
| `test_policy_minesweeper_executor.py` | 23 | α/β 并行 / Ω 综合 / 各级降级（α 失败、β 失败、双失败、Ω 失败、Ω 空、全失败、loop 异常）/ 汇总 / 进度回调 / horizon 透传 / 纯函数辅助 |
| `test_policy_minesweeper_service.py` | 37 | 生成闭环 / 评分 best-effort 解析 / id 唯一化 / 落盘 / 清理 / PDF 惰性 / 列表分页 / CRUD / 异常降级 |
| `test_policy_minesweeper_storage.py` | 18 | save/get 闭环 / merge upsert / 列表分页过滤倒序 / to_dict / set_pdf_path / delete / prune / 异常分支 |
| `test_policy_minesweeper_api.py` | 18 | SSE 非 A 股 400 / 空 code 400 / agent 禁用 400 / done 事件 / error 事件 / list / get 404 / 路径穿越白名单 / delete / PDF |
| `test_policy_minesweeper_factory.py` | 7 | 工具集精确（5+1）/ 噪音过滤 / 总数=6 / 三 Agent 边界 / 全局单例不污染 / config 两路径 / 缺失工具 warning |

## 3. 前端测试用例清单（3 文件 / 14 用例，全过）

| 测试文件 | 用例数 | 覆盖重点 |
|---------|-------|---------|
| `api/__tests__/policyMinesweeper.test.ts` | 7 | getReports/getReport/deleteReport / generateStream ok+400 / downloadPdf blob+失败 |
| `hooks/__tests__/usePolicyMinesweeper.test.tsx` | 4 | SSE 状态机：done→报告填充 / error 事件 / reset / 流不完整（真实 ReadableStream 喂事件）|
| `pages/__tests__/PolicyMinesweeperPage.test.tsx` | 3 | 标题+空态+按钮渲染 / 未选股票拦截 / 时间窗口切换高亮 |

**前端质量门**：`tsc --noEmit` 零类型错误、`npm run lint` 零警告、`npm run build` 成功（`PolicyMinesweeperPage-*.js` chunk 已生成）。

## 4. 测试策略

- **DI 注入 `loop_runner`**：executor 三 Agent 并行编排可 100% 单测，无需 monkeypatch 局部 import 或真实 LLM。
- **离线 mock**：API 测试用 TestClient + monkeypatch service；storage 用真实内存 SQLite（`sqlite:///:memory:`）；前端 mock axios apiClient + 全局 fetch + 真实 ReadableStream。
- **白盒覆盖防御分支**：scorecard / factory 的 `try/except`、缺失兜底、warning 分支均有定向用例，达成 100%。
- **不烧 token**：无任何真实 LLM 调用；端到端真实生成留待 PR 验收。

## 5. 零无关功能影响

- 后端改动**纯追加**：新增文件 + `storage.py`/`factory.py`/`config.py`/`.env.example` 仅追加 PM 专属内容（未编辑既有逻辑）。
- `factory.py` 追加未破坏既有 builder：supply-chain e2e（factory 消费方）9/9 通过。
- 全量后端套件中 PM 相关 169 用例全过；既有失败均为其他在研工作（P1–P3 scoring 缺 `runner` fixture、deep_research md2pdf `_font_registered` 等），非本模块引入。
- 全量前端套件 788 passed / 5 failed，5 个失败均为 pre-existing（`DeepResearchPage` 的 `title=` governance 违规、`SidebarNav` stale 断言、`ReportOverview` 3 项），本模块 14 用例全过且新页面 governance-clean（用 `aria-label`）。

## 6. 运行方式

```bash
# 后端 PM 全量（含覆盖率）
.venv/bin/python -m pytest tests/test_policy_minesweeper_*.py -q \
  --cov=src.services.policy_minesweeper_scorecard \
  --cov=src.services.policy_minesweeper_service \
  --cov=src.agent.tools.policy_minesweeper_tools \
  --cov=src.agent.policy_minesweeper_executor --cov-report=term

# 前端 PM 全量
cd apps/dsa-web && npx vitest run src/api/__tests__/policyMinesweeper.test.ts \
  src/hooks/__tests__/usePolicyMinesweeper.test.tsx \
  src/pages/__tests__/PolicyMinesweeperPage.test.tsx
```
