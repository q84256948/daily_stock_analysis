# -*- coding: utf-8 -*-
"""供应链分析 skill 数据目录定位。

数据落在 ``<repo>/data/supply_chain_skill/``（迁移自 serenity-skill，MIT），结构::

    SKILL.md                        核心方法论指令（236 行）
    references/                     8 个深度参考（按需注入 system prompt）
    assets/                         打分卡模板 / prompt 包 / 研报模板
    scripts/serenity_scorecard.py   瓶颈打分纯函数库（8 因子 + 8 惩罚）
    examples/                       输出样例（few-shot）
    evals/test-cases.md             6 个行为测试

路径可用环境变量 ``SUPPLY_CHAIN_DATA_DIR`` 覆盖。
"""

import os
from functools import lru_cache

# src/services/supply_chain/paths.py -> 上溯 4 级到仓库根
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_DEFAULT_DATA_DIR = os.path.join(_REPO_ROOT, "data", "supply_chain_skill")

# 注入 system prompt 的核心 references（审计修正：serenity-dialogue-protocol 是正确文件名）
CORE_REFERENCES = (
    "deep-research-workflow",
    "evidence-ladder",
    "market-source-playbook",
    "serenity-dialogue-protocol",
    "output-style-and-language",
)


@lru_cache(maxsize=1)
def data_dir() -> str:
    """供应链 skill 数据根目录。"""
    return os.environ.get("SUPPLY_CHAIN_DATA_DIR") or _DEFAULT_DATA_DIR


def skill_path() -> str:
    return os.path.join(data_dir(), "SKILL.md")


def references_dir() -> str:
    return os.path.join(data_dir(), "references")


def reference_path(name: str) -> str:
    return os.path.join(references_dir(), f"{name}.md")


def scorecard_script_path() -> str:
    return os.path.join(data_dir(), "scripts", "serenity_scorecard.py")


# ============================================================
# [v3] 行业 DNA 数据目录（产品·客户·竞争·前景 静态兜底）
# ============================================================
# 行业 DNA 是 v3 报告深度的静态兜底数据（KB 命中不足时使用）。
# 每个行业一个 YAML 文件，覆盖核心 8 字段：
#   products / key_players / concentration / customer_types / supplier_types
#   demand_drivers / policy_catalysts / time_window
# YAML 优先于 JSON：注释友好、便于维护、可读性强。
# 路径可由环境变量 SUPPLY_CHAIN_DNA_DIR 覆盖（与 SUPPLY_CHAIN_DATA_DIR 互不干扰）。


def industry_dna_dir() -> str:
    """行业 DNA 数据根目录（v3）。"""
    return os.environ.get("SUPPLY_CHAIN_DNA_DIR") or os.path.join(
        data_dir(), "industry_dna"
    )


def industry_dna_path(slug: str) -> str:
    """单个行业 DNA 文件路径：<slug>.yaml。"""
    return os.path.join(industry_dna_dir(), f"{slug}.yaml")
