# -*- coding: utf-8 -*-
"""Markdown 转 PDF 工具（深度投研报告专用）。

用 **xhtml2pdf + reportlab CID 字体** 纯 Python 渲染，不依赖任何系统二进制
（wkhtmltopdf/wkhtmltoimage 已于 2023 年停止维护，且 Homebrew 6.0+ 移除了
``wkhtmltopdf`` formula，导致 macOS 本地 PDF 下载 404）。

设计要点：
1. **纯 Python**：``pip install`` 即用，macOS / Linux / Docker 全平台一致，无需
   安装系统级 Qt/WebKit 或字体文件。
2. **CJK 零字体文件**：reportlab 内置 ``UnicodeCIDFont('STSong-Light')``（Adobe
   Asian CID 字体），通过 ``pdfmetrics.registerFont`` 注册 + CSS ``font-family``
   引用解决中文渲染。注意：xhtml2pdf 默认无 CJK（输出全是方块），``@font-face``
   嵌入 ttf/ttc 对 CJK 不可靠——必须走 reportlab CID 注册路径。
3. **模块级 ``threading.Semaphore(1)``** 限并发，保留原防 OOM 语义。
4. ``markdown_to_pdf_file()`` → 文件路径（惰性生成），而非返回 bytes。

失败语义：依赖缺失或渲染异常时返回 ``None``，不抛异常，由调用方（service 层）处理
降级为 HTTP 404，不影响报告生成主流程。

用法（endpoint）：
    path = await asyncio.to_thread(markdown_to_pdf_file, markdown_text, output_path)
    if path:
        return FileResponse(path, ...)

Security note: markdown_to_html_document 产出固定结构 HTML，经 xhtml2pdf 渲染为
PDF（reportlab 输出），不执行外部脚本。输入为系统生成的投研报告，非原始用户输入。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from src.formatters import markdown_to_html_document

logger = logging.getLogger(__name__)

# 单进程并发限流（保留原防 OOM 语义；xhtml2pdf 同步渲染，避免并发拖垮内存）
# 注：同一时刻只有 1 个 PDF 在生成；其他请求排队（os.stat 不阻塞）。
_pdf_lock = threading.Semaphore(1)

# reportlab 内置 Adobe CJK CID 字体（STSong-Light = 简体中文宋体）。
# 零外部字体文件，跨平台一致；幂等注册（重复注册 reportlab 自动忽略）。
_CJK_FONT_NAME = "STSong-Light"
_font_registered = False

# CJK 友好的 PDF 样式：全标签覆盖 CID 字体 + 表格边框 + 合理字号/行距。
# 覆盖范围必须包含 td/th/li/blockquote 等所有文本节点，否则对应标签回退默认字体出方块。
_PDF_CSS = """
<style>
body, p, td, th, li, h1, h2, h3, h4, h5, h6, blockquote, span, div, strong, em {
    font-family: '%s';
    font-size: 11pt;
    line-height: 1.6;
}
h1 { font-size: 18pt; }
h2 { font-size: 15pt; }
h3 { font-size: 13pt; }
table { border-collapse: collapse; width: 100%%; margin: 8px 0; }
td, th { border: 1px solid #999; padding: 4px 8px; text-align: left; }
th { background-color: #f0f0f0; font-weight: bold; }
blockquote { border-left: 3px solid #ccc; padding-left: 10px; color: #555; }
code, pre { font-family: 'STSong-Light'; }
</style>
""" % _CJK_FONT_NAME


def _ensure_cjk_font() -> None:
    """幂等注册 reportlab CID 字体（模块级只注册一次）。"""
    global _font_registered
    if _font_registered:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT_NAME))
    _font_registered = True


def markdown_to_pdf_file(markdown_text: str, output_path: str) -> Optional[str]:
    """将 Markdown 转为 PDF 文件（xhtml2pdf + reportlab CID 字体）。

    Args:
        markdown_text: Markdown 原文（utf-8）。
        output_path: PDF 输出文件路径（完整路径，函数内部不创建目录）。

    Returns:
        ``output_path``（成功）或 ``None``（失败/依赖缺失）。
        失败时返回 None，不抛异常，调用方处理降级。
    """
    if not markdown_text or not markdown_text.strip():
        logger.warning("[md2pdf] 空 Markdown，跳过")
        return None

    # 确保父目录存在（reports/deep_research/ 子目录首次写入）
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # ---------- Semaphore 限流 ----------
    acquired = _pdf_lock.acquire(timeout=5.0)
    if not acquired:
        logger.warning("[md2pdf] Semaphore 获取超时（PDF 生成队列满），跳过")
        return None

    try:
        # ---------- lazy import xhtml2pdf / reportlab ----------
        try:
            _ensure_cjk_font()
            from xhtml2pdf import pisa
        except ImportError:
            logger.warning("[md2pdf] xhtml2pdf/reportlab 未安装，PDF 生成跳过")
            return None

        # ---------- Markdown → HTML（复用 md2img 同源格式化器）→ 注入 CJK CSS ----------
        html = markdown_to_html_document(markdown_text)
        if "</head>" in html:
            html = html.replace("</head>", _PDF_CSS + "</head>", 1)
        else:
            html = _PDF_CSS + html

        # ---------- 渲染 ----------
        with open(output_path, "wb") as f:
            result = pisa.CreatePDF(html, dest=f, encoding="utf-8")

        if not result.err and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(
                "[md2pdf] 生成成功: %s (%.1f KB)",
                output_path,
                os.path.getsize(output_path) / 1024,
            )
            return output_path

        logger.warning("[md2pdf] xhtml2pdf 渲染失败或输出无效: err=%s", getattr(result, "err", "?"))
        # 清理可能产生的空/坏文件，避免后续误判已生成
        try:
            if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
                os.remove(output_path)
        except OSError:
            pass
        return None

    except Exception as exc:
        logger.warning("[md2pdf] PDF 生成失败: %s", exc)
        return None

    finally:
        _pdf_lock.release()
