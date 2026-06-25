# -*- coding: utf-8 -*-
"""Markdown 转 PDF 工具（深度投研报告专用）。

用 **WeasyPrint**（HTML/CSS → PDF，基于 Pango/Cairo）渲染。相比旧 xhtml2pdf +
reportlab CID 字体方案，正确处理：
- ``<ul><li>`` 项目符号（修复旧方案 bullet 渲染成 "煉" 的 CID CMap 错位）
- ``<pre>`` 代码块（修复旧方案 CJK 代码块整片黑条的 ``<pre>`` 元素级 bug）
- emoji / 箭头 / 表格（标准 CSS 兼容，旧方案多变为方框或错位汉字）

依赖：
- ``pip install weasyprint``
- 系统库：pango / cairo / glib / gdk-pixbuf
  - macOS：``brew install pango cairo gdk-pixbuf glib``（本模块自动探测 brew lib 路径，
    用户无需手动配置 ``DYLD_FALLBACK_LIBRARY_PATH``）
  - Linux/Debian：``apt-get install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    libglib2.0-0 fonts-noto-cjk``

设计要点：
1. **接口契约不变**：``markdown_to_pdf_file(markdown_text, output_path) -> Optional[str]``，
   成功返回 ``output_path``，失败/依赖缺失返回 ``None``（不抛异常），由 service 层降级为
   HTTP 404，不影响报告生成主流程。
2. **CJK 字体回退链**：跨平台 CSS font-family（macOS 苹方 / Linux Noto / 文泉 / 雅黑）。
3. **模块级 ``threading.Semaphore(1)``** 限并发（WeasyPrint 渲染 CPU/内存密集），保留防 OOM 语义。
4. 复用 ``formatters.markdown_to_html_document`` 生成 HTML，惰性生成 PDF 文件。

用法（endpoint）：
    path = await asyncio.to_thread(markdown_to_pdf_file, markdown_text, output_path)
    if path:
        return FileResponse(path, ...)

Security note: 输入为系统生成的投研报告 markdown，经 markdown2 → HTML → WeasyPrint 渲染，
不执行外部脚本；构造 HTML 时不传 base_url，不加载远程资源。
"""

from __future__ import annotations

import logging
import os
import platform
import threading
from typing import Optional

from src.formatters import markdown_to_html_document

logger = logging.getLogger(__name__)

# 单进程并发限流（WeasyPrint 渲染 CPU/内存密集，同进程串行避免 OOM）。
# 注：同一时刻只有 1 个 PDF 在生成；其他请求排队。
_pdf_lock = threading.Semaphore(1)

# Semaphore 获取超时秒数（提为常量，便于测试注入小值覆盖超时分支）。
_PDF_LOCK_TIMEOUT = 5.0

# macOS Homebrew glib 动态库候选路径（Apple Silicon / Intel）。
_BREW_LIB_CANDIDATES = ("/opt/homebrew/lib", "/usr/local/lib")
# 判定 brew glib 是否存在的标记文件（WeasyPrint 经 cffi 加载 libgobject）。
_GOBJECT_MARKER = "libgobject-2.0.0.dylib"

# CJK 字体回退链：macOS PingFang/Hiragino，Linux Noto/Source Han/文泉/雅黑，最后 sans-serif。
# 保证不同平台都能正确渲染中文；PDF 嵌入字体子集后外观稳定。
_PDF_FONT_STACK = (
    '"PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", '
    '"Source Han Sans SC", "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif'
)

# CJK 友好的 PDF 样式：全标签覆盖字体回退链 + 表格边框 + 合理字号/行距。
# 覆盖范围包含 td/th/li/blockquote/pre/code 等所有文本节点。
# CSS 的 { } 需转义为 {{ }} 以走 str.format。
_PDF_CSS = """
<style>
body, p, td, th, li, h1, h2, h3, h4, h5, h6, blockquote, span, div, strong, em, pre, code {{
    font-family: {fonts};
    font-size: 11pt;
    line-height: 1.6;
}}
h1 {{ font-size: 18pt; }}
h2 {{ font-size: 15pt; }}
h3 {{ font-size: 13pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
td, th {{ border: 1px solid #999; padding: 4px 8px; text-align: left; }}
th {{ background-color: #f0f0f0; font-weight: bold; }}
blockquote {{ border-left: 3px solid #ccc; padding-left: 10px; color: #555; }}
pre {{ background-color: #f6f8fa; padding: 8px; border-radius: 3px; white-space: pre-wrap; word-wrap: break-word; }}
code {{ font-family: {fonts}; }}
</style>
""".format(fonts=_PDF_FONT_STACK)


def _prepare_weasyprint_env() -> None:
    """macOS 下自动把 Homebrew 的 glib 动态库路径加入 dyld 搜索路径。

    WeasyPrint 经 cffi 加载 ``libgobject-2.0-0``；macOS 上 brew 安装的库不在系统
    dyld 默认搜索路径内，需 ``DYLD_FALLBACK_LIBRARY_PATH`` 指向 ``/opt/homebrew/lib``
    （Apple Silicon）或 ``/usr/local/lib``（Intel），否则报
    ``cannot load library 'libgobject-2.0-0'``。本函数幂等探测并设置，让用户免手动
    配置环境变量；非 macOS 无副作用；找不到 brew 路径时静默返回（后续 import 给出明确错误）。
    """
    if platform.system() != "Darwin":
        return
    current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    existing = current.split(":") if current else []
    for candidate in ("/opt/homebrew/lib", "/usr/local/lib"):
        if not os.path.exists(os.path.join(candidate, "libgobject-2.0.0.dylib")):
            continue
        if candidate in existing:
            return
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            f"{candidate}:{current}" if current else candidate
        )
        return


def markdown_to_pdf_file(markdown_text: str, output_path: str) -> Optional[str]:
    """将 Markdown 转为 PDF 文件（WeasyPrint 渲染）。

    Args:
        markdown_text: Markdown 原文（utf-8）。
        output_path: PDF 输出文件路径（完整路径；父目录不存在时自动创建）。

    Returns:
        ``output_path``（成功）或 ``None``（空输入 / 依赖缺失 / 渲染失败）。
        失败时不抛异常，调用方（service 层）处理降级为 HTTP 404。
    """
    if not markdown_text or not markdown_text.strip():
        logger.warning("[md2pdf] 空 Markdown，跳过")
        return None

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # ---------- Semaphore 限流 ----------
    acquired = _pdf_lock.acquire(timeout=5.0)
    if not acquired:
        logger.warning("[md2pdf] Semaphore 获取超时（PDF 生成队列满），跳过")
        return None

    try:
        # ---------- macOS 环境自适应 + lazy import weasyprint ----------
        _prepare_weasyprint_env()
        try:
            from weasyprint import HTML
        except Exception as exc:  # ImportError / cffi 加载 libgobject 失败的 OSError 等
            logger.warning("[md2pdf] weasyprint 未就绪（%s），PDF 生成跳过", exc)
            return None

        # ---------- Markdown → HTML（复用 md2img 同源格式化器）→ 注入 CJK CSS ----------
        html = markdown_to_html_document(markdown_text)
        if "</head>" in html:
            html = html.replace("</head>", _PDF_CSS + "</head>", 1)
        else:
            html = _PDF_CSS + html

        # ---------- 渲染（不传 base_url，避免加载远程资源） ----------
        HTML(string=html).write_pdf(output_path)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(
                "[md2pdf] 生成成功: %s (%.1f KB)",
                output_path,
                os.path.getsize(output_path) / 1024,
            )
            return output_path

        logger.warning("[md2pdf] WeasyPrint 渲染输出无效（空文件）")
        return None

    except Exception as exc:
        logger.warning("[md2pdf] PDF 生成失败: %s", exc)
        return None

    finally:
        _pdf_lock.release()
