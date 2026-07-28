# -*- coding: utf-8 -*-
"""[v3 PR-C] 深度小节 Markdown 渲染器。

职责：把 :class:`SupplyChainDeepDiveV3` 渲染成 Markdown §5（白话摘要兜底）+ §6-§10
量化深度小节 + 数据完整性披露脚注。每个小节独立渲染，单节为空就跳过整节，不抛异常。

设计要点：
- 与 ``SupplyChainReportService`` 解耦：纯函数 + 顶层 helper，便于单测
- 复用现有 markdown 表格风格（与 Serenity 报告一致）
- 中文显示：所有章节标题、表头用中文，列分隔符 `|`
- fail-open：单个 section 渲染失败 → 跳过该节 + 写入「待核验」脚注，绝不阻断整篇
- §5 是「白话摘要」兜底：LLM 已写时跳过（避免重复），LLM 未写时从 §7 数据派生

不修改任何现有渲染函数（``render`` in ``src/services/report_renderer.py` 保持不动）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.schemas.supply_chain import (
    FinancialQualityV3,
    IndustryOutlookV3,
    KeyPartnerV3,
    MarketPositionV3,
    ProductLineV3,
    SupplyChainDeepDiveV3,
)

# ============================================================
# 枚举本地化（schema 接受英文值，渲染层展示中文）
# ============================================================

_CATEGORY_CN: Dict[str, str] = {
    "core": "核心",
    "growth": "成长",
    "legacy": "传统",
    "exploratory": "探索",
}
_EVIDENCE_CN: Dict[str, str] = {
    "primary": "原始",
    "media": "媒体",
    "analysis": "分析",
    "kb_doc": "知识库",
    "social": "社交",
    "rumor": "传闻",
}
_TREND_CN: Dict[str, str] = {
    "rising": "↗ 上升",
    "stable": "→ 平稳",
    "falling": "↘ 下降",
    "volatile": "波动",
    "unknown": "未知",
}
_RISK_CN: Dict[str, str] = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "unknown": "未知",
}
_STATUS_CN: Dict[str, str] = {
    "growing": "增长",
    "stable": "稳定",
    "declining": "衰退",
    "transforming": "转型",
}
_TIME_CN: Dict[str, str] = {
    "near_term_3_6m": "短期 3-6 月",
    "mid_term_6_12m": "中期 6-12 月",
    "long_term_12_36m": "长期 12-36 月",
}
_CONFIDENCE_CN: Dict[str, str] = {"high": "高", "medium": "中", "low": "低"}


def _cn(value: Any, table: Dict[str, str], default: str = "—") -> str:
    """枚举本地化：英文 → 中文；不在表内则原样返回。"""
    if value is None:
        return default
    s = str(value)
    return table.get(s, s) if s else default


# ============================================================
# 单节渲染（5 张表 + §5 白话摘要兜底）
# ============================================================


def render_market_position_summary(
    deep_dive: SupplyChainDeepDiveV3,
    llm_markdown: str = "",
) -> str:
    """[v3 收敛] §5「市场地位与竞品」白话摘要兜底。

    设计目的：把用户原始诉求里"行业定位 / 核心竞争优势 / 与主要竞争对手对比 / 市场地位与
    市场占有率 / 市占率 / 行业排名 / 龙头地位 / 数据来源"这些重复字段**合并到一节**，
    由结构化数据派生，避免 LLM 在 §5 与 §7 重复描述。

    规则：
    - LLM 已在主报告写过 §5（`## 5.` 或 `### 5` 标题）→ 返回空字符串（不重复）
    - 没有任何 market_position / product_matrix 数据 → 返回空字符串（避免凭空捏造）
    - 否则：渲染 §5 标题 + 4 个子模块（行业定位 / 核心竞争优势 / 与主要竞争对手对比 /
      数据来源），全部基于 §6 / §7 结构化数据派生
    """
    if not deep_dive.market_position and not deep_dive.product_matrix:
        return ""
    if llm_markdown:
        markers = [
            "## 5.",
            "### 5.",
            "## 五、",
            "## 二、5",
            "## 二、基本面分析\n\n### 5",
        ]
        if any(m in llm_markdown for m in markers):
            return ""
    lines: List[str] = ["## 5. 市场地位与竞品"]
    # §5.1 行业定位（基于 product_matrix + market_position 综合）
    if deep_dive.product_matrix:
        core = [p for p in deep_dive.product_matrix if p.category == "core"]
        growth = [p for p in deep_dive.product_matrix if p.category == "growth"]
        anchor = core[0] if core else (deep_dive.product_matrix[0])
        position_bits: List[str] = []
        if anchor.revenue_share_pct is not None:
            position_bits.append(
                f"核心产品「{anchor.name}」营收占比 {anchor.revenue_share_pct:.0f}%"
            )
        if anchor.gross_margin_pct is not None:
            position_bits.append(f"毛利率 {anchor.gross_margin_pct:.0f}%")
        if anchor.target_market:
            position_bits.append(f"目标市场 {anchor.target_market[0]}")
        if growth:
            position_bits.append(f"成长曲线产品 {len(growth)} 个")
        if position_bits:
            lines.append("")
            lines.append("### 5.1 行业定位")
            lines.append("")
            lines.append("；".join(position_bits) + "。")
    # §5.2 / §5.3 核心竞争优势 + 与主要竞争对手对比（合并：基于 market_position）
    if deep_dive.market_position:
        lines.append("")
        lines.append("### 5.2 核心竞争优势 与 §5.3 与主要竞争对手对比")
        lines.append("")
        lines.append("| 子赛道 | 排名 | 地位 | 主要竞品 | 替代风险 |")
        lines.append("|---|---:|---|---|---|")
        for m in deep_dive.market_position:
            rank_text = (
                f"第 {m.market_rank}" if m.market_rank is not None else "未披露排名"
            )
            share_text = (
                f"份额 {m.market_share_pct:.0f}%"
                if m.market_share_pct is not None
                else "份额待核验"
            )
            leadership = (
                "龙头"
                if (m.market_rank == 1 and m.market_share_pct is not None)
                else (
                    "领先"
                    if (m.market_rank is not None and m.market_rank <= 3)
                    else "跟随"
                )
            )
            comp = "、".join(m.top_competitors[:3]) if m.top_competitors else "—"
            risk = _cn(m.substitution_risk, _RISK_CN, "未知")
            lines.append(
                f"| {m.subsegment} | {rank_text} | "
                f"{leadership}（{share_text}）| {comp} | {risk} |"
            )
        # 集中描述（避免再列重复表格）
        leaders = [
            m
            for m in deep_dive.market_position
            if m.market_rank == 1 and m.market_share_pct is not None
        ]
        if leaders:
            bits = [
                f"{m.subsegment} 龙头（市占 {m.market_share_pct:.0f}%）"
                for m in leaders
            ]
            lines.append("")
            lines.append("公司在上述子赛道处于龙头地位：" + "；".join(bits) + "。")
    # §5.4 数据来源
    sources = sorted(
        {
            str(m.evidence_strength)
            for m in deep_dive.market_position
            if m.evidence_strength
        }
        | {
            str(p.evidence_strength)
            for p in deep_dive.product_matrix
            if p.evidence_strength
        }
    )
    if sources:
        lines.append("")
        lines.append("### 5.4 数据来源")
        lines.append("")
        lines.append(
            "上述摘要基于结构化数据自动派生，证据强度："
            + "、".join(_cn(s, _EVIDENCE_CN, s) for s in sources)
            + "。具体数字与证据见 §6-§10。"
        )
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def render_product_matrix(products: List[ProductLineV3]) -> str:
    """§6 产品矩阵与定位（v3 第一深度小节）。products 按 revenue_share_pct 降序。"""
    if not products:
        return ""
    sorted_p = sorted(
        products,
        key=lambda x: (x.revenue_share_pct is None, -(x.revenue_share_pct or 0)),
    )
    lines: List[str] = [
        "## 6. 产品矩阵与定位",
        "",
        "| 产品 | 战略定位 | 营收占比 | 毛利率 | 目标市场 | 价格带 | 差异化卖点 | 证据 |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    for p in sorted_p:
        rev = f"{p.revenue_share_pct:.1f}%" if p.revenue_share_pct is not None else "—"
        gm = f"{p.gross_margin_pct:.1f}%" if p.gross_margin_pct is not None else "—"
        market = "、".join(p.target_market) if p.target_market else "—"
        price = p.price_band or "—"
        diff = "、".join(p.differentiators[:3]) if p.differentiators else "—"
        category_cn = _cn(p.category, _CATEGORY_CN, p.category)
        evidence_cn = _cn(p.evidence_strength, _EVIDENCE_CN, p.evidence_strength)
        lines.append(
            f"| {p.name} | {category_cn} | {rev} | {gm} | {market} | "
            f"{price} | {diff} | {evidence_cn} |"
        )
    return "\n".join(lines)


def render_market_position(positions: List[MarketPositionV3]) -> str:
    """§7 市场占有率（含行业排名/龙头地位）（v3 第二深度小节）。"""
    if not positions:
        return ""
    lines: List[str] = [
        "## 7. 市场占有率（含行业排名/龙头地位）",
        "",
        "| 子赛道 | 份额 | 排名 | CR3 | CR5 | 份额趋势 | 3 年变化 | 主要竞品 | 替代风险 | 证据 |",
        "|---|---:|---:|---:|---:|---|---:|---|---|---|",
    ]
    for m in positions:
        share = (
            f"{m.market_share_pct:.1f}%" if m.market_share_pct is not None else "待核验"
        )
        rank = str(m.market_rank) if m.market_rank is not None else "—"
        cr3 = f"{m.cr3_pct:.1f}%" if m.cr3_pct is not None else "—"
        cr5 = f"{m.cr5_pct:.1f}%" if m.cr5_pct is not None else "—"
        trend = _cn(m.share_trend, _TREND_CN, "未知")
        chg = (
            f"{m.share_change_3y_pct:+.1f}pct"
            if m.share_change_3y_pct is not None
            else "—"
        )
        comp = "、".join(m.top_competitors[:3]) if m.top_competitors else "—"
        risk = _cn(m.substitution_risk, _RISK_CN, "未知")
        evidence_cn = _cn(m.evidence_strength, _EVIDENCE_CN, m.evidence_strength)
        lines.append(
            f"| {m.subsegment} | {share} | {rank} | {cr3} | {cr5} | "
            f"{trend} | {chg} | {comp} | {risk} | {evidence_cn} |"
        )
    return "\n".join(lines)


def render_key_customers(customers: List[KeyPartnerV3]) -> str:
    """§8.1 主要客户。"""
    if not customers:
        return ""
    lines: List[str] = [
        "### 8.1 主要客户",
        "",
        "| 客户名称 | 份额 | 关联方 | 匿名 | 合作年限 | 披露来源 | 证据 |",
        "|---|---:|:---:|:---:|---:|---|---|",
    ]
    for c in customers:
        share = f"{c.share_pct:.1f}%" if c.share_pct is not None else "—"
        rp = "是" if c.is_related_party else "否"
        anon = "是" if c.is_anonymous else "否"
        years = f"{c.years_partnered} 年" if c.years_partnered is not None else "—"
        evidence_cn = _cn(c.evidence_strength, _EVIDENCE_CN, c.evidence_strength)
        lines.append(
            f"| {c.name} | {share} | {rp} | {anon} | {years} | "
            f"{c.public_source} | {evidence_cn} |"
        )
    return "\n".join(lines)


def render_key_suppliers(suppliers: List[KeyPartnerV3]) -> str:
    """§8.2 主要供应商。"""
    if not suppliers:
        return ""
    lines: List[str] = [
        "### 8.2 主要供应商",
        "",
        "| 供应商名称 | 采购占比 | 关联方 | 匿名 | 合作年限 | 披露来源 | 证据 |",
        "|---|---:|:---:|:---:|---:|---|---|",
    ]
    for s in suppliers:
        share = f"{s.share_pct:.1f}%" if s.share_pct is not None else "—"
        rp = "是" if s.is_related_party else "否"
        anon = "是" if s.is_anonymous else "否"
        years = f"{s.years_partnered} 年" if s.years_partnered is not None else "—"
        evidence_cn = _cn(s.evidence_strength, _EVIDENCE_CN, s.evidence_strength)
        lines.append(
            f"| {s.name} | {share} | {rp} | {anon} | {years} | "
            f"{s.public_source} | {evidence_cn} |"
        )
    return "\n".join(lines)


def render_industry_outlook(outlooks: List[IndustryOutlookV3]) -> str:
    """§9 行业前景与需求驱动（v3 第四深度小节）。"""
    if not outlooks:
        return ""
    lines: List[str] = [
        "## 9. 行业前景与需求驱动",
        "",
        "| 子赛道 | 状态 | 2024 TAM (USD bn) | 2027E TAM | CAGR | 中国份额 | 需求驱动 | 政策催化 | 替代风险 | 海外空间 | 时间窗 |",
        "|---|---|---:|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for o in outlooks:
        tam24 = f"{o.tam_2024_usd_bn:.1f}" if o.tam_2024_usd_bn is not None else "—"
        tam27 = f"{o.tam_2027e_usd_bn:.1f}" if o.tam_2027e_usd_bn is not None else "—"
        cagr = (
            f"{o.cagr_2024_2027_pct:+.1f}%" if o.cagr_2024_2027_pct is not None else "—"
        )
        cn = f"{o.china_share_pct:.1f}%" if o.china_share_pct is not None else "—"
        drv = "、".join(o.demand_drivers[:3]) if o.demand_drivers else "—"
        pol = "、".join(o.policy_catalysts[:2]) if o.policy_catalysts else "—"
        sub = "、".join(o.substitution_threats[:2]) if o.substitution_threats else "—"
        overseas = o.overseas_addressable or "—"
        status_cn = _cn(o.subsegment_status, _STATUS_CN, o.subsegment_status)
        time_cn = _cn(o.time_window, _TIME_CN, o.time_window)
        lines.append(
            f"| {o.subsegment} | {status_cn} | {tam24} | {tam27} | {cagr} "
            f"| {cn} | {drv} | {pol} | {sub} | {overseas} | {time_cn} |"
        )
    return "\n".join(lines)


def render_financial_quality(reports: List[FinancialQualityV3]) -> str:
    """§10 财务质量与产能跟踪（v3 第五深度小节）。"""
    if not reports:
        return ""
    lines: List[str] = [
        "## 10. 财务质量与产能跟踪",
        "",
        "| period | 营收同比 | 毛利率 | 毛利率同比 | 经营现金流同比 | 应收/营收 | 存货天数 | 合同负债同比 | capex 强度 | 产能利用率 | red_flags |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for f in reports:
        rev = f"{f.revenue_yoy_pct:+.1f}%" if f.revenue_yoy_pct is not None else "—"
        gm = f"{f.gross_margin_pct:.1f}%" if f.gross_margin_pct is not None else "—"
        gm_chg = (
            f"{f.gross_margin_change_yoy_pct:+.1f}pct"
            if f.gross_margin_change_yoy_pct is not None
            else "—"
        )
        ocf = (
            f"{f.operating_cash_flow_yoy_pct:+.1f}%"
            if f.operating_cash_flow_yoy_pct is not None
            else "—"
        )
        ar = f"{f.ar_to_revenue_pct:.1f}%" if f.ar_to_revenue_pct is not None else "—"
        inv = f"{f.inventory_days} 天" if f.inventory_days is not None else "—"
        cl = (
            f"{f.contract_liability_yoy_pct:+.1f}%"
            if f.contract_liability_yoy_pct is not None
            else "—"
        )
        cap = (
            f"{f.capex_intensity_pct:.1f}%"
            if f.capex_intensity_pct is not None
            else "—"
        )
        util = (
            f"{f.capacity_utilization_pct:.1f}%"
            if f.capacity_utilization_pct is not None
            else "—"
        )
        flags = "、".join(f.red_flags[:3]) if f.red_flags else "—"
        lines.append(
            f"| {f.period} | {rev} | {gm} | {gm_chg} | {ocf} | {ar} | "
            f"{inv} | {cl} | {cap} | {util} | {flags} |"
        )
    # 分业务收入占比附在 §10 末尾
    seg_lines: List[str] = []
    for f in reports:
        if f.revenue_segments:
            seg_text = "、".join(f"{k} {v:.1f}%" for k, v in f.revenue_segments.items())
            seg_lines.append(f"- **{f.period} 分业务收入占比**：{seg_text}")
    if seg_lines:
        lines.append("")
        lines.append("**分业务收入占比：**")
        lines.extend(seg_lines)
    return "\n".join(lines)


def render_section_status(deep_dive: SupplyChainDeepDiveV3) -> str:
    """数据完整性披露脚注。"""
    status = deep_dive.section_status()
    all_secs = [
        ("product_matrix", "§6 产品矩阵与定位"),
        ("market_position", "§7 市场占有率"),
        ("key_partners", "§8 关键客户与供应商"),
        ("industry_outlook", "§9 行业前景与需求驱动"),
        ("financial_quality", "§10 财务质量与产能跟踪"),
    ]
    lines = [
        "## 数据完整性披露",
        "",
        "| 小节 | 状态 |",
        "|---|:---:|",
    ]
    for key, label in all_secs:
        marker = "✓" if status[key] == "executed" else "✗"
        lines.append(f"| {label} | {marker} |")
    conf_map = {"high": "高", "medium": "中", "low": "低"}
    lines.append("")
    lines.append(
        f"**Aggregate Confidence**：{conf_map.get(deep_dive.aggregate_confidence, '—')}"
    )
    lines.append("")
    lines.append(
        f"截至时间：{deep_dive.fetched_at.isoformat() if deep_dive.fetched_at else '—'}"
    )
    return "\n".join(lines)


# ============================================================
# 顶层入口
# ============================================================


def render_deep_dive_sections(
    deep_dive: SupplyChainDeepDiveV3,
    llm_markdown: str = "",
) -> str:
    """把 SupplyChainDeepDiveV3 渲染成完整 Markdown（§6-§10 + 脚注，§5 由 LLM 提供）。

    - 单节为空 → 跳过整节
    - 渲染异常 → 整篇降级为占位文本，绝不抛
    - ``llm_markdown`` 用于 §5 检测：LLM 已写 §5 时不重复生成（避免白话摘要重复）
    """
    try:
        sections: List[str] = []
        # §5 白话摘要兜底：LLM 没写时由 §7 数据派生（避免报告出现「§5 漏写」）
        summary = render_market_position_summary(deep_dive, llm_markdown)
        if summary:
            sections.append(summary)
        if deep_dive.product_matrix:
            sections.append(render_product_matrix(deep_dive.product_matrix))
        if deep_dive.market_position:
            sections.append(render_market_position(deep_dive.market_position))
        if deep_dive.key_customers or deep_dive.key_suppliers:
            customer_md = render_key_customers(deep_dive.key_customers)
            supplier_md = render_key_suppliers(deep_dive.key_suppliers)
            partner_header = "## 8. 关键客户与供应商"
            partner_parts = [partner_header, ""]
            if customer_md:
                partner_parts.append(customer_md)
            if supplier_md:
                partner_parts.append(supplier_md)
            sections.append("\n\n".join(partner_parts))
        if deep_dive.industry_outlook:
            sections.append(render_industry_outlook(deep_dive.industry_outlook))
        if deep_dive.financial_quality:
            sections.append(render_financial_quality(deep_dive.financial_quality))
        # 数据完整性披露脚注（始终输出，即使所有 section 都为空）
        sections.append(render_section_status(deep_dive))
        return "\n\n".join(s for s in sections if s)
    except Exception as exc:  # noqa: BLE001
        return (
            f"## 数据完整性披露\n\n"
            f"⚠ 深度小节渲染失败：{exc!r}\n\n"
            f"Aggregate Confidence：—\n"
        )


def render_empty_deep_dive_placeholder() -> str:
    """灰度关闭或上游未提供 deep_dive 时的占位渲染（空字符串）。"""
    return ""


# ============================================================
# 解析辅助（从 LLM 输出中提取 §6-§10 Markdown 块）
# ============================================================


def extract_deep_dive_section_from_markdown(markdown: str) -> str:
    """从完整报告中提取 §6-§10 + 脚注段（如果存在）。

    用法：``extract_deep_dive_section_from_markdown(executor_result.content)``。
    找不到 → 返回空字符串。
    """
    if not markdown:
        return ""
    markers = ["## 6.", "## 数据完整性披露"]
    start_idx = -1
    for marker in markers:
        idx = markdown.find(marker)
        if idx >= 0 and (start_idx < 0 or idx < start_idx):
            start_idx = idx
    if start_idx < 0:
        return ""
    return markdown[start_idx:].rstrip() + "\n"
