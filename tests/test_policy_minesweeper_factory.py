# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — factory builder 单元测试。

验证 ``build_policy_minesweeper_executor``：
- 工具集精确：5 个 wengu 筛选工具 + 1 个 ``score_policy_minesweeper``，无 backtest/博弈噪音。
- 三 Agent 边界（``max_steps_ab``/``max_steps_omega``、``wall_ab``/``wall_omega``、
  ``max_workers``）使用 executor 硬编码默认值。
- 不污染问股全局 ``ToolRegistry`` 单例（score 工具只进排雷专属 registry）。
- 缺失工具走 warning 分支（config 漂移防护）。
- ``config=None`` 与显式传 ``config`` 两条路径均可构建。

不依赖真实 LLM / 网络（``LLMToolAdapter`` 仅构造不调用）。
"""

from __future__ import annotations

import logging

from src.agent.factory import build_policy_minesweeper_executor


# ============================================================
# 工具集与边界
# ============================================================

class TestFactoryWiring:
    def test_curated_tools_registered(self):
        executor = build_policy_minesweeper_executor()
        names = {t.name for t in executor.tool_registry.list_tools()}
        # 5 个 wengu 筛选工具（严格对齐 α/β 角色 prompt 引用的工具）
        assert {
            "search_stock_news",
            "search_comprehensive_intel",
            "get_stock_info",
            "get_realtime_quote",
            "get_sector_rankings",
        } <= names
        # Ω 综合裁决打分工具
        assert "score_policy_minesweeper" in names

    def test_noise_tools_excluded(self):
        executor = build_policy_minesweeper_executor()
        names = {t.name for t in executor.tool_registry.list_tools()}
        # backtest / 技术博弈类工具被过滤掉（降低政策/公告语境下的 LLM 决策噪音）
        assert "run_backtest" not in names
        assert "get_chip_distribution" not in names
        assert "analyze_trend" not in names

    def test_total_tool_count_is_seven(self):
        executor = build_policy_minesweeper_executor()
        names = executor.tool_registry.list_names()
        # 恰好 7 个（5 wengu + score + search_company_announcements），去重后无重复注册
        assert len(names) == 7
        assert len(set(names)) == 7
        # 两个 PM 专属工具都已注册
        assert {"score_policy_minesweeper", "search_company_announcements"} <= set(names)

    def test_three_agent_bounds(self):
        executor = build_policy_minesweeper_executor()
        assert executor.max_steps_ab == 10
        assert executor.max_steps_omega == 6
        assert executor.wall_ab == 300.0
        assert executor.wall_omega == 240.0
        assert executor.max_workers == 2


# ============================================================
# 隔离性（不污染问股全局单例）
# ============================================================

class TestIsolation:
    def test_global_registry_not_polluted(self):
        from src.agent.factory import get_tool_registry

        build_policy_minesweeper_executor()  # 构建一次独立 registry
        global_names = {t.name for t in get_tool_registry().list_tools()}
        # score_policy_minesweeper 只进排雷专属 registry，不进问股全局缓存
        assert "score_policy_minesweeper" not in global_names


# ============================================================
# config 路径 + 缺失工具 warning（config 漂移防护）
# ============================================================

class TestConfigPaths:
    def test_explicit_config_not_none_branch(self):
        from src.config import get_config

        # 显式传 config（覆盖 `if config is None` 的 False 分支）
        executor = build_policy_minesweeper_executor(config=get_config())
        assert "score_policy_minesweeper" in executor.tool_registry.list_names()

    def test_missing_tools_logs_warning(self, monkeypatch, caplog):
        from src.agent.tools.registry import ToolRegistry

        # 让源 registry 为空 → 5 个 wengu 工具全部缺失，触发 warning 分支
        monkeypatch.setattr(
            "src.agent.factory.get_tool_registry", lambda: ToolRegistry()
        )
        with caplog.at_level(logging.WARNING, logger="src.agent.factory"):
            executor = build_policy_minesweeper_executor()
        # warning 被记录（覆盖 `if missing:` True 分支）
        assert any("缺失工具" in rec.getMessage() for rec in caplog.records)
        # score 工具仍注册（来自 ALL_POLICY_MINESWEEPER_TOOLS，不依赖源 registry）
        assert "score_policy_minesweeper" in executor.tool_registry.list_names()
        # wengu 工具全部缺失（源 registry 被掏空）
        assert "search_stock_news" not in executor.tool_registry.list_names()
