# 知识库功能优化方案

## 1. 审计结论

原方案方向成立：DSA 需要一个用户可维护的私有知识库，用于沉淀 PDF、Markdown、文本、网页等材料，并在供应链分析、深度投研等 AI 报告中作为可引用的补充证据。

但原方案存在四类问题，需要先收敛：

| 问题 | 影响 | 优化方向 |
| --- | --- | --- |
| 一次性引入 ChromaDB、PDF 解析、网页解析、前端状态、会话管理等完整栈 | 实施面过大，新增依赖和测试成本高 | P0 先做可用闭环，P1 再接向量库 |
| 将知识库定义为“最高优先级”数据源 | 容易覆盖公告、行情、双源校验等更权威来源 | 改为“用户提供材料优先召回，但事实等级低于公告/交易所/结构化数据” |
| 大段代码示例未校验现有依赖和路径 | 容易误导实现，后续代码与实际仓库漂移 | 文档只定义契约、边界、目录和测试矩阵 |
| URL 抓取和 PDF 解析缺少安全边界 | 存在 SSRF、超大文件、恶意 PDF、版权与隐私风险 | 明确文件大小、URL allow/deny、超时、来源标注和 fail-open |

本方案将知识库拆成两个层级：

1. **P0：本地私有资料库 + 关键词检索闭环**  
   使用 SQLite 元数据 + SQLite FTS5 文本索引，先支持上传文本/Markdown/PDF 文本提取结果、检索、引用、删除、报告集成。
2. **P1：向量 RAG 增强**  
   只有当 P0 召回质量不够时，再引入 ChromaDB 或其他向量库；Embedding 通过 LiteLLM，但必须新增显式配置和降级路径。

## 2. 功能定位

知识库不是“事实真源”，而是“用户私有证据库”。

在报告生成中的优先级建议如下：

| 优先级 | 来源 | 使用方式 |
| --- | --- | --- |
| P0 | 交易所公告、巨潮公告、上市公司公告、定期报告 | 可作为确认事实 |
| P1 | 东方财富、同花顺、iFinD、AkShare 等结构化数据 | 可作为行情/财务/板块数据依据，需保留口径 |
| P2 | 用户知识库 | 可作为用户提供证据、历史材料、行业资料、访谈纪要引用 |
| P3 | 公开新闻、社区、研报摘要 | 只能作为线索或市场分歧 |
| P4 | LLM 推断 | 只能作为待核验判断 |

因此报告中引用知识库内容时必须标注：

- 文档标题
- 来源类型
- 上传时间或原始 URL
- 命中片段
- 是否已被公告/结构化数据交叉验证

## 3. 范围边界

### 3.1 P0 必做

- 文档来源：
  - 纯文本输入
  - Markdown 上传
  - PDF 上传后的文本提取
  - URL 保存为来源链接，网页抓取可作为 best-effort
- 文档管理：
  - 新增
  - 列表
  - 删除
  - 重新索引
- 检索：
  - SQLite FTS5 关键词召回
  - 股票代码、股票名称、行业、主题标签过滤
  - 返回可引用片段
- 报告集成：
  - 供应链分析可调用 `search_knowledge_base`
  - A 股深度投研可调用 `search_knowledge_base`
  - 命中内容进入报告“用户知识库参考”小节
  - 未命中不阻断报告生成

### 3.2 P0 不做

- 不做多用户权限体系。
- 不做复杂聊天会话历史。
- 不把知识库内容自动覆盖结构化数据。
- 不引入 ChromaDB 作为首版强依赖。
- 不新增独立前端状态库，优先复用现有 API/hook/page 模式。

### 3.3 P1 再做

- ChromaDB / 向量库。
- Embedding 批处理队列。
- 混合检索：FTS + 向量召回 + rerank。
- 知识库问答独立页面。
- 文档版本、chunk 命中统计、召回质量评估。

## 4. 数据模型

### 4.1 SQLite 表

建议新增两张表，沿用现有 SQLite 管理方式，避免 P0 引入第二套存储。

`knowledge_documents`

| 字段 | 说明 |
| --- | --- |
| `id` | 文档 ID，建议 `kb_YYYYMMDDHHMMSS_x` |
| `title` | 文档标题 |
| `source_type` | `text` / `markdown` / `pdf` / `url` |
| `source_url` | URL 来源，可为空 |
| `file_path` | 本地文件路径，可为空 |
| `content_hash` | 内容 hash，用于去重 |
| `tags` | JSON 字符串，股票/行业/主题标签 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |
| `deleted_at` | 软删除时间，可为空 |

`knowledge_chunks`

| 字段 | 说明 |
| --- | --- |
| `id` | chunk ID |
| `document_id` | 所属文档 |
| `chunk_index` | 顺序 |
| `content` | 片段正文 |
| `token_estimate` | 估算 token 数 |
| `metadata` | JSON 字符串 |

同时创建 FTS5 虚拟表：

```sql
CREATE VIRTUAL TABLE knowledge_chunks_fts
USING fts5(content, document_id UNINDEXED, chunk_id UNINDEXED);
```

### 4.2 Pydantic 契约

按仓库“类型-契约-数据三层防御”规则，API 请求/响应使用 Pydantic v2：

- `KnowledgeDocumentCreate`
- `KnowledgeDocumentItem`
- `KnowledgeChunkHit`
- `KnowledgeSearchRequest`
- `KnowledgeSearchResponse`

输入边界：

- `title`：1-120 字符
- `content`：1-200000 字符
- `url`：仅允许 `http` / `https`
- `tags`：单项 1-40 字符，最多 20 个
- `top_k`：1-20

## 5. 后端设计

### 5.1 建议目录

```text
api/v1/endpoints/knowledge.py
src/schemas/knowledge_base.py
src/services/knowledge_base_service.py
src/services/knowledge_base_parser.py
src/agent/tools/knowledge_base_tools.py
tests/test_knowledge_base_*.py
```

保持文件数少一点，P0 不拆 `processor/embedder/storage/retriever` 四层。等向量化进入 P1 后再拆。

### 5.2 API

建议路由前缀：`/api/v1/knowledge-base`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/documents/text` | 新增文本/Markdown 内容 |
| `POST` | `/documents/upload` | 上传 PDF/Markdown/文本文件 |
| `POST` | `/documents/url` | 保存并抓取 URL |
| `GET` | `/documents` | 文档列表 |
| `GET` | `/documents/{document_id}` | 文档详情 |
| `DELETE` | `/documents/{document_id}` | 删除文档和索引 |
| `POST` | `/search` | 知识库检索 |

P0 不需要独立 `/chat/stream`。已有报告 Agent 已经能生成文本，知识库先作为工具接入，避免另做一套聊天系统。

### 5.3 文档解析

| 类型 | P0 处理 | 失败行为 |
| --- | --- | --- |
| text | 直接切分 | 空内容 422 |
| markdown | 读取 UTF-8 文本，保留标题结构 | 解析失败 400 |
| pdf | 使用已安装或新增的最小 PDF 文本提取库 | 失败时文档不入库 |
| url | 超时抓取正文文本，保存 URL | 抓取失败时可只保存 URL + 待抓取状态 |

限制：

- 单文件默认不超过 20MB。
- 单文档文本默认不超过 200000 字符。
- URL 抓取超时 10 秒。
- 禁止内网地址、localhost、file 协议，避免 SSRF。
- 解析出的内容必须保存原始来源和时间。

### 5.4 检索逻辑

P0 使用简单混合打分即可：

1. FTS5 按 query 召回。
2. 股票代码、股票名称、行业、主题标签加权。
3. 最近更新文档轻微加权。
4. 返回 top_k 片段。

返回结果必须包含：

- `document_id`
- `document_title`
- `source_type`
- `source_url`
- `chunk_id`
- `content`
- `score`
- `created_at`

### 5.5 Agent 工具

新增一个共享工具即可：

`search_knowledge_base(query: str, stock_code: str | None = None, stock_name: str | None = None, top_k: int = 5)`

工具行为：

- 知识库不可用时返回 `available=false`，不抛异常。
- 无命中时返回空结果和说明。
- 命中内容只作为“用户知识库参考”，不能自动写成已确认事实。
- 报告引用时必须附文档标题和片段。

优先接入：

1. 供应链分析报告。
2. A 股深度投研报告。
3. 政策与公告排雷。

## 6. 前端设计

### 6.1 页面入口

新增 `/knowledge-base` 页面，侧边栏放在供应链分析附近。

P0 页面只需要三个区域：

1. 上传/新增资料。
2. 文档列表。
3. 检索预览。

不做独立知识库聊天页。原因是报告 Agent 已经承担问答和生成能力，P0 更需要先把“资料入库、可检索、可引用”做稳。

### 6.2 交互要求

- 上传后显示解析状态、chunk 数、内容 hash。
- 文档列表支持按标题、标签、来源类型筛选。
- 删除前二次确认。
- 检索预览显示命中文档和片段。
- URL 文档必须展示原始 URL。
- PDF 解析失败时显示明确错误，不静默成功。

## 7. 配置与依赖

### 7.1 P0 配置

新增配置项时同步 `.env.example`：

```env
KNOWLEDGE_BASE_ENABLED=true
KNOWLEDGE_BASE_MAX_FILE_MB=20
KNOWLEDGE_BASE_MAX_CHARS=200000
KNOWLEDGE_BASE_URL_TIMEOUT=10
KNOWLEDGE_BASE_MAX_RESULTS=5
```

### 7.2 依赖策略

P0 只允许新增真正必要的 PDF/HTML 解析依赖。

| 能力 | 优先方案 |
| --- | --- |
| 元数据存储 | 现有 SQLite |
| 文本检索 | SQLite FTS5 |
| Markdown | 直接按文本处理 |
| URL 抓取 | 优先复用现有网络工具；没有再用 `requests` |
| PDF 文本提取 | 选一个轻量依赖，失败即提示 |
| 向量库 | P1 再评估 ChromaDB |
| Embedding | P1 通过 LiteLLM，需显式模型配置 |

P1 如引入向量库，再补：

```env
KNOWLEDGE_BASE_VECTOR_ENABLED=false
KNOWLEDGE_BASE_EMBEDDING_MODEL=text-embedding-3-small
KNOWLEDGE_BASE_VECTOR_TOP_K=8
```

## 8. 报告集成规则

### 8.1 供应链分析

触发条件：

- 用户输入包含具体公司、行业、产业链主题。
- 知识库已启用且有文档。

报告新增小节：

```text
## 用户知识库参考

| 文档 | 片段摘要 | 用途 | 校验状态 |
| --- | --- | --- | --- |
```

校验状态：

- `已被公告/结构化数据验证`
- `与公开数据存在冲突`
- `仅用户资料支持`
- `待核验`

### 8.2 A 股深度投研

知识库用于补充：

- 公司历史调研纪要
- 产业链上下游资料
- 国产替代材料
- 客户/供应商线索
- 竞争格局材料

不得用于直接确认：

- 实时股价
- 财务数据
- 板块成分
- 公告事实
- 监管处罚

这些仍需走现有结构化数据、公告检索和双源校验。

## 9. 安全与合规

- 上传内容默认本地私有存储。
- 不把用户文档原文写入日志。
- 不在错误信息中暴露本地绝对路径。
- URL 抓取必须禁止内网地址：
  - `127.0.0.0/8`
  - `10.0.0.0/8`
  - `172.16.0.0/12`
  - `192.168.0.0/16`
  - `localhost`
  - `file://`
- 报告中引用知识库时保留来源，避免把用户上传材料伪装成公开事实。
- 删除文档时同步删除 chunk、FTS 索引和本地文件。

## 10. 测试矩阵

| 层级 | 测试 |
| --- | --- |
| Parser | 文本、Markdown、PDF 解析成功/失败、超大文件拒绝 |
| Storage | 新增、去重、删除、软删除、FTS 索引同步 |
| Search | top_k、标签过滤、股票代码过滤、无结果、特殊字符 query |
| API | 422 输入校验、上传、删除、检索、URL SSRF 拒绝 |
| Agent Tool | 知识库不可用 fail-open、无命中、命中引用字段完整 |
| 报告集成 | 供应链/深度投研命中知识库后正确落入“用户知识库参考” |
| 前端 | 上传、列表、删除、检索预览、错误展示 |

最低验证：

```bash
python -m pytest tests/test_knowledge_base_*.py
python -m pytest -m "not network"
cd apps/dsa-web && npm run lint && npm run build
```

## 11. 实施计划

### Phase 0：契约与存储

- 新增 Pydantic schema。
- 新增 SQLite 表和 FTS5 索引。
- 新增 service：新增、删除、检索。
- 新增 parser：文本、Markdown、PDF 基础解析。
- 新增后端单测。

### Phase 1：页面与工具

- 新增 `/knowledge-base` 页面。
- 新增文档上传、列表、删除、检索预览。
- 新增 `search_knowledge_base` 工具。
- 接入供应链分析和 A 股深度投研。
- 报告输出“用户知识库参考”。

### Phase 2：URL 与质量护栏

- URL 抓取 best-effort。
- SSRF 防护。
- 来源可信度标注。
- 文档重新索引。
- 检索命中统计。

### Phase 3：向量 RAG

只有当关键词召回不足时执行：

- 引入 ChromaDB 或同类向量库。
- 新增 Embedding 配置。
- 支持 FTS + 向量混合召回。
- 增加召回质量评测集。

## 12. 回滚方案

- 配置 `KNOWLEDGE_BASE_ENABLED=false` 后关闭页面入口和 Agent 工具。
- 保留数据库表，不影响既有报告。
- Agent 工具 fail-open，知识库异常不阻断供应链、深度投研、排雷报告。
- 若向量库 P1 出现问题，可退回 SQLite FTS5 检索。

