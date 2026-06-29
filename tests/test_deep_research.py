# -*- coding: utf-8 -*-
"""深度投研报告单元测试（离线，不依赖 LLM）。

覆盖：
- DeepResearchValidator：空报告 / 完整报告 / 缺失层检测 / 结论计数 / 概率和。
- normalize_a_share：A 股通过、港股/美股/空/非法拒绝。
- report_id 白名单契约：``^\\d{6}_\\d{12}$``（防路径穿越，与 endpoint 对齐）。
- md2pdf：Markdown→PDF（纯 Python xhtml2pdf + reportlab CID CJK 字体，离线可跑）。
"""

import re
from unittest.mock import patch

import pytest

from src.agent.deep_research_validator import DeepResearchValidator
from src.services.deep_research_service import (
    DeepResearchInputError,
    normalize_a_share,
)

# report_id 白名单（与 api/v1/endpoints/deep_research.py 的 _REPORT_ID_RE 对齐）
# {6位代码}_{12位时间戳}，可选 _序号 后缀（同分钟冲突追加）
REPORT_ID_RE = re.compile(r"^\d{6}_\d{12}(_\d+)?$")


GOOD_MD = """# x
## 投资结论
**【结论】** 买入。三情景：牛市25% 基准50% 熊市25%
## 一、宏观与政策环境
**【结论】** 大盘指数市场流动性ERP政策社融PPI宏观
## 二、产业与赛道
**【结论】** 产业链行业供应链竞争壁垒市占率生命周期格局
## 三、公司分析
**【结论】** 模式项目产能
## 四、财务质量
**【结论】** 营收利润ROE毛利率现金流杜邦
## 五、估值与目标价
**【结论】** 估值PEPBDCFSOTP目标价情景PEG安全边际
## 六、博弈与节奏
**【结论】** 筹码均线K线量能资金流主力催化股东户数融资余额
## 七、风险提示
风险1
"""

FULL_TOOLS = [
    {"tool": "get_market_indices"},
    {"tool": "search_comprehensive_intel"},
    {"tool": "get_sector_rankings"},
    {"tool": "get_stock_info"},
    {"tool": "analyze_trend"},
]


class TestDeepResearchValidator:
    def test_empty_report_scores_zero(self):
        result = DeepResearchValidator().validate("")
        assert result.score == 0
        assert len(result.missing_layers) == 5

    def test_complete_report_high_score(self):
        result = DeepResearchValidator().validate(GOOD_MD, FULL_TOOLS)
        assert result.score >= 80
        assert result.conclusion_count >= 7
        assert result.probability_sum == 100.0

    def test_missing_tool_flags_layer(self):
        # 缺 get_market_indices → 宏观层被标记
        tools_no_macro = [t for t in FULL_TOOLS if t["tool"] != "get_market_indices"]
        result = DeepResearchValidator().validate(GOOD_MD, tools_no_macro)
        assert "宏观" in result.missing_layers

    def test_missing_content_keyword_flags_layer(self):
        # 直接构造一份缺少宏观层的报告（不含任何宏观关键词）
        # 注：validator 关键词检测是"任意位置命中即覆盖"
        md_no_macro = (
            "# x\n"
            "## 投资结论\n**【结论】** 买入\n"
            "## 二、产业与赛道\n**【结论】** 产业链行业供应链竞争壁垒市占率生命周期格局\n"
            "## 三、公司分析\n**【结论】** 模式项目产能\n"
            "## 四、财务质量\n**【结论】** 营收利润ROE毛利率现金流杜邦\n"
            "## 五、估值与目标价\n**【结论】** 估值PEPBDCFSOTP目标价情景PEG安全边际\n"
            "## 六、博弈与节奏\n**【结论】** 筹码均线K线量能资金流主力催化股东户数融资余额\n"
            "## 七、风险提示\n风险1\n"
        )
        result = DeepResearchValidator().validate(md_no_macro, FULL_TOOLS)
        assert "宏观" in result.missing_layers, f"expected 宏观 missing: {result.details}"

    def test_none_input_is_safe(self):
        # None / 空输入不应抛异常
        result = DeepResearchValidator().validate(None, None)  # type: ignore[arg-type]
        assert result.score == 0

    def test_validation_markers_counted_in_details(self):
        from src.agent.deep_research_validator import _count_validation_markers
        assert _count_validation_markers("PE 30.5 ✓ 冲突 ⚠") == (1, 1)
        assert _count_validation_markers("无标记") == (0, 0)
        md = GOOD_MD + "\nPE 30.5 ✓（双源验证）\nROE ⚠ 冲突\n"
        result = DeepResearchValidator().validate(md, FULL_TOOLS)
        assert any("双源验证标注" in d for d in result.details)

    def test_no_markers_omits_detail(self):
        result = DeepResearchValidator().validate(GOOD_MD, FULL_TOOLS)
        assert not any("双源验证标注" in d for d in result.details)


class TestNormalizeAShare:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("600519", "600519"),
            ("SH600519", "600519"),
            ("sz000001", "000001"),
            ("600519.SH", "600519"),
            ("920493", "920493"),  # 北交所
            ("300750", "300750"),  # 创业板
            ("688981", "688981"),  # 科创板
        ],
    )
    def test_accept_a_share(self, raw, expected):
        assert normalize_a_share(raw) == expected

    @pytest.mark.parametrize("bad", ["AAPL", "HK00700", "00700", "TSLA", "", "abc", "12345"])
    def test_reject_non_a_share(self, bad):
        with pytest.raises(DeepResearchInputError):
            normalize_a_share(bad)


class TestReportIdWhitelist:
    """report_id 白名单防路径穿越（与 endpoint _REPORT_ID_RE 对齐）。"""

    @pytest.mark.parametrize(
        "rid",
        [
            "600519_202606241200",  # 基本格式
            "000001_202601010000",
            "600519_202606241200_1",  # 同分钟冲突追加序号后缀（合法）
            "600519_202606241200_12",  # 多位序号
        ],
    )
    def test_valid_report_id(self, rid):
        assert REPORT_ID_RE.fullmatch(rid) is not None

    @pytest.mark.parametrize(
        "rid",
        [
            "../../etc/passwd",  # 路径穿越
            "600519_202606241200_../../etc",  # 序号后缀位置穿越（_\d+ 不匹配）
            "600519_202606241200_a",  # 后缀必须纯数字
            "600519_2026062412",  # 时间戳不足 12 位
            "600519_2026062412001",  # 时间戳超长
            "AAPL_202606241200",  # 非数字代码
            "600519_20260624120a",  # 含字母
            "60051_202606241200",  # 代码不足 6 位
            "6005191_202606241200",  # 代码超 6 位
            "600519-202606241200",  # 分隔符错误
        ],
    )
    def test_reject_traversal_and_malformed(self, rid):
        assert REPORT_ID_RE.fullmatch(rid) is None


class TestResolveUniqueReportId:
    """report_id 同分钟冲突保护（_resolve_unique_report_id）。"""

    def test_unique_base_id_unchanged(self):
        """base_id 不存在 → 原样返回。"""
        from src.services.deep_research_service import _resolve_unique_report_id

        with patch(
            "src.services.deep_research_service.get_db"
        ) as mock_db:
            mock_db.return_value.get_deep_research_report.return_value = None
            assert _resolve_unique_report_id("600519_202606241200") == "600519_202606241200"

    def test_conflict_appends_sequence(self):
        """base_id 已存在 → 追加 _1；_1 也存在 → 追加 _2。"""
        from src.services.deep_research_service import _resolve_unique_report_id

        existing = {"600519_202606241200": True, "600519_202606241200_1": True}

        def fake_get(rid):
            return object() if existing.get(rid) else None

        with patch(
            "src.services.deep_research_service.get_db"
        ) as mock_db:
            mock_db.return_value.get_deep_research_report.side_effect = fake_get
            assert _resolve_unique_report_id("600519_202606241200") == "600519_202606241200_2"


class TestLookupStockName:
    """stock_name 缺省反查（_lookup_stock_name）。"""

    def test_returns_name_when_quote_available(self):
        from src.services.deep_research_service import _lookup_stock_name
        from types import SimpleNamespace

        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_realtime_quote.return_value = SimpleNamespace(name="中国巨石")
            assert _lookup_stock_name("600176") == "中国巨石"

    def test_returns_empty_on_failure(self):
        """实时行情失败 → 返回空串（调用方 fallback 到 code），不抛异常。"""
        from src.services.deep_research_service import _lookup_stock_name

        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_realtime_quote.side_effect = RuntimeError("net down")
            assert _lookup_stock_name("600176") == ""

    def test_returns_empty_when_no_name(self):
        from src.services.deep_research_service import _lookup_stock_name
        from types import SimpleNamespace

        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager"
        ) as mock_mgr:
            mock_mgr.return_value.get_realtime_quote.return_value = SimpleNamespace(name=None)
            assert _lookup_stock_name("600176") == ""


class TestMd2Pdf:
    """markdown_to_pdf_file 离线单测（纯 Python，无需系统二进制/字体文件）。

    验证对外契约：成功返回 output_path（文件存在 + PDF magic + 中文可渲染）；
    空 Markdown / 渲染异常 → 返回 None 且不抛异常（优雅降级）。
    """

    def _sample_md(self) -> str:
        return (
            "# 贵州茅台（600519）深度投研报告\n\n"
            "## 投资结论\n\n"
            "评级：买入 | 目标价：1,580 元 | 上行空间 +30.7%\n\n"
            "| 情景 | 概率 | 目标价 |\n|------|------|--------|\n"
            "| 牛市 | 25% | 1,800 |\n| 基准 | 50% | 1,580 |\n| 熊市 | 25% | 1,200 |\n"
        )

    def test_valid_markdown_produces_pdf(self, tmp_path):
        from src.md2pdf import markdown_to_pdf_file

        out = str(tmp_path / "report.pdf")
        result = markdown_to_pdf_file(self._sample_md(), out)

        import os

        assert result == out
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
        # PDF magic 校验
        with open(out, "rb") as f:
            assert f.read(5) == b"%PDF-", "输出必须是有效 PDF"

    def test_pdf_contains_chinese_text(self, tmp_path):
        """验证 CJK 字体注册生效：中文不渲染为方块（用文本提取校验）。"""
        from src.md2pdf import markdown_to_pdf_file

        out = str(tmp_path / "report_cjk.pdf")
        markdown_to_pdf_file(self._sample_md(), out)

        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(out)
        text = reader.pages[0].extract_text()
        # 关键中文应在文本中（若 CJK 字体未生效会全是 ■）
        assert "贵州茅台" in text, f"中文未正确渲染，提取文本：{text!r}"

    @pytest.mark.parametrize("empty", ["", "   ", "\n\n  \t"])
    def test_empty_markdown_returns_none(self, tmp_path, empty):
        from src.md2pdf import markdown_to_pdf_file

        out = str(tmp_path / "empty.pdf")
        assert markdown_to_pdf_file(empty, out) is None
        import os

        assert not os.path.exists(out)

    def test_render_failure_returns_none_not_raises(self, tmp_path, monkeypatch):
        """渲染异常（mock weasyprint 报错）应优雅降级返回 None，不抛异常。

        注：``src.md2pdf`` 已由 xhtml2pdf/pisa 迁移至 WeasyPrint（commit 9d47260），
        原 ``_font_registered`` 标志与 ``xhtml2pdf.pisa`` 已不存在；此处按现行 API
        mock ``weasyprint.HTML`` 的 ``write_pdf`` 抛错，断言优雅降级返回 None。
        """
        import src.md2pdf as md2pdf_mod
        md2pdf_mod._prepare_weasyprint_env()  # macOS: 先配好 brew lib 路径，下方 import weasyprint 才能成功
        import weasyprint

        class _BadHTML:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def write_pdf(self, *args, **kwargs):  # noqa: ANN001 (mock)
                raise RuntimeError("render boom")

        monkeypatch.setattr(weasyprint, "HTML", _BadHTML)

        out = str(tmp_path / "boom.pdf")
        # 不应抛异常
        assert md2pdf_mod.markdown_to_pdf_file("# 标题\n正文", out) is None

    def test_parent_dir_autocreated(self, tmp_path):
        """输出路径父目录不存在时应自动创建（reports/deep_research/ 首次写入场景）。"""
        from src.md2pdf import markdown_to_pdf_file

        nested = tmp_path / "reports" / "deep_research" / "sub.pdf"
        result = markdown_to_pdf_file(self._sample_md(), str(nested))
        import os

        assert result == str(nested)
        assert os.path.exists(str(nested))
