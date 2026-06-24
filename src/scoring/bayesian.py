# -*- coding: utf-8 -*-
"""仓位集中度校验（贝叶斯框架配套）。

提供 ``api/v1/endpoints/research_framework.py`` 引用的
``validate_position_with_concentration``——校验建议仓位在当前集中度下是否合规。

背景：该函数此前被 ``research_framework.py`` 顶层 import，但实现缺失
（``src/scoring/`` 在 git 中从未提交），导致整个 ``api.v1.router`` import 失败、
FastAPI 服务无法启动。本模块补全该实现，逻辑与 ``research_framework.py``
的仓位验证端点用法对齐（``current_concentration > 0.35`` 触发警告）。

阈值规则：
- 当前板块/个股集中度 > 35% → 拒绝（集中度过高）
- 单一建议仓位 > 50% → 拒绝（单仓位过大）
- 否则通过

如需更精细的贝叶斯/风险模型校验，可在此扩展（参考
``src/services/research_scoring_service.py`` 的 calculate_bayesian 输出）。
"""

from __future__ import annotations

from typing import Optional, Tuple

# 集中度/单仓位阈值（与 research_framework.py 的 endpoint 用法对齐）
_SECTOR_CONCENTRATION_LIMIT = 0.35
_SINGLE_POSITION_LIMIT = 0.50


def validate_position_with_concentration(
    position_suggestion: Optional[float],
    current_concentration: float = 0.0,
) -> Tuple[bool, Optional[str]]:
    """验证仓位建议是否合适（考虑当前集中度）。

    Args:
        position_suggestion: 建议的单一仓位大小（占比 0-1），可 None。
        current_concentration: 当前板块/个股集中度（占比 0-1）。

    Returns:
        ``(valid, warning)``：是否合规 + 警告信息（合规时为 None）。
    """
    try:
        concentration = float(current_concentration or 0.0)
    except (TypeError, ValueError):
        concentration = 0.0

    if concentration > _SECTOR_CONCENTRATION_LIMIT:
        return False, "Current sector concentration is already high"

    try:
        position = float(position_suggestion) if position_suggestion is not None else None
    except (TypeError, ValueError):
        position = None

    if position is not None and position > _SINGLE_POSITION_LIMIT:
        return False, "Single position size exceeds 50% threshold"

    return True, None
