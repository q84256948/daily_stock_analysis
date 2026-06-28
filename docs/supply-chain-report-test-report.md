# 供应链表单式报告流 — 测试报告

对应变更：`/supply-chain` 由聊天式升级为表单式报告流（分析主题 [+ 可选线索] → SSE → 报告 → 历史 → PDF）。本报告汇总新增测试、回归与类型检查结果。

## 测试矩阵

### 后端（pytest，离线 mock，不依赖真实 LLM/网络/DB 文件）

| 文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `tests/test_supply_chain_report_storage.py` | 18 | `SupplyChainReport` 模型 + 6 CRUD（save/get/list 倒序/delete 返回路径/set_pdf/prune 删文件）+ to_dict + `_run_write_transaction` 异常分支 |
| `tests/test_supply_chain_report_service.py` | 38 | `build_supply_chain_user_message`（带/不带/空白线索）、`_status_from_result`（success/partial/failed）、`_resolve_unique_report_id`、`generate_report`（成功落盘/线索注入 chat message/session 命名空间隔离/空主题/whitespace 主题/partial/failed/写盘失败跳过保存/done 事件全载荷）、list/get/delete 代理、PDF 惰性/复用/失败/import-error/md 缺失、prune（清文件/0 noop/unlink 异常吞掉）、目录创建、executor 缓存、prompt 含线索核验规则 |
| `tests/test_supply_chain_report_api.py` | 22 | `generate_stream`（空/超长 topic 422 / 缺字段 422 / 超长 hint 422 / agent 禁用 400 / done 事件 / service 异常 error 事件 / InputError error 事件）、list（空/带项/分页透传）、get（缺失 404 / report_id 白名单 6 种非法 404 / 详情）、delete（缺失 404 / 非法 404 / 成功）、PDF（缺失 404 / 非法 404 / 生成失败 404 / 安全路径返回文件 / root 外路径 404） |
| **小计** | **78** | 全部通过 |

### 前端（vitest + jsdom）

| 文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `apps/dsa-web/src/api/__tests__/supplyChainReports.test.ts` | 8 | getReports 解包+分页 / getReport 详情 / deleteReport / generateStream 成功（带 topic/hint）+ 非 2xx 抛错 / downloadPdf blob 下载（文件名+revoke）+ 失败抛带状态码错误 |
| `apps/dsa-web/src/hooks/__tests__/useSupplyChainReport.test.tsx` | 14 | done（带/无 report_id → done/error）/ error 事件 / heartbeat 不入 steps / thinking-tool-generating 入 steps / SSE 提前关闭无 done → error / SSE 流不可用 → error / 非 abort 网络错误 → error / 90s watchdog fake-timer 超时 / cancel → idle / reset 清空 / 卸载清理不抛错 / 传 AbortSignal / waitFor done |
| `apps/dsa-web/src/pages/__tests__/SupplyChainReportPage.test.tsx` | 9 | 挂载加载历史 / 主题必填 / 快捷模板填充 / 带线索生成（generateStream 收到 hint + 发送后清空 hint + 保留 topic）/ 无线索生成 / SSE error 展示 / 下载 PDF 按钮 / 复制 Markdown / 选中历史不回填线索 / 删除历史 |
| **小计** | **31** | 全部通过 |

## 回归（无影响确认）

| 范围 | 结果 |
| --- | --- |
| `tests/test_supply_chain_services.py` + `test_supply_chain_e2e.py`（旧供应链 scorecard/工具/chat 端点 E2E） | 全绿，旧 chat 端点与新 reports 端点共存无冲突 |
| `tests/test_md2pdf.py`（PDF 渲染，未改 md2pdf） | 全绿 |
| `tests/test_storage.py`（共享 storage.py，仅追加新模型/CRUD） | 全绿 |
| `tests/test_policy_minesweeper_{storage,service,api}.py`（同模式姊妹功能） | 全绿 |
| 前端 `npm run lint` + `npm run build`（全量） | 通过（tsc 类型检查 + vite 构建） |

合计回归 **132** 后端用例 + 全量前端 lint/build 通过。

## 类型检查（三层防御 Layer 1）

| 工具 | 范围 | 结果 |
| --- | --- | --- |
| pyright（`typeCheckingMode=standard`, `reportMissingTypeArgument=true`） | 新增/修改文件（`supply_chain_report_service.py` / `supply_chain_reports.py` / `storage.py` / `router.py`，venv 解析依赖） | **0 errors, 0 warnings** |
| mypy（`warn_return_any=true`） | 新增文件 `supply_chain_report_service.py` / `supply_chain_reports.py` | **0 errors**（仓库其余 761 errors 为既有无关文件，非本次引入） |

## 三层防御落地

- **Layer 1 类型**：所有新公开函数加类型注解；无裸 `dict/tuple/list/Callable`（pyright `reportMissingTypeArgument` 通过）。
- **Layer 2 契约**：本特性无复杂金融公式，按决策规则**不引入 icontract**（避免与 Pydantic 重复校验）。
- **Layer 3 数据**：`SupplyChainGenerateRequest` 用 Pydantic v2 `ConfigDict(strict=True, frozen=True, validate_assignment=True)` + `Field(min_length=1, max_length=1000/2000)`，空/超长主题解析期直接 422；service 层只做 `.strip()` 语义兜底。

## 已知既有失败（非本次引入，未触碰对应文件）

- `tests/test_deep_research.py::TestMd2Pdf::test_render_failure_returns_none_not_raises`：引用 `md2pdf._font_registered`（当前 `src/md2pdf.py` 无此属性），测试/代码既有漂移；本次未改 `md2pdf.py`/`test_deep_research.py`（`git status` 确认）。
- 前端 `tests/ui_governance.test.ts`（native `title=` 扫描）：既有违规来自 `DeepResearchPage.tsx` / `PolicyMinesweeperPage.tsx`（本次未触碰）；新 `SupplyChainReportPage.tsx` 已用 `aria-label`，**0** `title=` 违规。
- 前端 `SidebarNav.test.tsx` / `ReportOverview.test.tsx`（3 例）：既有失败，与本次无关。

## 复现命令

```bash
# 后端
python -m pytest tests/test_supply_chain_report_storage.py tests/test_supply_chain_report_service.py tests/test_supply_chain_report_api.py -v
# 前端
cd apps/dsa-web && npx vitest run src/api/__tests__/supplyChainReports.test.ts src/hooks/__tests__/useSupplyChainReport.test.tsx src/pages/__tests__/SupplyChainReportPage.test.tsx
```

---

## 附：SemiAnalysis 检索增强（`search_semianalysis` 工具）

供应链分析对半导体/AI 主题新增 SemiAnalysis（semianalysis.com）一级研究源检索工具。

| 文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `tests/test_supply_chain_semianalysis_tool.py` | 23 | `_build_semianalysis_query`（site 前缀+关键词/strip/空关键词仅前缀/None）、`_pick_search_provider`（None service/无可用/首个可用/空列表）、`_handle_search_semianalysis`（无 provider→error / service None→error / 成功：results 含 url+date+provider、query 站点限定、days=365 透传、max_results 透传、source_note 含 analysis / 搜索失败→error / 异常→error / 长 snippet 截断 500 / 结果封顶 max_results）、工具元数据（注册/category=search/必填 keywords/max_results 默认 5/description 含 semianalysis+半导体）、prompt 规则（含 search_semianalysis + SemiAnalysis 检索规则 + HBM/CoWoS 触发词 + analysis + 付费墙 + 非半导体不必调用） |
| `tests/test_supply_chain_services.py`（更新） | 同文件既有用例 | `TestToolMetadata` 工具数断言 1→2（同步 `ALL_SUPPLY_CHAIN_TOOLS` 新增 `search_semianalysis`） |
| **小计新增** | **23** | 全部通过 |

**回归**：`test_supply_chain_services.py` + `test_supply_chain_e2e.py`（工具集 membership 断言，非精确计数→不破坏）+ `test_supply_chain_report_{storage,service,api}.py` + `test_policy_minesweeper_tools.py`（公告检索姊妹工具，未触碰）全绿，合计 **157 通过**。

**类型检查**：pyright / mypy 在新工具文件 `src/agent/tools/supply_chain_tools.py` **0 error**（pyright 在 `supply_chain.py`/`supply_chain_executor.py` 的 4 个 error 均为既有裸泛型 `Queue`/`dict`/`Callable` 与 sessions 响应构造，非本次新增，本次仅各加 1 行显示名/1 段 prompt 字符串）。

**复现**：

```bash
python -m pytest tests/test_supply_chain_semianalysis_tool.py tests/test_supply_chain_services.py -v
```

---

## 附 2：实时端到端测试（运行中的服务，最新代码）

启动方式：`.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000`（auth 关闭 `ADMIN_AUTH_ENABLED=false`、`AGENT_MODE=true`、Tavily 已配）。
地址：**http://localhost:8000**（`/supply-chain` 为表单式报告页）。

### A. 部署 E2E（curl 打运行中的服务，9/9 通过）
| 检查 | 期望 | 实测 |
| --- | --- | --- |
| `GET /`（前端） | 200 + index.html | ✅ 200，`<title>dsa-web</title>` |
| `GET /api/v1/health` | 200 `{"status":"ok"}` | ✅ 200 |
| `GET /api/v1/supply-chain/reports` | 200 空列表 | ✅ `{"success":true,"data":[],"total":0}` |
| `POST /generate/stream` 空 topic | 422（Pydantic） | ✅ 422 |
| `POST /generate/stream` 超长 topic(1001) | 422 | ✅ 422 |
| `GET /reports/sc_x/pdf`（非法 id） | 404（白名单） | ✅ 404 |
| `GET /reports/600519_...`（deep_research id） | 404（白名单拒绝） | ✅ 404 |
| `GET /reports/sc_202606271530_1`（合法格式无记录） | 404 | ✅ 404 |
| `GET /chat/sessions`（旧端点共存） | 200 | ✅ 200 |

### B. SemiAnalysis 工具真实网络 E2E（Tavily → semianalysis.com）
直接调用 `_handle_search_semianalysis(keywords)`，active provider = `TavilySearchProvider`，query=`site:semianalysis.com {kw}`：
- `HBM3E supply` → 3 条 `newsletter.semianalysis.com` 真实文章（Nvidia B100/GB200 COGS、AI Capacity Constraints CoWoS and HBM、Nvidia Plans To Crush Competition），含正确 `url`。
- `CoWoS capacity` → 3 条（AI Capacity Constraints、The Great AI Silicon Shortage、Advanced Packaging Part 2），含正确 `url`。
- ✅ 新工具确实检索到 semianalysis.com 一级研究文章。

### C. 报告全生命周期 E2E（`tests/test_supply_chain_report_e2e.py`，2 用例，桩 executor 不烧 LLM）
真实 service ↔ API ↔ SQLite ↔ md2pdf 串联：
- `TestExecutorToolComposition`：`build_supply_chain_executor` 工具集含 `search_semianalysis` + `score_supply_chain_bottleneck`。✅
- `TestReportLifecycleE2E`：SSE 生成（done 带 report_id/markdown/status + `search_semianalysis`→显示名「SemiAnalysis 检索」）→ 列表含新报告 → 详情读回 markdown → **PDF 惰性生成（weasyprint 渲染 138KB `%PDF`，二次请求复用）** → 删除后 404。✅

### D. 前端渲染 E2E（headless Chromium）
`http://localhost:8000/supply-chain` 渲染：标题「供应链分析报告」、左栏「历史报告」(暂无)、快捷主题按钮（A 股 AI 半导体供应链 / 光模块产业链瓶颈在哪 / 中际旭创是不是 CPO 核心卡点）、「生成报告」按钮、空态提示 + Serenity 9 步副标题；**控制台无错误**。截图：`/tmp/sc_report_page.png`。新页 chunk：`SupplyChainReportPage-*.js`（含「增加供应链线索」输入框）。

### 汇总
- 完整供应链测试套件：**128 通过**（services + e2e + semianalysis_tool + report storage/service/api + report_e2e）。
- 服务运行中：http://localhost:8000（健康）。
- 真实 LLM 端到端生成（5–15 分钟 agent 运行）未在本次执行（耗时/token）；全流程已由 C 的桩 executor 生命周期 E2E 覆盖，新 SemiAnalysis 工具已由 B 的真实网络检索验证。

---

## 附 3：PDF 宽表列宽塌缩修复（`md2pdf._PDF_CSS`）

**现象**：供应链报告 PDF 的宽多列表格（「线索验证」「核心标的」6 列长 CJK）表头/单元格被压成「1 字竖排」（`用\n户\n线\n索`），格式错误。深度投研报告 PDF 正常（其报告以散文+列表为主、几乎无宽表）。

**根因**：`formatters.markdown_to_html_document` 注入面向 web 的 `table { display: block; overflow-x: auto }`（GitHub 式横向滚动表格）。WeasyPrint 分页 PDF 不支持横向滚动，把表格渲染为块元素、列宽塌缩。`md2pdf._PDF_CSS` 此前未覆盖 `display`，故 web 样式生效。

**修复**（`src/md2pdf.py` `_PDF_CSS`，注入在 formatters `<style>` 之后、同优先级后者生效）：
```css
table { ...; display: table; table-layout: fixed; }      /* 覆盖 display:block，恢复表格布局；fixed 列宽均分 */
td, th { ...; vertical-align: top; word-break: break-word; overflow-wrap: anywhere; }  /* 长 CJK 在格内换行 */
```

**验证**：
- 真实报告 `reports/supply_chain/sc_202606271841_1.md` 经 `markdown_to_pdf_file` 重渲染，5 个表头（用户线索/验证状态/关键证据/来源强度/对结论的影响）作为完整 token 出现，无 1 字竖排，单元格长内容可提取。✅
- 运行中的服务（已重启加载修复）`GET /reports/sc_202606271841_1/pdf` 惰性重生成 433KB PDF，表格网格正常。✅
- 深度投研报告 `300003_*.md` 重渲染 739KB，内容完整、无乱码「煉」——**共享 renderer 无回归**。✅
- 新增 `tests/test_md2pdf.py` 两条回归：`test_wide_table_columns_not_collapsed`（6 列宽表不塌缩）+ `test_pdf_css_overrides_table_display_block`（CSS 契约）。`test_md2pdf.py` 共 **16 通过**；pyright/mypy `md2pdf.py` 0 error。

---

## 附 4：线索多源炒作检索（`search_clue_hype` 工具）

用户提供了「供应链线索」时，跨国内财经媒体加大搜索面，任一媒体提及即题材炒作加分项。

| 文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `tests/test_supply_chain_clue_hype_tool.py` | 26 | `_build_clue_hype_query`（有 site/无 site/strip/空/None）、`_hype_signal`（0无/1-2弱/3-4中/≥5强/None 负数）、`_handle_search_clue_hype`（无 provider→error；成功多源逐源检索+站点限定 query+每源 mention_count/sample url+mention_sources 聚合+total_mentions+hype_signal 分级+note；**单源异常其它源继续**；全源无命中→信号无；搜索失败源计 error/0；max_results_per_source 封顶+透传；days=180 透传）、工具元数据（注册/category=search/必填 clue/max_results 默认 3/description 含题材炒作+媒体名/源常量覆盖点名媒体）、prompt 规则（含 search_clue_hype+题材炒作信号+新浪/雪球/同花顺+hype_risk 联动+加分项） |
| `tests/test_supply_chain_services.py`（更新） | 同文件既有 | `TestToolMetadata` 工具数断言 2→3，names 加 `search_clue_hype` |
| **小计新增** | **26** | 全部通过 |

**真实网络 smoke**（Tavily 已配）：`_handle_search_clue_hype("新莱应材 新凯来 供应商")` 实测 5 源全部命中（新浪财经/雪球/同花顺/巨潮 cninfo/全网），`hype_signal="强"`，返回各源真实文章/PDF url（含巨潮「昆山新莱洁净应用材料股份有限公司」年报、新浪半导体「新凯来核心龙头企业」文）。

**回归**：services + e2e + semianalysis_tool + report_{storage,service,api,e2e} + policy_tools 全绿，合计 **184 通过**。pyright/mypy `supply_chain_tools.py` 0 error。

**复现**：
```bash
python -m pytest tests/test_supply_chain_clue_hype_tool.py -v
```

---

## 附 5：PDF `⚠️` emoji 乱码修复（`strip_emoji_for_pdf`）

**现象**：供应链报告下载 PDF 出现「大量乱码」（上一轮已修表格列宽塌缩）。本轮 pymupdf 渲染 + 字体/字形取证定位新根因。

**取证（确定性）**：嵌入字体 `苹果-简`(PingFang SC) / Semi-Bold / Oblique + `Apple-Color-Emoji`。逐字符 font 取证：`①②③④⑤`/`≤`/`μm`/`•` 全走 PingFang SC（正常）；**只有 `⚠️`(U+26A0+U+FE0F) 走 `Apple-Color-Emoji`**——WeasyPrint 无法把彩色 emoji 位图嵌入 PDF → 渲染成豆腐块（乱码）。报告里 3 个 `⚠️`（题材炒作信号/技术面快照的显著警告位）。列表 `<ol><li>` 良构、标记 bbox 在左边距（正常），表格上一轮已修。

**修复**（`src/services/supply_chain_report_service.py`，作用域仅供应链 PDF）：
- 纯函数 `strip_emoji_for_pdf` + `_EMOJI_STRIP_RE`：剥彩色 emoji（旗帜/补充平面象形/杂项符号☀-➿含⚠/补充象形A/变体选择符/ZWJ），保留 CJK/①②③/≤/μ/•/→/——。
- `_generate_pdf` 渲染前调 `strip_emoji_for_pdf(md 原文)`；`.md` 文件不动（Web/Markdown 视图仍显示 emoji）。

**验证**：
- 真实报告 `sc_202606280945_1` 重生成（删旧 PDF→服务惰性重渲染）：PDF 文本层**无 `⚠`**、警告正文「这是最关键的风险信号」保留、`①②③④⑤`/`≤`/`μm` 保留、**不再嵌入 `Apple-Color-Emoji` 字体**。✅
- 新增 `tests/test_supply_chain_report_pdf_emoji.py` **12 用例**（`strip_emoji_for_pdf` 纯函数 10：剥各类 emoji+VS+ZWJ、保留 CJK/符号/None/空、混合片段；渲染回归 2：`_generate_pdf` 对含 `⚠️` 的 md 生成无 `⚠` PDF + 正文保留、`.md` 原文不动）。
- 回归：`md2pdf`(16) + `supply_chain_report_{service,api,e2e}` + `supply_chain_clue_hype`/`semianalysis`/`services` 全绿，合计 **136 通过**（唯一失败为既有 `test_deep_research.py::_font_registered` 漂移，与本次无关）。pyright/mypy `supply_chain_report_service.py` 0 error。

**为什么不动共享 `md2pdf`**：作用域仅供应链 = 不影响深度投研/排雷 PDF（#4）；供应链的 emoji 由题材炒作信号新功能引入，在供应链层修最内聚。`.md` 原文不动 → Web 视图不受影响。

**复现**：
```bash
python -m pytest tests/test_supply_chain_report_pdf_emoji.py -v
```
