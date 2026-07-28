# -*- coding: utf-8 -*-
"""行业 DNA 静态数据加载器（v3）。

职责：
- 加载 ``data/supply_chain_skill/industry_dna/*.yaml`` 静态兜底数据
- 提供按 ``slug`` / ``keyword`` 两种查询方式
- 行业匹配（基于 ``keywords`` 字段）返回首个命中的 DNA

设计要点：
- YAML 优先于 JSON：注释友好 + 维护成本低
- 加载缓存（lru_cache）：同一进程只读一次磁盘
- 加载失败 fail-open：单文件解析异常不拖垮其它文件
- 与 SupplyChainKBRetriever 并联：KB 命中 < 3 时优先读 DNA

Schema：每个 YAML 必须含以下 8 个核心字段（其余可选）：
  industry_name    str         行业名（中文）
  slug             str         文件 slug（与文件名一致）
  keywords         list[str]   行业关键词（用于匹配）
  products         list[str]   主线产品清单
  key_players      list[str]   全球/国内 Top5
  concentration    str         CR3/CR5/CR10 描述
  customer_types   list[str]   主要客户类别
  supplier_types   list[str]   主要供应商类别
  demand_drivers   list[str]   需求驱动因素
  policy_catalysts list[str]   政策催化
  substitution_risks list[str] 替代风险
  time_window      str         默认分析时间窗（near/mid/long）
  source           str         数据来源说明
  last_updated     str         最后更新日期（YYYY-MM-DD）
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from src.services.supply_chain.paths import industry_dna_dir, industry_dna_path

logger = logging.getLogger(__name__)

# 核心必填字段（其余可选）
REQUIRED_DNA_FIELDS: tuple[str, ...] = (
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
    "time_window",
    "source",
    "last_updated",
)

# 可选字段（缺失时使用默认值，不视为错误）
OPTIONAL_DNA_FIELDS: tuple[str, ...] = (
    "substitution_risks",
    "overseas_addressable",
    "tam_2024_usd_bn",
    "tam_2027e_usd_bn",
)


class IndustryDNA:
    """单个行业 DNA 数据结构（frozen 风格）。

    所有字段从 YAML 加载；构造时校验必填字段，避免运行时 NPE。
    """

    __slots__ = (
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
        "extra",
    )

    def __init__(self, raw: Dict[str, Any]) -> None:
        missing = [k for k in REQUIRED_DNA_FIELDS if k not in raw]
        if missing:
            raise ValueError(
                f"IndustryDNA 解析失败：缺少必填字段 {missing}。"
                f"请检查 YAML 文件是否含全部 14 个核心字段。"
            )
        self.industry_name: str = str(raw["industry_name"])
        self.slug: str = str(raw["slug"])
        self.keywords: List[str] = [str(k) for k in raw.get("keywords", []) or []]
        self.products: List[str] = [str(p) for p in raw.get("products", []) or []]
        self.key_players: List[str] = [str(p) for p in raw.get("key_players", []) or []]
        self.concentration: str = str(raw.get("concentration", ""))
        self.customer_types: List[str] = [
            str(c) for c in raw.get("customer_types", []) or []
        ]
        self.supplier_types: List[str] = [
            str(s) for s in raw.get("supplier_types", []) or []
        ]
        self.demand_drivers: List[str] = [
            str(d) for d in raw.get("demand_drivers", []) or []
        ]
        self.policy_catalysts: List[str] = [
            str(p) for p in raw.get("policy_catalysts", []) or []
        ]
        self.substitution_risks: List[str] = [
            str(s) for s in raw.get("substitution_risks", []) or []
        ]
        self.time_window: str = str(raw.get("time_window", "mid_term_6_12m"))
        self.source: str = str(raw.get("source", ""))
        self.last_updated: str = str(raw.get("last_updated", ""))
        # 额外字段（保留，便于后续扩展）
        self.extra: Dict[str, Any] = {
            k: v for k, v in raw.items() if k not in REQUIRED_DNA_FIELDS
        }

    def to_dict(self) -> Dict[str, Any]:
        """转 dict，供 Pydantic 校验后构造 ProductLineV3 / IndustryOutlookV3 等。"""
        result: Dict[str, Any] = {
            "industry_name": self.industry_name,
            "slug": self.slug,
            "keywords": list(self.keywords),
            "products": list(self.products),
            "key_players": list(self.key_players),
            "concentration": self.concentration,
            "customer_types": list(self.customer_types),
            "supplier_types": list(self.supplier_types),
            "demand_drivers": list(self.demand_drivers),
            "policy_catalysts": list(self.policy_catalysts),
            "substitution_risks": list(self.substitution_risks),
            "time_window": self.time_window,
            "source": self.source,
            "last_updated": self.last_updated,
        }
        result.update(self.extra)
        return result


def _load_yaml_safe(path: str) -> Optional[Dict[str, Any]]:
    """安全加载 YAML 文件，失败返回 None。

    优先用 ``yaml.safe_load``（PyYAML）；缺失则尝试 ``json`` 兜底（保持向后兼容）。
    """
    if not os.path.isfile(path):
        return None
    try:
        import yaml  # type: ignore[import-not-found]

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            logger.warning("[IndustryDNA] %s 顶层不是 dict，已跳过", path)
            return None
        return data
    except ImportError:
        # PyYAML 缺失时降级到 JSON（极简兜底，仅支持 json 后缀）
        try:
            import json

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IndustryDNA] %s 加载失败: %s", path, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IndustryDNA] %s 解析异常: %s", path, exc)
        return None


@lru_cache(maxsize=64)
def load_dna(slug: str) -> Optional[IndustryDNA]:
    """按 slug 加载单个 DNA（缓存）。失败返回 None（fail-open）。"""
    path = industry_dna_path(slug)
    raw = _load_yaml_safe(path)
    if raw is None:
        return None
    try:
        return IndustryDNA(raw)
    except ValueError as exc:
        logger.warning("[IndustryDNA] %s 校验失败: %s", slug, exc)
        return None


@lru_cache(maxsize=1)
def list_slugs() -> tuple[str, ...]:
    """列出所有可用行业 slug（缓存）。

    目录不存在 / 为空时返回空元组。
    """
    d = industry_dna_dir()
    if not os.path.isdir(d):
        logger.info("[IndustryDNA] DNA 目录不存在: %s", d)
        return ()
    try:
        files = sorted(os.listdir(d))
    except OSError as exc:
        logger.warning("[IndustryDNA] 列举 %s 失败: %s", d, exc)
        return ()
    slugs: List[str] = []
    for name in files:
        if name.endswith((".yaml", ".yml")):
            slugs.append(os.path.splitext(name)[0])
    return tuple(slugs)


@lru_cache(maxsize=1)
def _load_all_dna() -> Dict[str, IndustryDNA]:
    """加载目录下所有 DNA（缓存）。"""
    out: Dict[str, IndustryDNA] = {}
    for slug in list_slugs():
        dna = load_dna(slug)
        if dna is not None:
            out[slug] = dna
    return out


def find_dna_by_keyword(keyword: str) -> Optional[IndustryDNA]:
    """按关键词在 ``keywords`` 字段查找首个命中的 DNA。

    大小写不敏感；空字符串返回 None。
    """
    if not keyword:
        return None
    kw_lower = keyword.strip().lower()
    for dna in _load_all_dna().values():
        if any(kw_lower in str(k).lower() for k in dna.keywords):
            return dna
    return None


def find_dna_by_keywords(keywords: List[str]) -> Optional[IndustryDNA]:
    """按关键词列表查找首个命中的 DNA（任一关键词命中即返回）。"""
    for kw in keywords or ():
        dna = find_dna_by_keyword(kw)
        if dna is not None:
            return dna
    return None


def get_all_dna() -> Dict[str, IndustryDNA]:
    """返回所有已加载 DNA（slug -> DNA）。"""
    return dict(_load_all_dna())


def clear_cache() -> None:
    """清空所有 lru_cache（用于测试或热更新）。"""
    load_dna.cache_clear()
    list_slugs.cache_clear()
    _load_all_dna.cache_clear()
