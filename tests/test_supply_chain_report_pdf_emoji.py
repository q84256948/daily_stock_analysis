# -*- coding: utf-8 -*-
"""供应链报告 PDF emoji 乱码修复测试。

根因：WeasyPrint 无法把彩色 emoji 位图嵌入 PDF，⚠️ 等路由到 Apple-Color-Emoji
字体时渲染成豆腐块。修复 = ``supply_chain_report_service._generate_pdf`` 渲染前用
``strip_emoji_for_pdf`` 剥彩色 emoji + 变体选择符（保留 CJK/①②③/≤/μ/•/→/——）。

覆盖：
- ``strip_emoji_for_pdf`` 纯函数：剥 emoji、保信息性字符、None/空安全。
- 渲染回归：含 ⚠️ 的 md 经 ``_generate_pdf`` → PDF 文本层无 ⚠、正文保留。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.services.supply_chain_report_service as svc  # noqa: E402
from src.services.supply_chain_report_service import (  # noqa: E402
    SupplyChainReportService,
    strip_emoji_for_pdf,
)

# macOS 先配好 brew lib 路径，确保 weasyprint 可 import
try:
    import src.md2pdf as _m  # noqa: E402

    _m._prepare_weasyprint_env()
except Exception:  # noqa: BLE001
    pass
try:
    from pypdf import PdfReader  # noqa: E402
except Exception:  # noqa: BLE001
    PdfReader = None


def _weasyprint_ready() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


WEASY_READY = _weasyprint_ready()
skip_no_weasy = pytest.mark.skipif(
    not WEASY_READY, reason="weasyprint/系统库不可用，跳过渲染类用例"
)


# --------------------------------------------------------------------------- #
# 纯函数 strip_emoji_for_pdf
# --------------------------------------------------------------------------- #


class TestStripEmojiForPdf:
    def test_strips_warning_emoji_and_variation_selector(self):
        out = strip_emoji_for_pdf("⚠️ 这是最关键的风险信号")
        assert "⚠" not in out
        assert "️" not in out  # U+FE0F 变体选择符也剥掉
        assert "这是最关键的风险信号" in out

    def test_strips_common_color_emoji(self):
        out = strip_emoji_for_pdf("涨 📈 跌 🔥 完成 ✅ 目标 🎯")
        for e in ("📈", "🔥", "✅", "🎯"):
            assert e not in out
        assert "涨" in out and "跌" in out and "完成" in out and "目标" in out

    def test_keeps_cjk_and_informative_symbols(self):
        # 这些字符 WeasyPrint 经 PingFang SC 能正常渲染，必须保留
        keep = "新莱应材（300260）①②③④⑤ ≤ μm • → —— 营收 +5.2% ROE 8.65%"
        assert strip_emoji_for_pdf(keep) == keep

    def test_keeps_circled_numbers_and_math(self):
        assert strip_emoji_for_pdf("① ② ③ ≤ ≥ μ → ") == "① ② ③ ≤ ≥ μ → "

    def test_strips_consecutive_emoji(self):
        assert strip_emoji_for_pdf("📈📈⚠️🔥") == ""

    def test_strips_zwj_sequences(self):
        # ZWJ 组合 emoji 也剥掉
        assert "👨" not in strip_emoji_for_pdf("a👨‍👩‍👧b")
        assert "ab" == strip_emoji_for_pdf("a👨‍👩‍👧b").replace("‍", "")

    def test_none_safe(self):
        assert strip_emoji_for_pdf(None) == ""

    def test_empty_safe(self):
        assert strip_emoji_for_pdf("") == ""

    def test_plain_text_unchanged(self):
        assert strip_emoji_for_pdf("纯中文报告，无 emoji。") == "纯中文报告，无 emoji。"

    def test_mixed_strip_keeps_text(self):
        # 实际报告片段
        src = "⚠️ **这是最关键的风险信号。** 当 ① 市场已定价 ② 利好出尽 📉"
        out = strip_emoji_for_pdf(src)
        assert "⚠" not in out and "📉" not in out
        assert "这是最关键的风险信号" in out and "①" in out and "②" in out


# --------------------------------------------------------------------------- #
# 渲染回归：_generate_pdf 对 emoji md 剥离后生成无 ⚠ 的 PDF
# --------------------------------------------------------------------------- #


@skip_no_weasy
def test_generate_pdf_strips_emoji_from_render(tmp_path, monkeypatch):
    """含 ⚠️ 的 md → _generate_pdf → PDF 文本层不含 ⚠、正文保留。"""
    md_file = tmp_path / "r.md"
    md_file.write_text(
        "# 供应链报告\n\n## 题材炒作信号\n\n⚠️ **这是最关键的风险信号。**\n\n"
        "① 市场已定价 ② 利好出尽 📈\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(id="sc_test_emoji", md_path=str(md_file), pdf_path=None)

    # 避免 DB：set_supply_chain_pdf_path 走 mock
    mock_db = MagicMock()
    mock_db.set_supply_chain_pdf_path.return_value = True
    monkeypatch.setattr(svc, "get_db", lambda: mock_db)

    pdf_path = SupplyChainReportService()._generate_pdf(record)

    assert pdf_path == str(md_file.with_suffix(".pdf"))
    assert Path(pdf_path).exists()
    # PDF 回填了 pdf_path
    mock_db.set_supply_chain_pdf_path.assert_called_once_with("sc_test_emoji", pdf_path)

    # 关键回归：PDF 文本层无 ⚠ / 📈，但正文信息保留
    text = "\n".join(p.extract_text() or "" for p in PdfReader(pdf_path).pages)
    assert "⚠" not in text
    assert "📈" not in text
    assert "这是最关键的风险信号" in text
    assert "①" in text and "②" in text  # 信息性符号保留


@skip_no_weasy
def test_generate_pdf_md_file_not_untouched(tmp_path, monkeypatch):
    """剥 emoji 只影响 PDF，.md 原文不动（Web/Markdown 视图仍显示 emoji）。"""
    md_file = tmp_path / "r.md"
    original = "# 报告\n\n⚠️ 警告内容 📈\n"
    md_file.write_text(original, encoding="utf-8")
    record = SimpleNamespace(id="sc_test", md_path=str(md_file), pdf_path=None)
    monkeypatch.setattr(svc, "get_db", lambda: MagicMock(set_supply_chain_pdf_path=lambda *a: True))

    SupplyChainReportService()._generate_pdf(record)

    # .md 文件内容原样保留（含 emoji）
    assert md_file.read_text(encoding="utf-8") == original
