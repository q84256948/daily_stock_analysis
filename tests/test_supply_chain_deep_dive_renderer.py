# -*- coding: utf-8 -*-
"""[v3 PR-C] 深度小节渲染层 + service 集成单测。

覆盖：
1. §5 白话摘要兜底 + 6 个单节渲染函数（§6/§7/§8.1/§8.2/§9/§10 + 脚注）
2. 顶层 render_deep_dive_sections 入口
3. extract_deep_dive_section_from_markdown 解析
4. SupplyChainReportService 集成：灰度开关 / 落库 / 详情返回
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import pytest

from src.schemas.supply_chain import (
    FinancialQualityV3,
    IndustryOutlookV3,
    KeyPartnerV3,
    MarketPositionV3,
    ProductLineV3,
    SupplyChainDeepDiveV3,
)
from src.services.supply_chain import deep_dive_renderer as renderer


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERENITY_DEEP_DIVE_V3_ENABLED", raising=False)


def _sample_deep_dive() -> SupplyChainDeepDiveV3:
    return SupplyChainDeepDiveV3(
        ticker="600519",
        company="贵州茅台",
        fetched_at=datetime(2026, 1, 15, 18, 0, 0, tzinfo=timezone.utc),
        aggregate_confidence="high",  # 5 节全 executed → high
        product_matrix=[
            ProductLineV3(
                name="飞天 53° 500ml",
                category="core",
                revenue_share_pct=65.0,
                gross_margin_pct=92.0,
                target_market=["高端商务宴请"],
                price_band="1499 元以上",
                differentiators=["品牌护城河"],
                evidence_strength="primary",
            ),
            ProductLineV3(
                name="系列酒",
                category="growth",
                revenue_share_pct=15.0,
                gross_margin_pct=75.0,
                evidence_strength="analysis",
            ),
        ],
        market_position=[
            MarketPositionV3(
                subsegment="高端白酒",
                market_share_pct=33.0,
                market_rank=1,
                cr3_pct=75.0,
                cr5_pct=88.0,
                share_trend="rising",
                share_change_3y_pct=5.0,
                top_competitors=["五粮液", "泸州老窖"],
                substitution_risk="low",
                evidence_strength="primary",
            ),
        ],
        key_customers=[
            KeyPartnerV3(
                side="customer",
                name="客户A",
                share_pct=12.0,
                is_related_party=True,
                is_anonymous=True,
                public_source="annual_report",
                evidence_strength="primary",
            ),
        ],
        key_suppliers=[
            KeyPartnerV3(
                side="supplier",
                name="有机高粱基地",
                share_pct=35.0,
                public_source="prospectus",
                evidence_strength="primary",
            ),
        ],
        industry_outlook=[
            IndustryOutlookV3(
                subsegment="高端白酒",
                subsegment_status="growing",
                tam_2024_usd_bn=200.0,
                tam_2027e_usd_bn=300.0,
                cagr_2024_2027_pct=14.5,
                china_share_pct=95.0,
                demand_drivers=["商务复苏"],
                policy_catalysts=["消费税"],
                substitution_threats=["进口烈酒"],
                overseas_addressable="有限（华人/免税）",
                time_window="mid_term_6_12m",
                evidence_strength="primary",
            ),
        ],
        financial_quality=[
            FinancialQualityV3(
                period="2024Q3",
                revenue_yoy_pct=15.0,
                gross_margin_pct=91.5,
                gross_margin_change_yoy_pct=0.5,
                operating_cash_flow_yoy_pct=18.0,
                ar_to_revenue_pct=2.3,
                inventory_days=365,
                contract_liability_yoy_pct=25.0,
                capex_intensity_pct=8.0,
                capacity_utilization_pct=95.0,
                revenue_segments={"茅台酒": 85.0, "系列酒": 13.0, "其他": 2.0},
                red_flags=[],
                evidence_strength="primary",
            ),
        ],
        sections_executed=[
            "product_matrix",
            "market_position",
            "key_partners",
            "industry_outlook",
            "financial_quality",
        ],
    )


# ============================================================
# §6 render_product_matrix
# ============================================================


class TestRenderProductMatrix:
    def test_empty_returns_empty(self) -> None:
        assert renderer.render_product_matrix([]) == ""

    def test_render_basic(self) -> None:
        products = [
            ProductLineV3(name="A", category="core", revenue_share_pct=70.0),
            ProductLineV3(name="B", category="growth", revenue_share_pct=30.0),
        ]
        out = renderer.render_product_matrix(products)
        assert "## 6. 产品矩阵与定位" in out
        assert "| 产品 |" in out  # 表头
        assert "| A |" in out
        assert "| B |" in out
        # 排序：70% 优先于 30%
        assert out.index("| A |") < out.index("| B |")

    def test_render_with_null(self) -> None:
        products = [ProductLineV3(name="X", category="legacy")]
        out = renderer.render_product_matrix(products)
        # [v3 本地化] category "legacy" 渲染为 "传统"
        assert "| X | 传统 |" in out
        # null 字段渲染为 "—"
        assert "—" in out


# ============================================================
# §7 render_market_position
# ============================================================


class TestRenderMarketPosition:
    def test_empty(self) -> None:
        assert renderer.render_market_position([]) == ""

    def test_render_rising(self) -> None:
        m = MarketPositionV3(
            subsegment="高端白酒",
            market_share_pct=33.0,
            market_rank=1,
            cr3_pct=75.0,
            cr5_pct=88.0,
            share_trend="rising",
            share_change_3y_pct=5.0,
            top_competitors=["五粮液", "泸州老窖"],
            substitution_risk="low",
        )
        out = renderer.render_market_position([m])
        assert "## 7. 市场占有率" in out
        assert "高端白酒" in out
        assert "33.0%" in out
        assert "↗ 上升" in out
        assert "+5.0pct" in out
        assert "五粮液" in out
        assert "低" in out  # 替代风险 low → "低"

    def test_render_with_null(self) -> None:
        m = MarketPositionV3(subsegment="X")
        out = renderer.render_market_position([m])
        assert "待核验" in out  # market_share_pct 为 null 时显示待核验


# ============================================================
# §8 render_key_customers / suppliers
# ============================================================


class TestRenderKeyPartners:
    def test_empty_customers_and_suppliers(self) -> None:
        assert renderer.render_key_customers([]) == ""
        assert renderer.render_key_suppliers([]) == ""

    def test_anonymous_customer(self) -> None:
        c = KeyPartnerV3(
            side="customer",
            name="客户A",
            is_related_party=True,
            is_anonymous=True,
            share_pct=12.0,
            public_source="annual_report",
        )
        out = renderer.render_key_customers([c])
        assert "### 8.1 主要客户" in out
        assert "客户A" in out
        assert "是" in out  # 关联方 + 匿名
        assert "annual_report" in out

    def test_supplier(self) -> None:
        s = KeyPartnerV3(
            side="supplier",
            name="有机高粱基地",
            share_pct=35.0,
            public_source="prospectus",
        )
        out = renderer.render_key_suppliers([s])
        assert "### 8.2 主要供应商" in out
        assert "有机高粱基地" in out


# ============================================================
# §9 render_industry_outlook
# ============================================================


class TestRenderIndustryOutlook:
    def test_empty(self) -> None:
        assert renderer.render_industry_outlook([]) == ""

    def test_render_growing(self) -> None:
        o = IndustryOutlookV3(
            subsegment="高端白酒",
            subsegment_status="growing",
            tam_2024_usd_bn=200.0,
            tam_2027e_usd_bn=300.0,
            cagr_2024_2027_pct=14.5,
            china_share_pct=95.0,
            demand_drivers=["商务复苏"],
            policy_catalysts=["消费税"],
            substitution_threats=["进口烈酒"],
            overseas_addressable="有限",
            time_window="mid_term_6_12m",
        )
        out = renderer.render_industry_outlook([o])
        assert "## 9. 行业前景与需求驱动" in out
        assert "高端白酒" in out
        assert "200.0" in out
        assert "300.0" in out
        assert "+14.5%" in out
        assert "商务复苏" in out


# ============================================================
# §10 render_financial_quality
# ============================================================


class TestRenderFinancialQuality:
    def test_empty(self) -> None:
        assert renderer.render_financial_quality([]) == ""

    def test_render_with_segments(self) -> None:
        f = FinancialQualityV3(
            period="2024Q3",
            revenue_yoy_pct=15.0,
            gross_margin_pct=91.5,
            revenue_segments={"A": 60.0, "B": 35.0, "C": 5.0},
            red_flags=["应收账款上升"],
        )
        out = renderer.render_financial_quality([f])
        assert "## 10. 财务质量与产能跟踪" in out
        assert "2024Q3" in out
        assert "+15.0%" in out
        assert "91.5%" in out
        # 分业务收入占比附在 §10 末尾
        assert "分业务收入占比" in out
        assert "A 60.0%" in out
        assert "应收账款上升" in out


# ============================================================
# 脚注 render_section_status
# ============================================================


class TestRenderSectionStatus:
    def test_all_executed(self) -> None:
        v3 = _sample_deep_dive()
        # compute_aggregate_confidence 是纯函数（frozen 不允许 setattr）
        agg = v3.compute_aggregate_confidence()
        assert agg == "high"
        out = renderer.render_section_status(v3)
        assert "## 数据完整性披露" in out
        assert "§6 产品矩阵与定位 | ✓" in out
        assert "§7 市场占有率 | ✓" in out
        assert "§8 关键客户与供应商 | ✓" in out
        assert "§9 行业前景与需求驱动 | ✓" in out
        assert "§10 财务质量与产能跟踪 | ✓" in out
        assert "Aggregate Confidence" in out
        assert "**Aggregate Confidence**：高" in out

    def test_partial(self) -> None:
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            product_matrix=[ProductLineV3(name="A", category="core")],
            sections_executed=["product_matrix"],
        )
        out = renderer.render_section_status(v3)
        assert "§6 产品矩阵与定位 | ✓" in out
        assert "§7 市场占有率 | ✗" in out


# ============================================================
# 顶层 render_deep_dive_sections
# ============================================================


class TestRenderDeepDiveSections:
    def test_full_sample(self) -> None:
        v3 = _sample_deep_dive()
        out = renderer.render_deep_dive_sections(v3)
        # §5 白话摘要兜底（LLM_markdown 为空 → 派生）
        assert "## 5. 市场地位与竞品" in out
        assert "### 5.1 行业定位" in out
        assert "### 5.2 核心竞争优势 与 §5.3 与主要竞争对手对比" in out
        assert "### 5.4 数据来源" in out
        assert "## 6. 产品矩阵与定位" in out
        assert "## 7. 市场占有率（含行业排名/龙头地位）" in out
        assert "## 8. 关键客户与供应商" in out
        assert "### 8.1 主要客户" in out
        assert "### 8.2 主要供应商" in out
        assert "## 9. 行业前景与需求驱动" in out
        assert "## 10. 财务质量与产能跟踪" in out
        assert "## 数据完整性披露" in out

    def test_llm_already_wrote_section5_skips_fallback(self) -> None:
        """LLM 在主报告里写了 §5 → renderer 不重复派生（避免白话摘要重复）。"""
        v3 = _sample_deep_dive()
        llm_markdown = (
            "## 1. 结论\nx\n## 5. 市场地位与竞品\nx\n## 6. 产品矩阵与定位\nx\n"
        )
        out = renderer.render_deep_dive_sections(v3, llm_markdown=llm_markdown)
        # §5 兜底未触发（不在 renderer 输出里）
        assert "### 5.1 行业定位" not in out
        # §6/§7/§10 仍正常
        assert "## 6. 产品矩阵与定位" in out

    def test_empty_sections_only_shows_footer(self) -> None:
        v3 = SupplyChainDeepDiveV3(ticker="X", company="Y")
        out = renderer.render_deep_dive_sections(v3)
        # 5 节全空：§6-§10 主标题都不应出现
        assert "## 6. 产品矩阵与定位" not in out
        assert "## 7. 市场占有率（含行业排名/龙头地位）" not in out
        assert "## 8. 关键客户与供应商" not in out
        assert "## 9. 行业前景与需求驱动" not in out
        assert "## 10. 财务质量与产能跟踪" not in out
        # §5 兜底也因数据全空不触发
        assert "## 5. 市场地位与竞品" not in out
        assert "## 数据完整性披露" in out
        # 5 节全 skipped
        assert "§6 产品矩阵与定位 | ✗" in out
        assert "§10 财务质量与产能跟踪 | ✗" in out

    def test_partial_sections(self) -> None:
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            product_matrix=[ProductLineV3(name="A", category="core")],
            sections_executed=["product_matrix"],
        )
        out = renderer.render_deep_dive_sections(v3)
        assert "## 6. 产品矩阵与定位" in out
        # 其它 4 节空：主标题不应出现
        assert "## 7. 市场占有率（含行业排名/龙头地位）" not in out
        assert "## 8. 关键客户与供应商" not in out
        assert "## 9. 行业前景与需求驱动" not in out
        assert "## 10. 财务质量与产能跟踪" not in out
        assert "## 数据完整性披露" in out


# ============================================================
# §5 render_market_position_summary
# ============================================================


class TestRenderMarketPositionSummary:
    def test_no_data_returns_empty(self) -> None:
        v3 = SupplyChainDeepDiveV3(ticker="X", company="Y")
        assert renderer.render_market_position_summary(v3) == ""

    def test_llm_already_wrote_section5_skipped(self) -> None:
        v3 = _sample_deep_dive()
        llm = "## 5. 市场地位与竞品\nuser content"
        assert renderer.render_market_position_summary(v3, llm) == ""

    def test_only_market_position_triggers(self) -> None:
        """只含 market_position 数据时，§5 仍能派生。"""
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            market_position=[
                MarketPositionV3(
                    subsegment="高端白酒",
                    market_share_pct=33.0,
                    market_rank=1,
                    cr3_pct=75.0,
                    share_trend="rising",
                    top_competitors=["五粮液", "泸州老窖"],
                    substitution_risk="low",
                )
            ],
        )
        out = renderer.render_market_position_summary(v3)
        assert "## 5. 市场地位与竞品" in out
        assert "高端白酒" in out
        assert "龙头" in out
        assert "五粮液" in out

    def test_only_product_matrix_triggers(self) -> None:
        """只含 product_matrix 时，§5.1 行业定位派生出，§5.2 表格不出现。"""
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            product_matrix=[
                ProductLineV3(
                    name="飞天",
                    category="core",
                    revenue_share_pct=65.0,
                    gross_margin_pct=92.0,
                )
            ],
        )
        out = renderer.render_market_position_summary(v3)
        assert "## 5. 市场地位与竞品" in out
        assert "飞天" in out
        # 没有 market_position 时，§5.2 表格段不应出现
        assert "### 5.2 核心竞争优势 与 §5.3 与主要竞争对手对比" not in out

    def test_leadership_detection(self) -> None:
        """rank=1 + 有份额 → 「龙头」标签。"""
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            market_position=[
                MarketPositionV3(
                    subsegment="x",
                    market_share_pct=20.0,
                    market_rank=2,
                )
            ],
        )
        out = renderer.render_market_position_summary(v3)
        assert "领先" in out
        assert "龙头" not in out  # rank=2 不是龙头


# ============================================================
# extract_deep_dive_section_from_markdown
# ============================================================


class TestExtractDeepDiveSection:
    def test_empty_markdown(self) -> None:
        assert renderer.extract_deep_dive_section_from_markdown("") == ""

    def test_no_marker(self) -> None:
        md = "# 普通报告\n## 1. 结论\nblah"
        assert renderer.extract_deep_dive_section_from_markdown(md) == ""

    def test_with_marker_12(self) -> None:
        md = "## 9. 知识库参考\n\nx\n## 6. 产品矩阵与定位\n\ncontent\n## 数据完整性披露\n\nfooter"
        out = renderer.extract_deep_dive_section_from_markdown(md)
        assert "## 6. 产品矩阵与定位" in out
        assert "content" in out
        assert "## 9. 知识库参考" not in out

    def test_with_marker_footer_only(self) -> None:
        md = "## 主报告\n## 数据完整性披露\n\nfooter"
        out = renderer.extract_deep_dive_section_from_markdown(md)
        assert "## 数据完整性披露" in out
        assert "## 主报告" not in out


# ============================================================
# Service 集成：灰度开关
# ============================================================


class TestServiceFlagAndExtraction:
    def _service(self) -> Any:
        from src.services.supply_chain_report_service import (
            SupplyChainReportService,
        )

        return SupplyChainReportService()

    def test_flag_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SERENITY_DEEP_DIVE_V3_ENABLED", raising=False)
        assert self._service()._is_deep_dive_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", " True "])
    def test_flag_enabled_values(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("SERENITY_DEEP_DIVE_V3_ENABLED", val)
        assert self._service()._is_deep_dive_enabled() is True

    def test_flag_disabled_other_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ["0", "false", "no", "off", "random"]:
            monkeypatch.setenv("SERENITY_DEEP_DIVE_V3_ENABLED", val)
            assert self._service()._is_deep_dive_enabled() is False

    def test_extract_returns_none_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERENITY_DEEP_DIVE_V3_ENABLED", "false")
        svc = self._service()
        out = svc._extract_deep_dive_section(
            "## 6. 产品矩阵与定位\n\nA\n## 数据完整性披露\n\nfooter"
        )
        assert out is None

    def test_extract_returns_dict_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERENITY_DEEP_DIVE_V3_ENABLED", "true")
        svc = self._service()
        out = svc._extract_deep_dive_section(
            "## 6. 产品矩阵与定位\n\nA\n## 数据完整性披露\n\nfooter"
        )
        assert isinstance(out, dict)
        assert "_raw_markdown_section" in out
        assert "## 6. 产品矩阵与定位" in out["_raw_markdown_section"]

    def test_extract_empty_markdown_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERENITY_DEEP_DIVE_V3_ENABLED", "true")
        svc = self._service()
        # 不含 §10 → None
        out = svc._extract_deep_dive_section("## 1. 结论\nblah")
        assert out is None


# ============================================================
# DB 集成：deep_dive_json 字段
# ============================================================


class TestStorageDeepDiveJson:
    def test_save_with_deep_dive_json(self, tmp_path: Any) -> None:
        """save_supply_chain_report 接受 deep_dive_json 参数并持久化。"""
        from src.storage import get_db

        # 切换 DB 到临时 SQLite（不污染主 DB）
        os.environ["DSA_DB_URL"] = f"sqlite:///{tmp_path}/test.db"

        db = get_db()
        deep_dive_json = json.dumps(
            {"_raw_markdown_section": "## 6. ..."}, ensure_ascii=False
        )
        ok = db.save_supply_chain_report(
            report_id="sc_202601150000_1",
            topic="AI 半导体测试",
            research_hint=None,
            md_path="/tmp/sc_202601150000_1.md",
            status="success",
            deep_dive_json=deep_dive_json,
        )
        assert ok

        record = db.get_supply_chain_report("sc_202601150000_1")
        assert record is not None
        assert record.deep_dive_json == deep_dive_json

        d = record.to_dict()
        assert d["deep_dive_json"] == deep_dive_json

    def test_save_without_deep_dive_json(self, tmp_path: Any) -> None:
        """不传 deep_dive_json 时默认 None，向后兼容。"""
        from src.storage import get_db

        os.environ["DSA_DB_URL"] = f"sqlite:///{tmp_path}/test_compat.db"

        db = get_db()
        ok = db.save_supply_chain_report(
            report_id="sc_202601150000_2",
            topic="兼容测试",
            research_hint=None,
            md_path="/tmp/sc_202601150000_2.md",
            status="success",
        )
        assert ok
        record = db.get_supply_chain_report("sc_202601150000_2")
        assert record is not None
        assert record.deep_dive_json is None


# ============================================================
# 端到端渲染：deep_dive → markdown 注入
# ============================================================


class TestEndToEndRendering:
    def test_render_to_markdown_for_storage(self, tmp_path: Any) -> None:
        """完整链路：构造 v3 → 渲染 markdown → 落盘 → DB 回读 deep_dive_json。"""
        from src.storage import get_db

        os.environ["DSA_DB_URL"] = f"sqlite:///{tmp_path}/test_e2e.db"
        db = get_db()

        v3 = _sample_deep_dive()
        # v3 frozen，compute_aggregate_confidence 是纯函数返回
        agg = v3.compute_aggregate_confidence()
        assert agg == "high"
        deep_md = renderer.render_deep_dive_sections(v3)
        assert "## 6." in deep_md

        # 落盘 Markdown
        md_path = tmp_path / "sc_e2e.md"
        md_path.write_text(deep_md, encoding="utf-8")
        assert md_path.exists()

        # DB 落 deep_dive_json
        deep_dive_json = v3.model_dump_json()
        db.save_supply_chain_report(
            report_id="sc_e2e_1",
            topic="e2e",
            research_hint=None,
            md_path=str(md_path),
            status="success",
            deep_dive_json=deep_dive_json,
        )
        record = db.get_supply_chain_report("sc_e2e_1")
        assert record is not None
        assert record.deep_dive_json is not None
        # 序列化往返
        v3_round = SupplyChainDeepDiveV3.model_validate_json(record.deep_dive_json)
        assert v3_round.ticker == v3.ticker
        assert len(v3_round.product_matrix) == len(v3.product_matrix)
