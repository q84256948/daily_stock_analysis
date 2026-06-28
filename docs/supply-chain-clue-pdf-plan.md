# 供应链表单式分析、线索增强与 PDF 报告最终方案

## 审计结论

上一版方向正确：供应链分析应从聊天式体验升级为类似「A股深度投研报告」的表单式报告流，并把「增加供应链线索」作为本轮高优先级调查目标。

需要收敛和修正的点：

- **不能完全照搬深度投研的股票表单**：供应链分析既有主题扫描，也有单公司挑战。主输入应是「分析主题」，股票只是主题的一种写法。
- **第一阶段不需要复杂模式枚举**：`主题扫描/单公司挑战/候选对比/瓶颈打分` 可以先作为前端快捷模板或 prompt 语义，不必变成后端强契约字段。
- **PDF 应绑定报告记录，不应绑定聊天消息**：既然改为表单式报告，就需要 `supply_chain_reports` 元数据表，PDF 走报告惰性生成。
- **旧聊天端点要保留一段时间**：避免直接破坏已有会话、测试和外部调用方。新页面只走报告端点。
- **线索不能作为历史表单默认值恢复**：线索是一次性调查目标，历史报告可以展示当次线索，但重新生成必须由用户重新输入。
- **安全边界要明确**：`report_id` 白名单、路径收敛、PDF 生成失败文案、旧会话与新报告命名空间隔离都要写进实现要求。

## 目标

- 将 `/supply-chain` 主体验改造为表单式报告页面：表单输入 → SSE 生成 → 报告展示 → 历史报告 → PDF 下载。
- 新增「增加供应链线索」输入框，线索只对本次生成生效。
- 后端把线索作为高权重调查目标，围绕它搜索、验证、证伪和交叉印证。
- 最终报告必须包含「线索验证」小节，并将验证结果融合到供应链层级排序、候选标的、瓶颈分、风险和证伪条件中。
- 复用现有 `SupplyChainExecutor`、供应链工具集、SSE 进度事件和 `src/md2pdf.py`。
- 新增供应链报告历史、详情、删除和 PDF 惰性下载。

## 非目标

- 不做长期线索库、多线索管理、线索收藏。
- 不新增专用数据源，第一阶段继续复用现有行情、新闻、基本面、综合情报和瓶颈打分工具。
- 不改共享 `run_agent_loop`。
- 不新增配置项；报告保留数量第一阶段用 service 常量，后续确有需要再抽配置并同步 `.env.example`。
- 不把旧聊天会话迁移成报告历史。
- 不在第一阶段实现「基于报告继续追问」。

## 当前基线

- 当前供应链页面：`apps/dsa-web/src/pages/SupplyChainChatPage.tsx`
- 当前供应链 API：`apps/dsa-web/src/api/supplyChainChat.ts`
- 当前供应链 store：`apps/dsa-web/src/stores/supplyChainChatStore.ts`
- 当前后端端点：`api/v1/endpoints/supply_chain.py`
- 当前执行器：`src/agent/supply_chain_executor.py`
- PDF 工具：`src/md2pdf.py`
- 参考页面：`apps/dsa-web/src/pages/DeepResearchPage.tsx`
- 参考 hook：`apps/dsa-web/src/hooks/useDeepResearch.ts`
- 参考后端：`api/v1/endpoints/deep_research.py`
- 参考 service：`src/services/deep_research_service.py`
- 专题文档：`docs/supply-chain-research.md`

## 产品方案

### 页面布局

`/supply-chain` 保持路由不变，页面改为双栏报告式布局：

- 左栏：历史供应链报告列表，桌面常驻，移动端 Drawer。
- 右栏：表单、生成进度、错误提示、报告正文、报告操作。
- 报告正文使用现有 markdown 渲染能力，优先复用 `ReportMarkdownBody`。

### 表单字段

第一阶段只保留两个核心字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| 分析主题 | textarea | 是 | 例如「A 股 AI 半导体供应链」「光模块产业链瓶颈」「中际旭创是不是 CPO 核心卡点」 |
| 增加供应链线索 | textarea | 否 | 本轮临时线索，例如客户、供应商、订单、技术路线、产能、政策、公告关键词 |

暂不增加后端强约束的 `mode` 字段。原因：

- 现有 Serenity prompt 已能根据用户问题识别主题扫描、单公司挑战、候选对比、瓶颈打分。
- `mode` 会增加 API、测试、文档和未来兼容成本，但第一阶段收益有限。
- 如需引导用户，前端可以用快捷模板按钮填充「分析主题」，不需要改变后端契约。

### 线索规则

- 线索只随本次 `generate` 请求发送。
- 请求发出后清空线索输入框。
- 选择历史报告时可以展示该报告当时使用过的线索，但不回填到新表单。
- 重新生成时只保留分析主题，线索需要用户重新输入。
- 线索为空时生成行为与普通供应链报告一致。

### 报告操作

报告生成完成后支持：

- 下载 PDF。
- 复制 markdown。
- 删除历史报告。
- 基于同一主题重新生成。

## API 方案

新增报告式端点：

```http
POST   /api/v1/supply-chain/generate/stream
GET    /api/v1/supply-chain/reports
GET    /api/v1/supply-chain/reports/{report_id}
DELETE /api/v1/supply-chain/reports/{report_id}
GET    /api/v1/supply-chain/reports/{report_id}/pdf
```

旧聊天端点先保留：

```http
POST   /api/v1/supply-chain/chat
POST   /api/v1/supply-chain/chat/stream
GET    /api/v1/supply-chain/chat/sessions
GET    /api/v1/supply-chain/chat/sessions/{session_id}
DELETE /api/v1/supply-chain/chat/sessions/{session_id}
```

新页面只调用报告式端点。旧端点不进入新历史报告列表。

### 生成请求

```json
{
  "topic": "分析 A 股 AI 半导体供应链",
  "research_hint": "重点验证 CPO 光模块上游薄膜铌酸锂供应链"
}
```

约束：

- `topic` 必填，trim 后不能为空。
- `research_hint` 可选，trim 后为空则按无线索处理。
- `topic` 和 `research_hint` 都要限制最大长度，建议第一阶段：`topic <= 1000`，`research_hint <= 2000`。

### SSE 事件

沿用现有事件类型：

- `thinking`
- `tool_start`
- `tool_done`
- `generating`
- `heartbeat`
- `done`
- `error`

`done` 事件：

```json
{
  "type": "done",
  "success": true,
  "report_id": "sc_202606271530_1",
  "markdown": "...",
  "status": "success",
  "total_steps": 24,
  "total_tokens": 123456,
  "provider": "..."
}
```

状态值与现有报告类能力对齐，使用：

- `success`
- `partial`
- `failed`

## 后端方案

### 报告 service

新增 `src/services/supply_chain_report_service.py`，职责参考 `DeepResearchService`：

- 校验和规范化 `topic` / `research_hint`。
- 生成唯一 `report_id`。
- 组装本轮 prompt。
- 调用 `SupplyChainExecutor.chat(...)` 或新增轻量 `generate(...)` 包装。
- 将 markdown 写入 `reports/supply_chain/`。
- 保存报告元数据。
- 列表、详情、删除。
- PDF 惰性生成。
- 清理超额报告及对应 `.md` / `.pdf`。

报告目录：

```text
reports/supply_chain/
```

### report_id

建议格式：

```text
sc_{YYYYMMDDHHmm}_{seq}
```

示例：

```text
sc_202606271530_1
```

白名单：

```text
^sc_\d{12}_\d+$
```

不要把 topic slug 拼进 `report_id`。主题可能包含中文、空格、标点，进入路径后会增加安全和兼容成本。标题展示用 `topic` 字段即可。

### 存储表

新增 SQLAlchemy 模型 `SupplyChainReport`，表名 `supply_chain_reports`。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 报告 id |
| `topic` | 分析主题 |
| `research_hint` | 本次线索，可为空 |
| `created_at` | 创建时间 |
| `md_path` | markdown 文件路径 |
| `pdf_path` | PDF 文件路径，可为空 |
| `status` | `success` / `partial` / `failed` |
| `total_steps` | Agent 步数 |
| `total_tokens` | token 使用量 |
| `provider` | LLM provider |
| `model` | LLM model，可为空 |
| `error` | 失败原因，可为空 |

索引：

- `created_at`

第一阶段不解析供应链瓶颈分、候选股票、线索验证状态为结构化字段。报告正文是主契约，元数据只服务列表、详情、PDF 和删除。

### 内部 session

为复用现有 executor 和 conversation 基础设施，service 可使用内部 session id：

```text
supply_chain_report:{report_id}
```

注意：

- 新报告列表只读 `supply_chain_reports`，不读 conversation session。
- 旧聊天列表只读 `supply_chain:`，不会看到 `supply_chain_report:`。
- 删除报告时不强制删除内部 conversation，第一阶段可不处理；若要清理，必须只删 `supply_chain_report:{report_id}`，不能影响旧聊天会话。

### 线索注入

线索非空时，把用户输入包装成单条本轮用户消息：

```text
分析主题：
{topic}

高优先级供应链线索（只对本轮报告生效，不代表事实）：
{research_hint}

本轮必须围绕该线索执行：
1. 主动搜索公告、财报、新闻、行业资料、上下游公司信息。
2. 对关键说法至少做两类来源交叉验证；无法验证时标注“待核验”。
3. 同时寻找支持、冲突、证伪信息。
4. 把验证结果写入最终报告的“线索验证”部分。
5. 说明该线索如何影响供应链层级排序、候选标的、瓶颈分和风险判断。
```

线索为空时只发送：

```text
分析主题：
{topic}
```

### Prompt 增强

在 `src/agent/supply_chain_executor.py` 的 system prompt 增加规则：

- 用户线索是调查目标，不是事实。
- 线索优先级高于普通上下文，但低于工具证据。
- 必须查找支持、冲突、证伪信息。
- 对订单、客户、供应商关系、产能、市占率、政策影响等具体说法，必须标注来源强度。
- 不能因为用户提供线索就强行确认；证伪也是有效结论。
- 最终报告必须包含「线索验证」小节。

### 报告结构

最终 markdown 至少包含：

```markdown
# 供应链分析报告

## 一句话结论

## 产业链层级排序

## 候选标的与瓶颈分

## 线索验证

| 用户线索 | 验证状态 | 关键证据 | 来源强度 | 对结论的影响 |
| --- | --- | --- | --- | --- |

## 主要风险

## 证伪条件

## 下一步验证
```

线索验证状态限定：

- `已确认`
- `部分确认`
- `未找到可靠证据`
- `存在冲突`
- `已证伪`

如果没有线索，可以省略「线索验证」或写明「本次未提供额外线索」。

### PDF 生成

复用 `src.md2pdf.markdown_to_pdf_file`：

1. `GET /reports/{report_id}/pdf`。
2. 白名单校验 `report_id`。
3. 查询 `supply_chain_reports`。
4. `pdf_path` 存在且文件存在则直接返回。
5. 否则读取 `md_path`，生成同名 `.pdf`。
6. 生成成功后回写 `pdf_path`。
7. 返回 `FileResponse`。

路径安全：

- `md_path` / `pdf_path` resolve 后必须位于 `reports/supply_chain/`。
- 路径不合法按 404 处理，不暴露真实文件系统路径。

## 前端方案

### 文件结构

建议新增：

- `apps/dsa-web/src/api/supplyChainReports.ts`
- `apps/dsa-web/src/hooks/useSupplyChainReport.ts`

可以直接改造：

- `apps/dsa-web/src/pages/SupplyChainChatPage.tsx`

也可以新增 `SupplyChainPage.tsx` 后替换路由。为减少路由和菜单改动，推荐保留 `/supply-chain` 路由，页面组件内部换成报告式实现。

### API wrapper

```ts
export interface SupplyChainGenerateRequest {
  topic: string;
  research_hint?: string;
}
```

提供：

- `getReports(limit, offset)`
- `getReport(reportId)`
- `deleteReport(reportId)`
- `generateStream(payload, options)`
- `downloadPdf(reportId)`

下载实现复用 `deepResearchApi.downloadPdf` 的 fetch blob 模式。

### Hook

`useSupplyChainReport` 参考 `useDeepResearch`：

- `idle -> generating -> done | error`
- 支持 `AbortController`
- 支持 30s heartbeat 和 90s watchdog
- SSE 正常结束但没有 done/error 时提示用户去历史列表查看
- done 后返回 `reportId` 和 markdown

### 页面状态

核心状态：

```ts
const [topic, setTopic] = useState('');
const [researchHint, setResearchHint] = useState('');
const [history, setHistory] = useState([]);
const [currentDetail, setCurrentDetail] = useState(null);
const [pdfLoading, setPdfLoading] = useState(false);
```

提交规则：

- `topic.trim()` 为空时提示。
- `researchHint.trim()` 非空才传。
- 生成开始后清空 `researchHint`。
- `topic` 保留，方便重新生成。
- 生成完成后刷新历史列表。

历史报告：

- 列表展示 topic、created_at、status、是否有 PDF。
- 详情展示 markdown。
- 点击历史报告不回填 `researchHint`。

## 测试方案

### 后端

新增：

- `tests/test_supply_chain_report_service.py`
- `tests/test_supply_chain_storage.py`

扩展或新增：

- `tests/test_supply_chain_api.py`

覆盖：

- `topic` 为空返回 400/422。
- `research_hint` 为空时不注入线索段。
- 带线索时 executor 收到线索调查指令。
- SSE done 返回 `report_id`、`markdown`、`status`。
- markdown 落盘成功后保存元数据。
- 报告列表按时间倒序。
- 报告详情读取 markdown。
- 删除报告同步删除元数据并 best-effort 删除 `.md` / `.pdf`。
- PDF 惰性生成成功、复用已有 PDF、渲染失败。
- `report_id` 路径穿越被拒绝。
- 旧 chat 端点仍可用。

### 前端

新增：

- `apps/dsa-web/src/api/__tests__/supplyChainReports.test.ts`
- `apps/dsa-web/src/hooks/__tests__/useSupplyChainReport.test.ts`

页面测试覆盖：

- topic 必填。
- research hint 随请求发送。
- 发送后清空 research hint。
- topic 保留。
- 历史报告加载、选中、删除。
- PDF 下载按钮调用正确 API。
- SSE error 展示错误。

## 文档更新

需要同步：

- `docs/supply-chain-research.md`
- `docs/CHANGELOG.md`

不更新 `README.md`。这是专题功能细节，不是首页级能力介绍。

## 验证命令

后端：

```bash
python -m pytest tests/test_supply_chain_report_service.py tests/test_supply_chain_storage.py tests/test_supply_chain_api.py tests/test_supply_chain_services.py
python -m py_compile api/v1/endpoints/supply_chain.py src/agent/supply_chain_executor.py src/services/supply_chain_report_service.py
```

PDF：

```bash
python -m pytest tests/test_md2pdf.py
```

前端：

```bash
cd apps/dsa-web
npm run lint
npm run build
```

## 分期实施

### P0：报告式后端闭环

- 新增 `SupplyChainReport` 存储模型和 CRUD。
- 新增 report service。
- 新增 `/generate/stream` 和 reports CRUD/PDF 端点。
- 保留旧 chat 端点。
- 补后端测试。

### P1：表单式前端

- 新增 API wrapper 和 hook。
- 将 `/supply-chain` 页面切到表单式报告流。
- 接入历史报告、详情、删除和 PDF 下载。
- 补前端测试。

### P2：线索质量增强

- 强化 prompt 中的线索验证规则。
- 优化报告模板中的「线索验证」小节。
- 根据真实样例调整工具调用策略。

### P3：后续可选能力

- 基于报告继续追问。
- 专用公告/招投标/专利/环评数据源。
- 结构化提取候选标的、瓶颈分、线索验证状态。
- 配置化报告保留数量。

## 风险与处理

### 聊天式改为表单式影响旧用户

风险：已有用户依赖多轮追问。

处理：旧 chat 端点保留；页面主路径切换为报告流。后续确有需求再做「基于报告追问」。

### 供应链主题不是单股票

风险：照搬深度投研会把供应链研究做窄。

处理：主字段使用「分析主题」，不强制股票选择。

### 线索污染后续报告

风险：上一轮线索被误用于下一轮。

处理：线索只在本次 generate payload 中传递，发送后清空，不回填历史线索。

### 用户线索错误

风险：Agent 被错误线索带偏。

处理：prompt 明确线索是调查目标，不是事实；报告必须展示支持、冲突、证伪和待核验。

### 存储与旧会话混杂

风险：旧 `supply_chain:` 会话和新报告历史混在一起。

处理：新报告只读 `supply_chain_reports`；内部 session 使用 `supply_chain_report:` 前缀。

### PDF 路径穿越

风险：report_id 或路径拼接不安全。

处理：report_id 白名单 + resolve 后校验在 `reports/supply_chain/` 内。

### 生成失败但有部分内容

风险：长任务中途失败，用户拿不到已生成内容。

处理：service 接受 `partial` 状态；只要有 markdown 就落盘并可在历史中查看。

## 回滚方式

- 前端 `/supply-chain` 路由切回 `SupplyChainChatPage`。
- 后端保留旧 chat 端点即可恢复原供应链聊天功能。
- 停用或删除新 reports 端点。
- 新表 `supply_chain_reports` 与旧会话隔离，回滚不影响旧聊天数据。
- 删除 `reports/supply_chain/` 下新生成的 `.md` / `.pdf` 即可清理新产物。

## 推荐实施顺序

1. 新增存储模型和 service。
2. 新增报告式 API 和 PDF 下载。
3. 支持 `research_hint` 注入与 prompt 线索验证规则。
4. 补后端测试。
5. 新增前端 API wrapper 和 hook。
6. 改造 `/supply-chain` 页面为表单式报告流。
7. 补前端测试。
8. 更新 `docs/supply-chain-research.md` 和 `docs/CHANGELOG.md`。

