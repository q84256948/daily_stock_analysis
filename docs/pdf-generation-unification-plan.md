# PDF 生成统一方案（简单静态 HTML → WeasyPrint）

> 状态：方案（待实施）　·　关联：深度投研 / 政策与公告排雷 / 供应链分析 三处报告 PDF 下载
>　·　参考基线：`6fe5aed`（main 最新，其 PDF 生成对深度投研可用）
>　·　原则：KISS、高内聚低耦合、新代码 100% 测试、不影响无关功能

---

## 1. 背景与目标

供应链分析报告「下载 PDF」连续被反馈「乱码 / 格式错误」，历经两次症状级修补（表格列宽覆盖、供应链层 emoji 剥离）仍未解决。用户要求：**把所有 PDF 生成统一换成「直接把 HTML 生成 PDF：简单静态 HTML、轻量快速（pdfkit / WeasyPrint）」**，并以 `6fe5aed` 为可用参考。

目标：
1. 建立一个**统一的、内容无关的** PDF 渲染器，任何报告（窄表/宽表/emoji/代码块/`<br>` 单元格）都能稳定渲染。
2. 切断 PDF 对「邮件/通知共用 HTML 格式化器」的耦合（根因之一）。
3. 消除「服务端修复后用户仍看到旧乱码」的缓存放大因。
4. 深度投研 / 政策排雷 / 供应链三处 PDF 走同一渲染器，零差异。

## 2. 现状与症状

- 全仓**所有 PDF 生成只有一个函数**：`src/md2pdf.py::markdown_to_pdf_file`（WeasyPrint）。
  - 调用方：`deep_research_service._generate_pdf` / `policy_minesweeper_service._generate_pdf` / `supply_chain_report_service._generate_pdf`。
  - 下载端点：`api/v1/endpoints/{deep_research,policy_minesweeper,supply_chain_reports}.py::download_pdf`。
- 现行链路：`md → formatters.markdown_to_html_document(md) → 注入 _PDF_CSS → WeasyPrint → PDF`。
- 症状：深度投研 PDF 正常；供应链 PDF「乱码、格式错误」，两次修补后用户仍反馈「还是乱码」。

## 3. 根因分析（取证，非图像猜测）

### 3.1 git 取证：`6fe5aed` 与 `HEAD` 在 PDF 链路上的差异
- `git diff 6fe5aed HEAD -- src/md2pdf.py`：**唯一差异**是本会话的「表格列宽」补丁（`table{display:table;table-layout:fixed}`）。`src/formatters.py`、`deep_research_service.py` 自 `6fe5aed` 起**未变**。
- 即：`6fe5aed`（可用参考）的 PDF 方案 = 当前方案 − 该补丁。基线本身就是 WeasyPrint + `formatters.markdown_to_html_document` + `_PDF_CSS`。

### 3.2 结构根因：PDF 复用「邮件 formatter」的 web CSS
`formatters.markdown_to_html_document` 与邮件/通知（notification）**共用**，注入的是**面向 web/邮件**的样式：
```
table { display: block; overflow-x: auto; }   /* GitHub 式横向滚动 */
tr:hover { background-color: #f1f8ff; }
body { max-width: 900px; ... }
```
- `display:block` 表格在 WeasyPrint（分页 PDF，无横向滚动）下会把宽表列宽压塌、表头压成单字竖排。
- 深度投研报告（散文为主、表格窄、基本无 emoji）**容忍**了这套 web CSS，故 `6fe5aed`「正常」。
- 供应链报告（**宽多列表格 + 单元格内 `<br>` + ⚠️ 彩色 emoji + 偶发泄漏的规划句**）触发冲突 → 列塌缩 / emoji 豆腐块。
- 既有的表格 `table-layout` 覆盖、供应链层 `strip_emoji` 是**症状级补丁**，未消除「PDF 复用邮件 HTML」这一耦合。

### 3.3 字体层取证（pymupdf）
- 供应链 PDF 嵌入 `苹果-简`(PingFang SC) 子集，与「正常的」深度投研 PDF **同一字体子集**（相同子集前缀 `TELXQP+`/`NXYACE+`/`HJNUFM+`）。
- 逐字符 font 取证：`①②③④⑤` / `≤` / `μm` / `•` 全部走 PingFang SC（**正常**）；**仅 `⚠️`**(U+26A0 + U+FE0F) 走 `Apple-Color-Emoji`（彩色位图，WeasyPrint 无法嵌入 PDF → 豆腐块）。
- 文本层 Unicode 全程正确 → **`pypdf` 文本提取看不出视觉乱码**（这正是前几轮「验证通过」却仍乱码的原因——文本层正确不代表字形渲染正确）。

### 3.4 最强放大因：PDF 端点缺 `Cache-Control`
- 三个 PDF 下载端点的 `FileResponse` **均未设 `Cache-Control`**（已 grep 确认）。
- 浏览器对同一 URL `/api/v1/.../reports/{id}/pdf` 做启发式缓存 → **服务端修了、磁盘 PDF 重生成了，用户浏览器仍发旧缓存** →「修了三次还是乱码」。
- 与观察吻合：供应链（新报告、首份是坏的、被缓存）始终乱码；深度投研（缓存里本来就是好的）始终正常。

### 3.5 结论
根因是双重的：
- **① 结构耦合**：PDF 复用邮件 formatter 的 web CSS（`display:block` 表格 / `:hover` / `max-width`），对宽表/emoji 不稳。
- **② 缓存放大**：PDF 端点缺 `Cache-Control`，用户拿不到修复后的文件。

用户指示的「简单静态 HTML → WeasyPrint」治①；② 需配套加 `no-store`。

## 4. 方案设计

### 4.1 选型：WeasyPrint（**不**用 pdfkit）
- pdfkit 依赖 `wkhtmltopdf` 系统二进制；项目历史（`src/md2img.py` / `src/config.py` / `docs/CHANGELOG.md`）已记录 **macOS Homebrew 6.0+ 无 `wkhtmltopdf` formula**，曾因此从 imgkit/wkhtmltopdf 迁出。pdfkit 在当前部署环境不可行。
- WeasyPrint 已集成、`6fe5aed` 即用之、依赖（pango/cairo/glib）已装；保留 `_prepare_weasyprint_env`（macOS `DYLD_FALLBACK_LIBRARY_PATH` 自适应）与信号量限流。

### 4.2 核心：专用 PDF HTML 模板，解耦邮件 formatter
重写 `src/md2pdf.py`（原地重写，保留公共契约与内部符号，最小化测试 churn）：

1. **HTML 构造改用 markdown2 直出 body 片段**，不再走 `formatters.markdown_to_html_document`：
   ```python
   body = markdown2.markdown(md, extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"])
   html = "<!DOCTYPE html><html><head><meta charset='utf-8'>" + _PDF_CSS + "</head><body>" + body + "</body></html>"
   ```
2. **`_PDF_CSS` 改为 PDF 专用干净 CSS（无任何 web-ism）**：
   - CJK 字体栈（`PingFang SC` / `Hiragino Sans GB` / `Noto Sans CJK SC` / … / `sans-serif`）；
   - 表格**原生** `display:table`（天然，**无 `display:block` 可冲突**）+ `table-layout:auto`（内容驱动列宽，宽表自然分布）+ `td,th{vertical-align:top;overflow-wrap:anywhere;word-break:break-word}`；
   - `@page{margin:20mm 18mm}`、标题/列表/代码块/引用/链接样式；
   - **不含** `display:block`、`overflow-x:auto`、`:hover`、`max-width:900px`。
3. **彩色 emoji 剥离下沉到渲染器**（`strip_emoji_for_pdf` + `_EMOJI_STRIP_RE`）：剥彩色 emoji（旗帜/补充平面象形/杂项符号 `☀-➿` 含 ⚠/补充象形/变体选择符 `U+FE00-FE0F`/ZWJ），**保留** CJK / `①②③④⑤` / `≤` / `μm` / `•` / `→` / `——`。对所有 PDF 生效（深度投研 PDF 也曾有 `Apple-Color-Emoji`，统一受益）。
4. **公共契约不变**：`markdown_to_pdf_file(markdown_text, output_path) -> Optional[str]`（成功返回路径，失败返回 None，fail-open → service 层 404）+ `_pdf_lock` 信号量 + `_prepare_weasyprint_env` + `_PDF_LOCK_TIMEOUT` 等内部符号保留。**三个 service 零改动（drop-in）**。

### 4.3 配套：消除缓存放大因
三个 PDF 端点的 `FileResponse` 统一加响应头：
```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
```
强制浏览器每次回源，拿到重生成的 PDF。

### 4.4 收尾：去掉症状级补丁
- `supply_chain_report_service.py`：删 `strip_emoji_for_pdf` / `_EMOJI_STRIP_RE`，`_generate_pdf` 还原为 `markdown = md_path.read_text(...)`（emoji 现由渲染器统一处理）。
- `md2pdf._PDF_CSS`：去掉之前加的 `display:table;table-layout:fixed` 覆盖补丁（新模板原生表格，无需覆盖邮件 CSS）。

## 5. 改动范围（文件）

| 文件 | 改动 |
|---|---|
| `src/md2pdf.py` | 原地重写：markdown2 直出 body → 极简静态 HTML + 干净 `_PDF_CSS`（原生表格、无 web-ism）→ `strip_emoji_for_pdf` 剥彩色 emoji → WeasyPrint。保留 `markdown_to_pdf_file` 公共契约 + `_pdf_lock` + `_prepare_weasyprint_env` + 各常量。移除 `from src.formatters import markdown_to_html_document`。 |
| `src/services/supply_chain_report_service.py` | 删 `strip_emoji_for_pdf` / `_EMOJI_STRIP_RE`；`_generate_pdf` 还原直接读 md（emoji 由渲染器处理）。 |
| `api/v1/endpoints/deep_research.py` | `download_pdf` 的 `FileResponse` 加 `Cache-Control: no-store, no-cache, must-revalidate` + `Pragma: no-cache` + `Expires: 0`。 |
| `api/v1/endpoints/policy_minesweeper.py` | 同上。 |
| `api/v1/endpoints/supply_chain_reports.py` | 同上。 |
| `tests/test_md2pdf.py` | 更新：新模板渲染（宽表表头完整、彩色 emoji 剥离、CJK/`①②③`/`≤`/`μm`/`•` 保留）；CSS 契约（**不含** `display:block`/`overflow-x:auto`/`:hover`、含原生 `table` + 字体栈）；既有 `bullet/code/emoji/table/complex/semaphore/env` 用例适配。 |
| `tests/test_supply_chain_report_pdf_emoji.py` | 移除（emoji 剥离迁到渲染器，用例并入 `test_md2pdf.py`，测试用例不丢失）。 |
| `tests/test_pdf_endpoints_cache.py`（新） | 三端点 PDF 响应头 `Cache-Control: no-store` 断言。 |
| `docs/CHANGELOG.md` / `docs/supply-chain-report-test-report.md` | 记录统一渲染器 + no-store + emoji 下沉。 |

> 三处 service 的 `_generate_pdf` 调用点 **不变**（仍是 `markdown_to_pdf_file(md, out)`）；深度投研 / 排雷 service 文件**无需改动**。

## 6. 关键设计契约

```python
# src/md2pdf.py（重写后对外契约保持）
def markdown_to_pdf_file(markdown_text: str, output_path: str) -> Optional[str]: ...
def strip_emoji_for_pdf(text: Optional[str]) -> str: ...   # 新增（从 supply_chain service 迁入）
# 保留：_pdf_lock, _PDF_LOCK_TIMEOUT, _prepare_weasyprint_env,
#       _BREW_LIB_CANDIDATES, _GOBJECT_MARKER, _PDF_FONT_STACK, _PDF_CSS（干净版）
```

`_PDF_CSS` 要点（PDF 专用，无 web-ism）：
```css
@page { margin: 20mm 18mm; }
body { font-family: "PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","WenQuanYi Micro Hei","Microsoft YaHei",sans-serif; font-size: 11pt; line-height: 1.6; color: #222; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }            /* 原生 display:table */
td, th { border: 1px solid #999; padding: 5px 8px; text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }
th { background-color: #f0f0f0; font-weight: bold; }
ul, ol { padding-left: 22px; }   h2 { border-bottom: 1px solid #ddd; }   pre/code/blockquote/hr/a { ... }
```

## 7. 验证方案

- **单元（`tests/test_md2pdf.py`）**：渲染器输出 PDF；`⚠️` 剥离、`新莱应材/①②③④⑤/≤/μm/•/→/——` 保留；宽表（6 列）表头完整（文本提取）；CSS **不含** `display:block`/`overflow-x:auto`/`:hover`、含 `table` 与字体栈；空输入/依赖缺失/渲染异常 fail-open（返回 None）；信号量超时返回 None；父目录自动创建。
- **端点（`tests/test_pdf_endpoints_cache.py`，新）**：三端点 PDF 响应头含 `Cache-Control: no-store`（service 层 mock，无真实渲染）。
- **集成**：三个 service 仍生成 PDF（drop-in 不变）；`pyright` / `mypy` 改动文件 0 error。
- **真实重生（人工/脚本）**：重启服务 → 删供应链旧 PDF → `GET /reports/{id}/pdf` 重生 → `pypdf` 文本干净（无 `⚠`）；`pymupdf` 渲染 PNG 做「字符指纹多样性」tofu 烟雾测试（多样性正常、无单一豆腐块指纹压倒）；响应头含 `no-store`。
- **前端**：`apps/dsa-web` 无改动（PDF 下载走后端）；`npm run lint && npm run build` 仅确认无回归。
- **回归命令**：
  ```bash
  python -m pytest tests/test_md2pdf.py tests/test_pdf_endpoints_cache.py \
    tests/test_supply_chain_report_service.py tests/test_supply_chain_report_e2e.py \
    tests/test_deep_research.py tests/test_policy_minesweeper_api.py -v
  python -m py_compile src/md2pdf.py src/services/supply_chain_report_service.py \
    api/v1/endpoints/deep_research.py api/v1/endpoints/policy_minesweeper.py api/v1/endpoints/supply_chain_reports.py
  ```

## 8. 风险与回滚

- **影响面**：渲染器为三 feature 共用，统一重写同时改变深度投研/排雷 PDF 视觉（更干净的模板、彩色 emoji 被剥）——这是「所有 PDF 统一」的预期效果；CJK 与表格**内容**不变。
- **macOS WeasyPrint 依赖**：保留 `_prepare_weasyprint_env`（`DYLD_FALLBACK_LIBRARY_PATH` 指向 `/opt/homebrew/lib`）；服务进程启动时需该 env（用户 shell profile 通常已配；服务实测可用——供应链/深度投研 PDF 现已在产）。注意：在进程启动**后**才 `os.environ[...]` 设置 DYLD 对当前进程的 `dlopen` 无效（dyld 在启动时读取），故服务需在已带该 env 的 shell 下启动。
- **回滚**：还原 `src/md2pdf.py` + 三端点响应头 + `supply_chain_report_service` 的 emoji 剥离；删 `tests/test_pdf_endpoints_cache.py`。零功能影响（公共契约未变）。

## 9. 决策与取舍

| 决策点 | 选择 | 理由 |
|---|---|---|
| 渲染引擎 | **WeasyPrint** | 已集成、`6fe5aed` 即用；pdfkit/wkhtmltopdf 在 macOS Homebrew 6.0+ 无 formula（项目历史已迁出） |
| HTML 来源 | **markdown2 直出 body**，弃 `formatters.markdown_to_html_document` | 切断与邮件 formatter 的 web CSS 耦合（根因①），消除 `display:block` 表格冲突 |
| 表格布局 | **原生** `display:table` + `table-layout:auto` | 无 web CSS 可冲突；内容驱动列宽，宽表自然分布 |
| emoji 处理 | **渲染器内剥离彩色 emoji**（下沉） | WeasyPrint 无法嵌入彩色位图；装饰性 emoji 剥离、信息性字符全保留；三 feature 统一受益 |
| 缓存 | **`Cache-Control: no-store`** 三端点 | 消除「修复后仍看旧缓存」放大因（根因②） |
| 改动粒度 | **原地重写 `md2pdf.py`**（不新增 `pdf_renderer.py`） | 保留公共契约与内部符号，最小化测试 churn；少一个文件 |
| service 层 | **零改动**（drop-in） | 公共契约不变；emoji 从供应链 service 移除（统一到渲染器） |

## 10. 实施顺序

1. 重写 `src/md2pdf.py`（干净 HTML + CSS + emoji 剥离 + WeasyPrint，保留契约/信号量/env）。
2. 三端点 `download_pdf` 加 `Cache-Control: no-store` 等响应头。
3. `supply_chain_report_service` 去 emoji 剥离（`_generate_pdf` 还原）。
4. 改/加测试（`test_md2pdf.py` 更新 + `test_pdf_endpoints_cache.py` 新增；移除 `test_supply_chain_report_pdf_emoji.py`，用例并入）。
5. 重启服务 → 删旧供应链 PDF → 重生成 → 取证验证；`pyright`/`mypy` + 回归。
6. `docs/CHANGELOG.md` + `docs/supply-chain-report-test-report.md`。

## 11. 附录：取证命令（可复现）

```bash
# 1) 确认 6fe5aed 与 HEAD 的 md2pdf 差异（仅表格补丁）
git diff 6fe5aed HEAD -- src/md2pdf.py

# 2) 字体/字形取证（需 pymupdf）
.venv/bin/python -c "
import fitz
doc = fitz.open('reports/supply_chain/<report_id>.pdf')
print([f[3] for f in doc.get_page_fonts(0)])           # 嵌入字体（苹果-简 = PingFang SC）
for b in doc[0].get_text('dict')['blocks']:
    for l in b['lines']:
        for s in l['spans']:
            t = s['text']
            for ch in t:
                if ch in '①②③④⑤⚠≤μ•':
                    print(repr(ch), '->', s['font'])    # 逐字符 font（⚠ 走 Apple-Color-Emoji = 豆腐块）
"

# 3) PDF 端点缺 Cache-Control 确认
grep -n "FileResponse" api/v1/endpoints/deep_research.py api/v1/endpoints/policy_minesweeper.py api/v1/endpoints/supply_chain_reports.py
```

## 12. 相关文件索引

- 渲染器：`src/md2pdf.py`（重写）
- 调用方 service：`src/services/deep_research_service.py`、`src/services/policy_minesweeper_service.py`、`src/services/supply_chain_report_service.py`
- 下载端点：`api/v1/endpoints/{deep_research,policy_minesweeper,supply_chain_reports}.py`
- 历史/依赖：`src/md2img.py`、`src/config.py`（`MD2IMG_ENGINE`）、`docs/CHANGELOG.md`（imgkit→xhtml2pdf→WeasyPrint 迁移记录）
- 测试：`tests/test_md2pdf.py`、`tests/test_pdf_endpoints_cache.py`（新）
