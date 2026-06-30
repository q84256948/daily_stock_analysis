# PDF 下载文件名统一方案

目标：所有用户下载到本地的报告 PDF 使用业务可读文件名，例如：

```text
科瑞技术（002957）深度投研报告20260630.pdf
```

本方案只规划实现，不写代码。

## 现状审计

当前 PDF 文件名有两层控制：

- 后端 `FileResponse(..., filename=...)`
  - `api/v1/endpoints/deep_research.py`
  - `api/v1/endpoints/policy_minesweeper.py`
  - `api/v1/endpoints/supply_chain_reports.py`
- 前端 Blob 下载 `<a download>`
  - `apps/dsa-web/src/api/deepResearch.ts`
  - `apps/dsa-web/src/api/policyMinesweeper.ts`
  - `apps/dsa-web/src/api/supplyChainReports.ts`

因此只改后端不够，前端当前会用 `deep_research_${reportId}.pdf`、`policy_minesweeper_${reportId}.pdf`、`supply_chain_${reportId}.pdf` 覆盖后端文件名。

服务端缓存路径不建议改。现有 service 都基本使用 `md_path.with_suffix(".pdf")` 惰性生成，并把 `pdf_path` 存入 SQLite。这个路径用于复用、删除和 prune，保留 ASCII report id 更稳。

## 命名规则

单股报告：

```text
股票中文名（股票代码）报告类型YYYYMMDD.pdf
```

示例：

```text
科瑞技术（002957）深度投研报告20260630.pdf
科瑞技术（002957）政策与公告排雷报告20260630.pdf
```

日期使用报告 `created_at` 的日期，而不是下载当天。这样历史报告重复下载时文件名稳定，也符合“当前分析日期”的含义。

股票名为空时 fallback 到股票代码。文件名清理规则：

- 移除 `/ \ : * ? " < > |`
- 移除换行和控制字符
- 压缩连续空白
- 保留中文、数字、字母和中文括号 `（ ）`

## 供应链报告边界

供应链报告当前是主题型报告，`supply_chain_reports` 表没有 `stock_code` / `stock_name`，只有 `topic` / `research_hint` / `created_at`。因此不能可靠生成“股票中文名（代码）”。

阶段 1 建议使用主题型文件名：

```text
主题供应链分析报告YYYYMMDD.pdf
```

示例：

```text
A股AI半导体供应链供应链分析报告20260630.pdf
中际旭创是不是CPO核心卡点供应链分析报告20260630.pdf
```

不要从 `topic` 正则猜股票。若后续要求供应链报告也绑定单股，需要新增可选 `stock_code` / `stock_name` 字段、数据库迁移、前端表单/API 调整和历史 fallback。

## 后端方案

新增共享 helper：

```text
src/services/report_filename.py
```

建议函数：

```python
format_stock_report_pdf_filename(stock_name, stock_code, report_type_label, created_at) -> str
format_topic_report_pdf_filename(topic, report_type_label, created_at) -> str
```

报告类型：

| 报告 | label |
| --- | --- |
| 深度投研 | `深度投研报告` |
| 政策与公告排雷 | `政策与公告排雷报告` |
| 供应链分析 | `供应链分析报告` |

三个 PDF endpoint 当前已先读取报告元数据，再生成 PDF。可直接用元数据构造 `download_filename`，然后传给 `FileResponse(filename=download_filename)`。

服务端缓存 PDF 继续保留旧路径，例如：

```text
reports/deep_research/002957_202606301230.pdf
reports/policy_minesweeper/002957_202606301230.pdf
reports/supply_chain/sc_202606301230_1.pdf
```

## 前端方案

新增共享下载 helper：

```text
apps/dsa-web/src/api/download.ts
```

职责：

- 从 `Content-Disposition` 解析 `filename*=UTF-8''...`
- 兼容 `filename="xxx.pdf"` 和 `filename=xxx.pdf`
- 支持中文 decode
- 解析失败时使用 fallback
- 统一 Blob URL 创建、点击下载和 revoke

三个 API wrapper 改为复用该 helper，不再各自硬编码 `<a download>`。

fallback 仍可保留旧格式：

- `deep_research_${reportId}.pdf`
- `policy_minesweeper_${reportId}.pdf`
- `supply_chain_${reportId}.pdf`

## 测试计划

后端：

- 深度投研 PDF 响应头包含 `科瑞技术（002957）深度投研报告20260630.pdf`
- 政策与公告排雷 PDF 响应头包含 `科瑞技术（002957）政策与公告排雷报告20260630.pdf`
- 供应链阶段 1 响应头包含 `A股AI半导体供应链供应链分析报告20260630.pdf`
- 股票名缺失时 fallback 到代码
- `created_at` ISO 字符串只取 `YYYYMMDD`
- 非法文件名字符被清理
- 原有路径安全校验和 PDF 失败 404 不变

前端：

- 优先使用 `Content-Disposition: attachment; filename*=UTF-8''...`
- 兼容普通 `filename="xxx.pdf"`
- 无 header 时使用 fallback
- 中文文件名 decode 正确
- 三个 API wrapper 都走共享 helper

## 验证命令

```bash
python -m pytest tests/test_deep_research.py tests/test_policy_minesweeper_api.py tests/test_supply_chain_report_api.py -v
python -m py_compile src/services/report_filename.py api/v1/endpoints/deep_research.py api/v1/endpoints/policy_minesweeper.py api/v1/endpoints/supply_chain_reports.py

cd apps/dsa-web
npx vitest run src/api/__tests__/deepResearch.test.ts src/api/__tests__/policyMinesweeper.test.ts src/api/__tests__/supplyChainReports.test.ts
npm run build
```

## 风险与回滚

风险：

- 中文 `Content-Disposition` 在浏览器间表现不同，需要前端解析 `filename*=` 兜底。
- 前端如果继续硬编码 `a.download`，后端命名不会生效。
- 供应链报告不是天然单股报告，阶段 1 只能主题型命名。

回滚：

- 后端三个 endpoint 恢复旧 `filename`。
- 前端三个 API wrapper 恢复旧 `a.download`。
- 删除共享 helper 和测试。
- 服务端缓存文件名和 DB 不变，无需数据迁移。

## 最终建议

先实现深度投研和政策与公告排雷的单股命名；供应链报告先使用主题型命名。这样满足主要下载名诉求，同时避免为了主题型供应链报告新增数据库迁移和不可靠股票识别。
