# -*- coding: utf-8 -*-
"""md2pdf 单元测试。

覆盖 ``markdown_to_pdf_file`` 全部路径：成功渲染、空输入、依赖缺失降级、
渲染异常降级、父目录创建、Semaphore 超时；以及本次修复的两个回归点：

- 列表项目符号不再乱码为 "煉"（``test_bullet_not_garbled``）
- ``<pre>`` 代码块不再黑条，内容可从 PDF 文本层提取（``test_code_block_not_black_bar``）

WeasyPrint 渲染依赖系统库（pango/cairo）；缺库环境自动 skip 渲染类用例，
降级逻辑（返回 None）仍可测，不阻断 CI。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.md2pdf as _md2pdf  # noqa: E402

# macOS 先配好 brew lib 路径，确保下方探测 import weasyprint 可成功
_md2pdf._prepare_weasyprint_env()

from pypdf import PdfReader  # noqa: E402


def _weasyprint_ready() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


def _extract_text(path: str) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


WEASY_READY = _weasyprint_ready()
skip_no_weasy = pytest.mark.skipif(
    not WEASY_READY, reason="weasyprint/系统库不可用，跳过渲染类用例"
)


# --------------------------------------------------------------------------- #
# 边界与降级
# --------------------------------------------------------------------------- #


def test_empty_markdown_returns_none(tmp_path):
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "empty.pdf"
    assert markdown_to_pdf_file("", str(out)) is None
    assert markdown_to_pdf_file("   \n\t ", str(out)) is None
    assert not out.exists()


def test_weasyprint_missing_returns_none(tmp_path, monkeypatch):
    """import weasyprint 失败时返回 None（保留降级语义，触发上层 404）。"""
    import src.md2pdf as m

    monkeypatch.setitem(sys.modules, "weasyprint", None)  # 让 `from weasyprint import ...` 抛 ImportError
    out = tmp_path / "degraded.pdf"
    assert m.markdown_to_pdf_file("# 标题\n正文", str(out)) is None
    assert not out.exists()


@skip_no_weasy
def test_render_exception_returns_none(tmp_path, monkeypatch):
    """write_pdf 抛异常时返回 None，不向外抛。"""
    import src.md2pdf as m
    import weasyprint

    class _BadHTML:
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(weasyprint, "HTML", _BadHTML)
    out = tmp_path / "fail.pdf"
    assert m.markdown_to_pdf_file("# 标题", str(out)) is None


# --------------------------------------------------------------------------- #
# 结构 / 契约
# --------------------------------------------------------------------------- #


def test_creates_parent_directory(tmp_path):
    """父目录不存在时自动创建（在 import weasyprint 之前执行，不依赖系统库）。"""
    import src.md2pdf as m

    deep = tmp_path / "a" / "b" / "c" / "x.pdf"
    m.markdown_to_pdf_file("# 标题", str(deep))
    assert (tmp_path / "a" / "b" / "c").is_dir()


def test_semaphore_timeout_returns_none(tmp_path, monkeypatch):
    """Semaphore 被占用时，新请求超时返回 None。"""
    import src.md2pdf as m

    monkeypatch.setattr(m, "_PDF_LOCK_TIMEOUT", 0.05)
    assert m._pdf_lock.acquire()  # 占用，模拟并发队列满
    try:
        out = tmp_path / "busy.pdf"
        assert m.markdown_to_pdf_file("# 标题", str(out)) is None
    finally:
        m._pdf_lock.release()


# --------------------------------------------------------------------------- #
# macOS 环境自适应（_prepare_weasyprint_env）
# --------------------------------------------------------------------------- #


def test_prepare_env_non_macos_noop(monkeypatch):
    import src.md2pdf as m

    monkeypatch.setattr(m.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DYLD_FALLBACK_LIBRARY_PATH", raising=False)
    m._prepare_weasyprint_env()
    assert "DYLD_FALLBACK_LIBRARY_PATH" not in os.environ


def test_prepare_env_macos_sets_path(tmp_path, monkeypatch):
    import src.md2pdf as m

    monkeypatch.setattr(m.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("DYLD_FALLBACK_LIBRARY_PATH", raising=False)
    fake_lib = tmp_path / "homebrew" / "lib"
    fake_lib.mkdir(parents=True)
    (fake_lib / m._GOBJECT_MARKER).write_text("")
    monkeypatch.setattr(m, "_BREW_LIB_CANDIDATES", (str(fake_lib),))

    m._prepare_weasyprint_env()
    assert str(fake_lib) in os.environ["DYLD_FALLBACK_LIBRARY_PATH"]


def test_prepare_env_idempotent(tmp_path, monkeypatch):
    """已存在的路径不重复追加。"""
    import src.md2pdf as m

    monkeypatch.setattr(m.platform, "system", lambda: "Darwin")
    fake_lib = tmp_path / "lib"
    fake_lib.mkdir()
    (fake_lib / m._GOBJECT_MARKER).write_text("")
    monkeypatch.setattr(m, "_BREW_LIB_CANDIDATES", (str(fake_lib),))
    monkeypatch.setenv("DYLD_FALLBACK_LIBRARY_PATH", str(fake_lib))

    m._prepare_weasyprint_env()
    assert os.environ["DYLD_FALLBACK_LIBRARY_PATH"].count(str(fake_lib)) == 1


def test_prepare_env_macos_no_brew_noop(monkeypatch, tmp_path):
    """macOS 但无 brew glib 标记文件时静默返回，不设环境变量。"""
    import src.md2pdf as m

    monkeypatch.setattr(m.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(m, "_BREW_LIB_CANDIDATES", (str(tmp_path / "nope"),))
    monkeypatch.delenv("DYLD_FALLBACK_LIBRARY_PATH", raising=False)
    m._prepare_weasyprint_env()
    assert "DYLD_FALLBACK_LIBRARY_PATH" not in os.environ


# --------------------------------------------------------------------------- #
# 回归 #1：列表项目符号不再乱码为 "煉"
# --------------------------------------------------------------------------- #


@skip_no_weasy
def test_bullet_not_garbled(tmp_path):
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "bullet.pdf"
    md = (
        "### 投资评级\n\n"
        "- **短期（3 个月）**：中性偏多 — 趋势强度 90/100\n"
        "- **中期（6 个月）**：增持\n"
        "- **长期（12 个月）**：看好\n"
    )
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    text = _extract_text(str(out))
    assert "短期" in text
    assert "中期" in text
    assert "煉" not in text  # 核心回归断言：旧 xhtml2pdf 方案此处出现 "煉"


# --------------------------------------------------------------------------- #
# 回归 #2：<pre> 代码块不再黑条，内容可提取
# --------------------------------------------------------------------------- #


@skip_no_weasy
def test_code_block_not_black_bar(tmp_path):
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "code.pdf"
    md = (
        "### 2.1 产业链图谱\n\n"
        "```\n"
        "上游（晶圆代工）→ 中游（芯片设计）→ 下游（终端）\n"
        "  TSMC/SMIC         桥接芯片         消费电子\n"
        "```\n"
    )
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    text = _extract_text(str(out))
    # 旧方案 <pre>+CJK 整片黑条、文本层丢失；WeasyPrint 正常渲染后内容可提取
    assert "上游" in text
    assert "中游" in text
    assert "下游" in text
    assert "→" in text
    assert "TSMC" in text


# --------------------------------------------------------------------------- #
# 其他渲染场景
# --------------------------------------------------------------------------- #


@skip_no_weasy
def test_emoji_does_not_crash(tmp_path):
    """emoji 不再崩；生成有效 PDF（彩色与否取决于宿主字体）。"""
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "emoji.pdf"
    md = "- 测试 📈 上涨 🔥 完成 ✅\n"
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    assert out.stat().st_size > 0


@skip_no_weasy
def test_table_renders(tmp_path):
    """瓶颈分表格正常渲染，内容可提取。"""
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "table.pdf"
    md = (
        "| 环节 | 公司 | 瓶颈分 |\n| --- | --- | --- |\n"
        "| 上游 | TSMC | 9.0 |\n| 中游 | 龙迅 | 7.5 |\n"
    )
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    text = _extract_text(str(out))
    assert "TSMC" in text
    assert "龙迅" in text


# --------------------------------------------------------------------------- #
# 回归 #3：宽多列 + 长 CJK 表格列宽不再塌缩为 1 字竖排
# ---------------------------------------------------------------------------


def test_pdf_css_overrides_table_display_block():
    """``_PDF_CSS`` 必须把表格 ``display`` 覆盖为 ``table`` + ``table-layout: fixed``，
    抵消 formatters 面向 web 的 ``table { display: block; overflow-x: auto }``——
    后者在 WeasyPrint 分页 PDF 下会把宽表列宽压成 1 字竖排（格式错误）。"""
    from src.md2pdf import _PDF_CSS

    assert "display: table" in _PDF_CSS
    assert "table-layout: fixed" in _PDF_CSS
    # 单元格允许任意断行，长 CJK / 长 token 在固定列宽内换行而不溢出
    assert "overflow-wrap: anywhere" in _PDF_CSS
    assert "vertical-align: top" in _PDF_CSS


@skip_no_weasy
def test_wide_table_columns_not_collapsed(tmp_path):
    """回归：宽多列 + 长 CJK 表格（供应链「线索验证」6 列形态）不再被压成 1 字竖排。

    根因：``formatters.markdown_to_html_document`` 注入 ``table { display: block;
    overflow-x: auto }``（GitHub 式横向滚动），WeasyPrint 不支持横向滚动，把宽表
    渲染为块、列宽塌缩；``_PDF_CSS``（注入更晚、同优先级后者生效）用
    ``display: table; table-layout: fixed`` 覆盖恢复真正表格布局。
    """
    import re

    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "wide_table.pdf"
    md = (
        "| 用户线索 | 验证状态 | 关键证据 | 来源强度 | 对结论的影响 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 新莱应材是新凯来的管阀件供应商 | 未找到可靠证据 | "
        "① 公告未披露客户名单含新凯来；② 互动易未检索到确认；③ 招投标无匹配记录 | "
        "rumor | 重大影响：若属实且新凯来放量，提升需求拐点评分 |\n"
    )
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    text = _extract_text(str(out))
    # 表头作为完整 token 出现（修复前 display:block 把它们压成单字竖排）
    for header in ("用户线索", "验证状态", "关键证据", "来源强度", "对结论的影响"):
        assert header in text, f"宽表表头 {header} 断裂为竖排（列宽塌缩）"
    # 不应出现 1 字竖排（用\n户\n线\n索）
    assert not re.search(r"用\s*\n\s*户\s*\n\s*线\s*\n\s*索", text), "仍存在 1 字竖排（列宽未修复）"
    # 单元格长内容可提取（在固定列宽内换行）
    assert "新凯来" in text and "互动易" in text


@skip_no_weasy
def test_complex_report_renders(tmp_path):
    """组合片段（标题+列表+代码块+表格+emoji）整体渲染，且无 "煉"。"""
    from src.md2pdf import markdown_to_pdf_file

    out = tmp_path / "complex.pdf"
    md = (
        "### 投资评级\n\n"
        "- **短期（3 个月）**：中性偏多 — MACD 多头排列\n"
        "- **长期（12 个月）**：看好 📈\n\n"
        "### 2.1 产业链图谱\n\n"
        "```\n上游 → 中游 → 下游\n  TSMC     龙迅     终端\n```\n\n"
        "| 环节 | 瓶颈分 |\n| --- | --- |\n| 上游 | 9.0 |\n"
    )
    assert markdown_to_pdf_file(md, str(out)) == str(out)
    text = _extract_text(str(out))
    assert "短期" in text
    assert "上游" in text
    assert "→" in text
    assert "煉" not in text
