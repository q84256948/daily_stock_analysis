# PDF 生成统一方案（审计优化版）

> 状态：方案（待实施）  
> 关联：深度投研 / 政策与公告排雷 / 供应链分析 三处报告 PDF 下载  
> 原则：KISS、统一入口、少改调用方、真实回归验证

---

## 1. 审计结论

该方案方向合理：PDF 生成应该统一收敛到 `src/md2pdf.py`，并与邮件/通知 HTML formatter 解耦。当前代码已经证明两个关键问题仍存在：

- `src/md2pdf.py` 仍调用 `src.formatters.markdown_to_html_document`，而该 formatter 面向 web/邮件，包含 `table { display: block; overflow-x: auto }`、`:hover`、`max-width: 900px` 等不适合分页 PDF 的 CSS。
- 三个 PDF 下载端点当前 `FileResponse` 均未设置 `Cache-Control`，浏览器可能继续使用旧 PDF。

上一版方案需要调整的地方：

- 「所有 PDF 调用方」判断基本成立，但当前仓库已存在 `api/v1/endpoints/supply_chain_reports.py`、`src/services/supply_chain_report_service.py` 和相关测试，方案应按现状描述，不再把供应链报告端点当作待新增能力。
- 不应强调“service 零改动”。供应链 service 当前有本地 `strip_emoji_for_pdf`，统一方案应删除该局部逻辑并迁入 `md2pdf.py`。
- 不建议依赖 `pymupdf` 字形指纹作为必要验收；可作为人工取证，自动测试仍以文本、CSS 契约、响应头和端到端 PDF 生成 smoke 为主。
- `test_supply_chain_report_pdf_emoji.py` 可以保留并改向共享 `md2pdf.strip_emoji_for_pdf`，不必强制删除文件；更少测试 churn。

## 2. 目标

1. `src/md2pdf.py` 成为唯一 PDF HTML/CSS 渲染入口。
2. PDF 渲染不再复用 `formatters.markdown_to_html_document`。
3. 深度投研、政策与公告排雷、供应链三处 PDF 使用同一静态 HTML 模板和 PDF 专用 CSS。
4. 彩色 emoji 剥离下沉到共享渲染器，避免供应链局部补丁。
5. 三个 PDF 下载端点统一禁止浏览器缓存。
6. 保持 `markdown_to_pdf_file(markdown_text, output_path) -> Optional[str]` 公共契约不变。

## 3. 非目标

- 不更换为 pdfkit/wkhtmltopdf。
- 不改三个 service 的 PDF 调用协议。
- 不引入新的 HTML 模板引擎。
- 不改前端 PDF 下载逻辑。
- 不解决所有报告内容质量问题，例如 Agent 输出规划句、表格列过多、证据缺失；本方案只处理 PDF 渲染链路。

## 4. 当前代码基线

当前共享渲染器：

- `src/md2pdf.py`
- 依赖：`markdown2>=2.4.0`、`weasyprint>=60.0`
- 现状：`markdown_to_pdf_file` 内部调用 `markdown_to_html_document(markdown_text)`，再把 `_PDF_CSS` 插入 `</head>` 前。

当前 PDF 调用方：

- `src/services/deep_research_service.py`
- `src/services/policy_minesweeper_service.py`
- `src/services/supply_chain_report_service.py`

当前 PDF 下载端点：

- `api/v1/endpoints/deep_research.py`
- `api/v1/endpoints/policy_minesweeper.py`
- `api/v1/endpoints/supply_chain_reports.py`

当前供应链局部补丁：

- `src/services/supply_chain_report_service.py::_generate_pdf` 在调用 `markdown_to_pdf_file` 前执行 `strip_emoji_for_pdf(...)`。
- `tests/test_supply_chain_report_pdf_emoji.py` 覆盖该局部剥离逻辑。

## 5. 根因

### 5.1 PDF 复用 web/邮件 CSS

`src.formatters.markdown_to_html_document` 是通用 HTML formatter，适合邮件、通知和 Web 风格展示，但不适合分页 PDF。典型冲突：

```css
body { max-width: 900px; margin: 0 auto; }
table { display: block; overflow-x: auto; }
tr:hover { background-color: #f1f8ff; }
pre { overflow: auto; }
```

这些规则在浏览器里用于横向滚动和交互 hover，但 WeasyPrint 生成分页 PDF 时没有横向滚动语义，宽表容易列宽塌缩、断行异常或视觉错乱。

### 5.2 emoji 局部修补位置不对

供应链报告单独剥 emoji 能缓解 `⚠️`、`📈` 等彩色 emoji 在 PDF 中的 tofu 方块问题，但问题不属于供应链业务层。其他报告未来也可能输出 emoji，因此应下沉到共享 PDF 渲染器。

### 5.3 PDF 端点缺 no-store

三个端点的 `FileResponse` 没有禁用缓存。对同一 URL：

```text
/api/v1/.../reports/{report_id}/pdf
```

浏览器或中间层可能复用旧 PDF，导致服务端修复后用户仍看到旧文件。

## 6. 设计方案

### 6.1 保留 WeasyPrint

继续使用 WeasyPrint，不使用 pdfkit：

- 当前项目已接入 WeasyPrint。
- `requirements.txt` 已有 `weasyprint>=60.0`。
- pdfkit 依赖 `wkhtmltopdf` 系统二进制，而项目历史已经从 wkhtmltopdf 路径迁出。
- 保留 `_prepare_weasyprint_env`、`_pdf_lock`、`_PDF_LOCK_TIMEOUT`。

### 6.2 md2pdf 改为静态 HTML 模板

`src/md2pdf.py` 不再导入：

```python
from src.formatters import markdown_to_html_document
```

改为直接使用 `markdown2.markdown(...)` 生成 body 片段：

```python
body = markdown2.markdown(
    strip_emoji_for_pdf(markdown_text),
    extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
)
html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>{_PDF_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""
```

安全边界保持不变：

- 不传 `base_url`。
- 不加载远程资源。
- 输入仍是系统生成的 markdown。

### 6.3 PDF 专用 CSS

`_PDF_CSS` 改成纯 CSS 字符串，不包含 `<style>` 标签，避免拼装混乱。

要求：

```css
@page { margin: 20mm 18mm; }
body {
  font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif;
  font-size: 11pt;
  line-height: 1.6;
  color: #222;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  table-layout: auto;
}
td, th {
  border: 1px solid #999;
  padding: 5px 8px;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
  word-break: break-word;
}
th { background-color: #f0f0f0; font-weight: bold; }
pre {
  background-color: #f6f8fa;
  padding: 8px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
code { font-family: inherit; }
blockquote { border-left: 3px solid #ccc; padding-left: 10px; color: #555; }
ul, ol { padding-left: 22px; }
a { color: #0645ad; text-decoration: none; }
```

明确禁止：

- `display: block` 用在 table。
- `overflow-x: auto`。
- `:hover`。
- `max-width: 900px`。

表格不强制 `table-layout: fixed`。上一轮 fixed 是为了覆盖 web CSS 的局部补丁；静态 PDF 模板已经没有 web CSS 冲突，默认用 `auto` 更符合内容驱动布局。若真实宽表仍不理想，再用专项测试决定是否对 `table-layout` 做局部调整。

### 6.4 emoji 剥离下沉

在 `src/md2pdf.py` 新增：

```python
def strip_emoji_for_pdf(text: Optional[str]) -> str: ...
```

处理规则：

- 剥离彩色 emoji、变体选择符 `U+FE00-FE0F`、ZWJ 组合中的 emoji。
- 保留 CJK、圈号数字 `①②③`、数学符号 `≤ ≥`、单位 `μm`、项目符号 `•`、箭头 `→`、破折号。
- None 返回空字符串。

`markdown_to_pdf_file` 内部先调用 `strip_emoji_for_pdf(markdown_text)`。

供应链 service 删除本地 `strip_emoji_for_pdf` 和 `_EMOJI_STRIP_RE`，`_generate_pdf` 改回直接读取 markdown：

```python
markdown = md_path.read_text(encoding="utf-8")
result_path = markdown_to_pdf_file(markdown, pdf_path)
```

### 6.5 三端点统一 no-store

三个 PDF 端点 `FileResponse` 增加：

```python
headers={
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
```

影响文件：

- `api/v1/endpoints/deep_research.py`
- `api/v1/endpoints/policy_minesweeper.py`
- `api/v1/endpoints/supply_chain_reports.py`

## 7. 改动范围

| 文件 | 改动 |
| --- | --- |
| `src/md2pdf.py` | 移除 `markdown_to_html_document` 依赖；使用 `markdown2.markdown` + PDF 专用 HTML/CSS；新增共享 `strip_emoji_for_pdf`；保留 `markdown_to_pdf_file`、锁、env 准备和失败返回 None 契约。 |
| `src/services/supply_chain_report_service.py` | 删除本地 emoji 剥离逻辑；PDF 生成前不再改写 markdown，由 `md2pdf` 统一处理。 |
| `api/v1/endpoints/deep_research.py` | PDF `FileResponse` 增加 no-store headers。 |
| `api/v1/endpoints/policy_minesweeper.py` | 同上。 |
| `api/v1/endpoints/supply_chain_reports.py` | 同上。 |
| `tests/test_md2pdf.py` | 增加/调整静态模板、CSS 契约、emoji 剥离、宽表、CJK 保留、失败降级测试。 |
| `tests/test_supply_chain_report_pdf_emoji.py` | 改为验证供应链 service 不再局部剥离，同时共享 `strip_emoji_for_pdf` 仍生效；或将纯函数用例迁到 `test_md2pdf.py` 后删除本文件。二选一，优先选择改造保留以减少 churn。 |
| `tests/test_pdf_endpoints_cache.py` | 新增三端点 PDF 响应头测试，mock service，不真实渲染 PDF。 |
| `docs/CHANGELOG.md` | 记录 PDF 渲染器统一、emoji 下沉、PDF no-store。 |
| `docs/supply-chain-report-test-report.md` | 更新供应链 PDF 相关测试说明，移除“仅供应链层修复”的旧结论。 |

## 8. 测试要求

### 8.1 md2pdf 单元测试

覆盖：

- 空 markdown 返回 None。
- weasyprint import 失败返回 None。
- WeasyPrint 渲染异常返回 None。
- 父目录不存在时自动创建。
- semaphore 获取超时返回 None。
- `_prepare_weasyprint_env` macOS 路径逻辑不回归。
- `strip_emoji_for_pdf` 剥离 `⚠️ 📈 🔥 ✅ 🎯`，保留 `新莱应材 ①②③ ≤ μm • → ——`。
- 生成 PDF 后文本包含 CJK、列表、代码块、表格内容。
- 宽表表头不被拆成单字竖排。
- `_PDF_CSS` 不包含 `display: block`、`overflow-x: auto`、`:hover`、`max-width: 900px`，并包含 CJK 字体栈和表格基础样式。

### 8.2 endpoint 缓存测试

新增 `tests/test_pdf_endpoints_cache.py`：

- deep research PDF 响应头包含 `Cache-Control: no-store`。
- policy minesweeper PDF 响应头包含 `Cache-Control: no-store`。
- supply chain PDF 响应头包含 `Cache-Control: no-store`。

测试方式：

- 裸 FastAPI app 挂对应 router。
- mock service `get_report` / `get_pdf_path`。
- 用临时目录创建 fake PDF。
- 不跑真实 WeasyPrint。

### 8.3 service 回归

覆盖：

- `SupplyChainReportService._generate_pdf` 直接读取 markdown 原文并调用 `markdown_to_pdf_file`。
- 成功后回写 `set_supply_chain_pdf_path`。
- `.md` 原文不被修改。
- deep research / policy minesweeper 现有 PDF service 测试不需要大改。

### 8.4 人工验证

真实验证建议：

```bash
python -m pytest tests/test_md2pdf.py tests/test_pdf_endpoints_cache.py \
  tests/test_supply_chain_report_service.py tests/test_supply_chain_report_api.py \
  tests/test_policy_minesweeper_api.py -v

python -m py_compile src/md2pdf.py src/services/supply_chain_report_service.py \
  api/v1/endpoints/deep_research.py \
  api/v1/endpoints/policy_minesweeper.py \
  api/v1/endpoints/supply_chain_reports.py
```

如本地具备 WeasyPrint 系统库，再手工执行：

1. 删除一份旧供应链报告的 `.pdf`。
2. 请求 `/api/v1/supply-chain/reports/{id}/pdf` 重新生成。
3. 确认响应头含 `Cache-Control: no-store`。
4. 打开 PDF 检查宽表、中文、代码块、列表和 emoji 方块。

`pymupdf` 渲染截图或字形取证只作为排障工具，不作为必需 CI。

## 9. 风险与取舍

### 深度投研和排雷 PDF 视觉会变化

统一渲染器会让三类报告使用同一 PDF 样式。视觉细节可能与之前不同，但这是统一方案的预期影响。内容契约不变。

### emoji 会从 PDF 中消失

彩色 emoji 主要是装饰或风险提示符号。PDF 中剥离它们，保留文字信息。Web/Markdown 原文不受影响。

### 表格仍可能过宽

PDF 页面宽度有限。静态模板能避免 web CSS 冲突，但不能保证任意超宽表都完美。第一阶段先使用 `table-layout: auto` + `overflow-wrap: anywhere`，真实报告若仍不佳，再考虑特定报告模板压缩列数。

### no-store 会增加重复下载成本

PDF 文件本身仍会在服务端复用 `pdf_path`，no-store 只要求浏览器回源，不会每次重新渲染。成本可接受。

## 10. 回滚方式

- 恢复 `src/md2pdf.py` 到当前实现。
- 恢复供应链 service 的本地 emoji 剥离。
- 移除三个端点的 no-store headers。
- 删除或回滚新增的 `test_pdf_endpoints_cache.py`。

公共函数签名不变，回滚不会影响业务 API。

## 11. 推荐实施顺序

1. 改 `src/md2pdf.py`：静态 HTML、PDF CSS、共享 emoji 剥离。
2. 改 `src/services/supply_chain_report_service.py`：删除局部 emoji 剥离。
3. 三个 PDF 端点增加 no-store headers。
4. 更新 `tests/test_md2pdf.py` 和供应链 emoji 测试。
5. 新增 `tests/test_pdf_endpoints_cache.py`。
6. 跑后端回归和 py_compile。
7. 更新 `docs/CHANGELOG.md`、`docs/supply-chain-report-test-report.md`。

## 12. 相关文件索引

- 渲染器：`src/md2pdf.py`
- 共享 HTML formatter：`src/formatters.py`
- 调用方 service：`src/services/deep_research_service.py`、`src/services/policy_minesweeper_service.py`、`src/services/supply_chain_report_service.py`
- 下载端点：`api/v1/endpoints/deep_research.py`、`api/v1/endpoints/policy_minesweeper.py`、`api/v1/endpoints/supply_chain_reports.py`
- 测试：`tests/test_md2pdf.py`、`tests/test_supply_chain_report_pdf_emoji.py`、`tests/test_supply_chain_report_api.py`、`tests/test_policy_minesweeper_api.py`

