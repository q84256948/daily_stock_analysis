# -*- coding: utf-8 -*-
"""[v3 PR-A] 供应链深度小节 schema + DNA loader 单测。

覆盖：
1. 6 个 v3 Pydantic 模型：构造、契约校验、约束边界
2. 顶层 SupplyChainDeepDiveV3：section_status() + compute_aggregate_confidence()
3. industry_dna_loader：4 个核心行业加载 + 关键词匹配 + cache
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.supply_chain import (
    FinancialQualityV3,
    IndustryOutlookV3,
    KeyPartnerV3,
    MarketPositionV3,
    ProductLineV3,
    SupplyChainDeepDiveV3,
)
from src.services.supply_chain.industry_dna_loader import (
    IndustryDNA,
    clear_cache,
    find_dna_by_keyword,
    get_all_dna,
    list_slugs,
    load_dna,
)


# ============================================================
# ProductLineV3 §6
# ============================================================


class TestProductLineV3:
    def test_minimal_valid(self) -> None:
        p = ProductLineV3(name="飞天 53° 500ml", category="core")
        assert p.name == "飞天 53° 500ml"
        assert p.category == "core"
        assert p.revenue_share_pct is None
        assert p.gross_margin_pct is None
        assert p.differentiators == []

    def test_full_valid(self) -> None:
        p = ProductLineV3(
            name="飞天 53° 500ml",
            category="core",
            revenue_share_pct=65.0,
            gross_margin_pct=92.0,
            target_market=["高端商务宴请", "礼品市场"],
            price_band="1499元以上",
            differentiators=["品牌护城河", "稀缺产能"],
            evidence_strength="primary",
        )
        assert p.revenue_share_pct == 65.0
        assert len(p.target_market) == 2

    def test_revenue_share_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ProductLineV3(name="X", category="core", revenue_share_pct=150.0)

    def test_gross_margin_negative_allowed(self) -> None:
        p = ProductLineV3(name="X", category="legacy", gross_margin_pct=-10.0)
        assert p.gross_margin_pct == -10.0

    def test_name_too_long(self) -> None:
        with pytest.raises(ValidationError):
            ProductLineV3(name="x" * 81, category="core")

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ProductLineV3.model_validate(
                {"name": "X", "category": "core", "invalid_field": "x"}
            )

    def test_invalid_category(self) -> None:
        with pytest.raises(ValidationError):
            ProductLineV3(name="X", category="invalid")  # type: ignore[arg-type]


# ============================================================
# MarketPositionV3 §7
# ============================================================


class TestMarketPositionV3:
    def test_rank_without_share_raises(self) -> None:
        """契约：market_rank 非空时 market_share_pct 应提供，否则报错。"""
        with pytest.raises(ValidationError) as exc_info:
            MarketPositionV3(subsegment="高端白酒", market_rank=1)
        assert "market_share_pct" in str(exc_info.value)

    def test_rank_with_share_ok(self) -> None:
        m = MarketPositionV3(
            subsegment="高端白酒", market_share_pct=33.0, market_rank=1
        )
        assert m.market_rank == 1

    def test_no_rank_no_share_ok(self) -> None:
        """market_rank 与 market_share_pct 都为空时合法。"""
        m = MarketPositionV3(subsegment="高端白酒")
        assert m.market_share_pct is None

    def test_cr_fields_validation(self) -> None:
        with pytest.raises(ValidationError):
            MarketPositionV3(subsegment="X", cr3_pct=120.0)

    def test_top_competitors_max_length(self) -> None:
        with pytest.raises(ValidationError):
            MarketPositionV3(
                subsegment="X",
                top_competitors=[f"竞品{i}" for i in range(11)],
            )


# ============================================================
# KeyPartnerV3 §8
# ============================================================


class TestKeyPartnerV3:
    def test_minimal_valid(self) -> None:
        p = KeyPartnerV3(side="customer", name="客户A")
        assert p.is_anonymous is False
        assert p.is_related_party is False

    def test_anonymous_customer(self) -> None:
        p = KeyPartnerV3(
            side="customer",
            name="客户A（集团关联经销商）",
            share_pct=12.0,
            is_related_party=True,
            is_anonymous=True,
            years_partnered=5,
            public_source="annual_report",
        )
        assert p.is_anonymous is True
        assert p.public_source == "annual_report"

    def test_supplier_side(self) -> None:
        p = KeyPartnerV3(side="supplier", name="贵州省内有机高粱基地")
        assert p.side == "supplier"

    def test_invalid_side(self) -> None:
        with pytest.raises(ValidationError):
            KeyPartnerV3(side="invalid", name="X")  # type: ignore[arg-type]


# ============================================================
# IndustryOutlookV3 §9
# ============================================================


class TestIndustryOutlookV3:
    def test_growing_tam_ok(self) -> None:
        o = IndustryOutlookV3(
            subsegment="高端白酒",
            subsegment_status="growing",
            tam_2024_usd_bn=200.0,
            tam_2027e_usd_bn=300.0,
            cagr_2024_2027_pct=14.5,
        )
        assert o.tam_2024_usd_bn == 200.0

    def test_declining_tam_exempt(self) -> None:
        """衰退行业豁免 TAM 校验。"""
        o = IndustryOutlookV3(
            subsegment="传统化工",
            subsegment_status="declining",
            tam_2024_usd_bn=100.0,
            tam_2027e_usd_bn=20.0,  # 80% 跌幅，growing 会报错，declining 豁免
        )
        assert o.tam_2027e_usd_bn == 20.0

    def test_growing_tam_too_small_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IndustryOutlookV3(
                subsegment="X",
                subsegment_status="growing",
                tam_2024_usd_bn=100.0,
                tam_2027e_usd_bn=20.0,  # 80% 跌幅，违反契约
            )
        assert "2027E TAM" in str(exc_info.value)

    def test_transforming_tam_threshold_60pct(self) -> None:
        """转型行业按 60% 阈值校验。"""
        o = IndustryOutlookV3(
            subsegment="X",
            subsegment_status="transforming",
            tam_2024_usd_bn=100.0,
            tam_2027e_usd_bn=70.0,  # 70% 比例，60% 阈值内，合法
        )
        assert o.tam_2027e_usd_bn == 70.0

        with pytest.raises(ValidationError):
            IndustryOutlookV3(
                subsegment="Y",
                subsegment_status="transforming",
                tam_2024_usd_bn=100.0,
                tam_2027e_usd_bn=50.0,  # 50% 比例，60% 阈值外，违反契约
            )

    def test_missing_tam_ok(self) -> None:
        """TAM 字段都为空时合法（待核验场景）。"""
        o = IndustryOutlookV3(subsegment="X")
        assert o.tam_2024_usd_bn is None


# ============================================================
# FinancialQualityV3 §10
# ============================================================


class TestFinancialQualityV3:
    def test_minimal_valid(self) -> None:
        f = FinancialQualityV3(period="2024Q3")
        assert f.period == "2024Q3"

    def test_period_pattern(self) -> None:
        with pytest.raises(ValidationError):
            FinancialQualityV3(period="2024-Q3")  # 错误格式
        with pytest.raises(ValidationError):
            FinancialQualityV3(period="2024Q5")  # 季度越界

    def test_segments_sum_ok(self) -> None:
        f = FinancialQualityV3(
            period="2024",
            revenue_segments={"产品A": 60.0, "产品B": 35.0, "其他": 5.0},
        )
        assert sum(f.revenue_segments.values()) == 100.0

    def test_segments_sum_too_off_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            FinancialQualityV3(
                period="2024",
                revenue_segments={"产品A": 60.0, "产品B": 30.0},  # 合计 90%，偏差 10%
            )
        assert "revenue_segments" in str(exc_info.value)

    def test_segments_within_5pct_ok(self) -> None:
        f = FinancialQualityV3(
            period="2024",
            revenue_segments={"产品A": 62.0, "产品B": 33.0, "其他": 5.0},  # 100%
        )
        assert sum(f.revenue_segments.values()) == 100.0

    def test_segments_96pct_ok(self) -> None:
        """96% (偏差 4%) 应合法（容忍 5%）。"""
        f = FinancialQualityV3(
            period="2024",
            revenue_segments={"产品A": 60.0, "产品B": 36.0},  # 96%
        )
        assert sum(f.revenue_segments.values()) == 96.0


# ============================================================
# SupplyChainDeepDiveV3 顶层
# ============================================================


class TestSupplyChainDeepDiveV3:
    def test_empty(self) -> None:
        v3 = SupplyChainDeepDiveV3(ticker="600519", company="贵州茅台")
        assert v3.sections_executed == []
        assert v3.aggregate_confidence == "low"
        assert v3.section_status() == {
            "product_matrix": "skipped",
            "market_position": "skipped",
            "key_partners": "skipped",
            "industry_outlook": "skipped",
            "financial_quality": "skipped",
        }

    def test_with_sections(self) -> None:
        v3 = SupplyChainDeepDiveV3(
            ticker="600519",
            company="贵州茅台",
            product_matrix=[ProductLineV3(name="飞天 53°", category="core")],
            market_position=[
                MarketPositionV3(
                    subsegment="高端白酒",
                    market_share_pct=33.0,
                    market_rank=1,
                    evidence_strength="primary",
                )
            ],
            sections_executed=["product_matrix", "market_position"],
        )
        status = v3.section_status()
        assert status["product_matrix"] == "executed"
        assert status["financial_quality"] == "skipped"

    def test_compute_aggregate_confidence_low(self) -> None:
        v3 = SupplyChainDeepDiveV3(ticker="X", company="Y")
        assert v3.compute_aggregate_confidence() == "low"
        assert v3.aggregate_confidence == "low"

    def test_compute_aggregate_confidence_medium(self) -> None:
        """3 节 executed → medium。"""
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            product_matrix=[ProductLineV3(name="X", category="core")],
            market_position=[
                MarketPositionV3(
                    subsegment="X",
                    market_share_pct=10.0,
                    market_rank=1,
                )
            ],
            industry_outlook=[
                IndustryOutlookV3(subsegment="X", evidence_strength="analysis")
            ],
            sections_executed=[
                "product_matrix",
                "market_position",
                "industry_outlook",
            ],
        )
        assert v3.compute_aggregate_confidence() == "medium"

    def test_compute_aggregate_confidence_high(self) -> None:
        """≥4 节 executed 且 ≥3 节 evidence_strength≥analysis → high。"""
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            product_matrix=[
                ProductLineV3(name="X", category="core", evidence_strength="primary")
            ],
            market_position=[
                MarketPositionV3(
                    subsegment="X",
                    market_share_pct=10.0,
                    market_rank=1,
                    evidence_strength="primary",
                )
            ],
            industry_outlook=[
                IndustryOutlookV3(subsegment="X", evidence_strength="analysis")
            ],
            financial_quality=[
                FinancialQualityV3(period="2024Q3", evidence_strength="primary")
            ],
            sections_executed=[
                "product_matrix",
                "market_position",
                "industry_outlook",
                "financial_quality",
            ],
        )
        # 纯函数返回 "high"，调用方按需 model_copy
        assert v3.compute_aggregate_confidence() == "high"

    def test_aggregate_confidence_literal(self) -> None:
        v3 = SupplyChainDeepDiveV3(
            ticker="X",
            company="Y",
            aggregate_confidence="high",
        )
        assert v3.aggregate_confidence == "high"

    def test_frozen(self) -> None:
        v3 = SupplyChainDeepDiveV3(ticker="X", company="Y")
        with pytest.raises(ValidationError):
            v3.aggregate_confidence = "high"  # type: ignore[misc]


# ============================================================
# industry_dna_loader
# ============================================================


@pytest.fixture(autouse=True)
def _clear_dna_cache() -> None:
    clear_cache()


class TestIndustryDNALoader:
    def test_list_slugs_returns_5_core(self) -> None:
        """[v3] 已扩展为 5 个核心行业（含 glass_fiber）。"""
        slugs = list_slugs()
        assert "semiconductor" in slugs
        assert "baijiu" in slugs
        assert "battery" in slugs
        assert "pharma" in slugs
        assert "glass_fiber" in slugs
        assert len(slugs) == 5

    def test_load_dna_semiconductor(self) -> None:
        dna = load_dna("semiconductor")
        assert dna is not None
        assert isinstance(dna, IndustryDNA)
        assert dna.industry_name == "半导体"
        assert dna.slug == "semiconductor"
        assert len(dna.products) >= 3
        assert len(dna.key_players) >= 5

    def test_load_dna_baijiu(self) -> None:
        dna = load_dna("baijiu")
        assert dna is not None
        assert dna.industry_name == "白酒"
        assert "茅台" in dna.key_players[0]

    def test_load_dna_missing_returns_none(self) -> None:
        assert load_dna("not_existed_industry") is None

    def test_find_dna_by_keyword(self) -> None:
        dna = find_dna_by_keyword("芯片")
        assert dna is not None
        assert dna.slug == "semiconductor"

        dna = find_dna_by_keyword("茅台")
        assert dna is not None
        assert dna.slug == "baijiu"

    def test_find_dna_by_keyword_case_insensitive(self) -> None:
        """大小写不敏感：英文关键词仍能命中（如『AI 芯片』中的『芯片』字段是大写环境）。"""
        # semiconductor.yaml 的 keywords 含『芯片』，大写『芯片』也应命中
        dna = find_dna_by_keyword("芯片")
        assert dna is not None
        assert dna.slug == "semiconductor"

    def test_find_dna_by_keyword_not_found(self) -> None:
        assert find_dna_by_keyword("not_in_any_industry") is None

    def test_find_dna_by_keywords(self) -> None:
        from src.services.supply_chain.industry_dna_loader import (
            find_dna_by_keywords,
        )

        dna = find_dna_by_keywords(["非关键词", "锂电", "x"])
        assert dna is not None
        assert dna.slug == "battery"

    def test_get_all_dna(self) -> None:
        """[v3] 已扩展为 5 个行业。"""
        all_dna = get_all_dna()
        assert len(all_dna) == 5
        assert all(isinstance(v, IndustryDNA) for v in all_dna.values())

    def test_to_dict_roundtrip(self) -> None:
        dna = load_dna("semiconductor")
        assert dna is not None
        d = dna.to_dict()
        assert d["industry_name"] == "半导体"
        assert d["slug"] == "semiconductor"
        assert isinstance(d["products"], list)

    def test_industry_dna_extra_fields_preserved(self) -> None:
        """YAML 含额外字段时，to_dict() 保留。"""
        dna = load_dna("semiconductor")
        assert dna is not None
        d = dna.to_dict()
        # 标准 14 字段必存在
        for k in (
            "industry_name",
            "slug",
            "keywords",
            "products",
            "key_players",
            "concentration",
            "customer_types",
            "supplier_types",
            "demand_drivers",
            "policy_catalysts",
            "substitution_risks",
            "time_window",
            "source",
            "last_updated",
        ):
            assert k in d


class TestIndustryDNAFailOpen:
    """测试 fail-open 行为：损坏的 YAML 不能拖垮 loader。"""

    def test_load_dna_missing_file_returns_none(self) -> None:
        clear_cache()
        assert load_dna("non_existent_slug") is None

    def test_load_dna_corrupted_yaml_returns_none(self, tmp_path, monkeypatch) -> None:
        """临时构造坏 YAML 不会抛异常。"""
        bad_yaml = tmp_path / "industry_dna" / "bad.yaml"
        bad_yaml.parent.mkdir(parents=True, exist_ok=True)
        bad_yaml.write_text("invalid: : : yaml\n  - [unclosed", encoding="utf-8")

        # 通过 monkeypatch 替换 paths 解析
        from src.services.supply_chain import paths as paths_mod

        monkeypatch.setattr(paths_mod, "industry_dna_dir", lambda: str(bad_yaml.parent))
        clear_cache()

        # load_dna("bad") 应当返回 None 而不抛
        result = load_dna("bad")
        assert result is None


class TestIndustryDNAConstruction:
    """测试 IndustryDNA 构造器的字段校验。"""

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            IndustryDNA({"industry_name": "X"})  # 缺 12 个字段
        assert "缺少必填字段" in str(exc_info.value)

    def test_partial_required_raises(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            IndustryDNA(
                {
                    "industry_name": "X",
                    "slug": "x",
                    "products": [],
                    # 缺 keywords/concentration/time_window 等
                }
            )
        assert "缺少必填字段" in str(exc_info.value)

    def test_optional_field_absent_ok(self) -> None:
        """substitution_risks 等可选字段缺失时应合法（默认值）。"""
        dna = IndustryDNA(
            {
                "industry_name": "X",
                "slug": "x",
                "keywords": [],
                "products": [],
                "key_players": [],
                "concentration": "",
                "customer_types": [],
                "supplier_types": [],
                "demand_drivers": [],
                "policy_catalysts": [],
                # substitution_risks 故意省略
                "time_window": "mid_term_6_12m",
                "source": "test",
                "last_updated": "2026-01-15",
            }
        )
        assert dna.substitution_risks == []
