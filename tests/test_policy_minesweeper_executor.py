# -*- coding: utf-8 -*-
"""政策与公告双维度排雷 — Executor 编排与降级单元测试。

通过 DI 注入 fake ``loop_runner``，覆盖 α/β 并行 → Ω 综合的全部路径与降级分支，
不依赖真实 LLM / 网络 / run_agent_loop 内部。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.agent.policy_minesweeper_executor import (
    PolicyMinesweeperExecutor,
    PolicyMinesweeperResult,
    _build_degraded_report,
    _build_omega_messages,
    _default_loop,
    _load_system_prompt,
    _ok,
)


# ---------------------------------------------------------------- fakes

@dataclass
class LoopOut:
    """模拟 RunLoopResult 的鸭子类型对象（避免重依赖 runner）。"""
    success: bool = True
    content: str = "report"
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 1
    total_tokens: int = 10
    provider: str = "test-provider"
    error: str = ""


class FakeLoop:
    """按 role 返回预设结果的 loop_runner；记录调用 kwargs，可选抛错。"""

    def __init__(self, results: Dict[str, LoopOut], raise_for=()) -> None:
        self.results = results
        self.raise_for = set(raise_for)
        self.calls: Dict[str, List[Dict[str, Any]]] = {}

    def __call__(self, role: str, **kwargs: Any) -> LoopOut:
        self.calls.setdefault(role, []).append(kwargs)
        cb = kwargs.get("progress_callback")
        if cb:
            cb({"type": "tool_start", "tool": "search_stock_news"})
        if role in self.raise_for:
            raise RuntimeError(f"{role} boom")
        return self.results[role]


def _ok_out(content: str = "α 公告分析内容", **kw) -> LoopOut:
    return LoopOut(success=True, content=content, **kw)


def _fail_out(error: str = "failed") -> LoopOut:
    return LoopOut(success=False, content="", error=error)


def _executor(loop: FakeLoop) -> PolicyMinesweeperExecutor:
    return PolicyMinesweeperExecutor(
        tool_registry=MagicMock(name="registry"),
        llm_adapter=MagicMock(name="llm"),
        loop_runner=loop,
        system_prompt="TEST PROMPT",
    )


def _run(loop: FakeLoop, horizon: str = "medium", cb=None):
    return _executor(loop).generate("300750", "示例公司", horizon=horizon, progress_callback=cb)


# ============================================================
# 正常路径
# ============================================================

class TestHappyPath:
    def test_all_three_success_status_success(self):
        loop = FakeLoop({"alpha": _ok_out("α 内容"), "beta": _ok_out("β 内容"), "omega": _ok_out("Ω 综合结论")})
        result = _run(loop)
        assert result.success and result.status == "success"
        assert result.alpha_ok and result.beta_ok and result.omega_ok
        assert result.markdown == "Ω 综合结论"

    def test_alpha_and_beta_each_called_once(self):
        loop = FakeLoop({"alpha": _ok_out(), "beta": _ok_out(), "omega": _ok_out()})
        _run(loop)
        assert len(loop.calls["alpha"]) == 1
        assert len(loop.calls["beta"]) == 1
        assert len(loop.calls["omega"]) == 1


# ============================================================
# 降级分支
# ============================================================

class TestDegradation:
    def test_alpha_degraded_omega_ok_partial(self):
        loop = FakeLoop({"alpha": _fail_out(), "beta": _ok_out(), "omega": _ok_out("Ω 结论")})
        result = _run(loop)
        assert result.status == "partial"
        assert not result.alpha_ok and result.beta_ok and result.omega_ok
        assert result.markdown == "Ω 结论"

    def test_beta_degraded_omega_ok_partial(self):
        loop = FakeLoop({"alpha": _ok_out(), "beta": _fail_out(), "omega": _ok_out("Ω 结论")})
        result = _run(loop)
        assert result.status == "partial" and not result.beta_ok

    def test_both_legs_degraded_omega_ok_partial(self):
        loop = FakeLoop({"alpha": _fail_out(), "beta": _fail_out(), "omega": _ok_out("Ω 仅基于已知")})
        result = _run(loop)
        assert result.status == "partial"
        assert not result.alpha_ok and not result.beta_ok and result.omega_ok

    def test_omega_failed_legs_ok_degrades_to_raw_report(self):
        loop = FakeLoop({"alpha": _ok_out("α 内容"), "beta": _ok_out("β 内容"), "omega": _fail_out("ω 超时")})
        result = _run(loop)
        assert result.status == "partial" and not result.omega_ok
        assert "α 内容" in result.markdown and "β 内容" in result.markdown
        assert "综合裁决" in result.markdown and "不构成投资建议" in result.markdown
        assert result.error == "ω 超时"

    def test_omega_empty_content_treated_as_failed(self):
        loop = FakeLoop({"alpha": _ok_out(), "beta": _ok_out(),
                         "omega": LoopOut(success=True, content="   ")})
        result = _run(loop)
        assert not result.omega_ok and result.status == "partial"

    def test_all_failed_status_failed(self):
        loop = FakeLoop({"alpha": _fail_out("a-err"), "beta": _fail_out("b-err"), "omega": _fail_out("o-err")})
        result = _run(loop)
        assert result.status == "failed" and not result.success
        assert result.markdown == ""
        assert result.error  # 有错误信息

    def test_loop_exception_caught_as_failed_leg(self):
        # alpha 抛错 → _loop_safe 捕获 → 当作 alpha 失败 → partial
        loop = FakeLoop(
            {"alpha": _ok_out(), "beta": _ok_out(), "omega": _ok_out("Ω 结论")},
            raise_for={"alpha"},
        )
        result = _run(loop)
        assert result.status == "partial" and not result.alpha_ok
        assert result.omega_ok


# ============================================================
# 汇总：步数/token/工具日志/provider
# ============================================================

class TestAggregation:
    def test_totals_summed_across_loops(self):
        loop = FakeLoop({
            "alpha": _ok_out(total_steps=3, total_tokens=100, provider="p-a"),
            "beta": _ok_out(total_steps=4, total_tokens=200, provider="p-b"),
            "omega": _ok_out(total_steps=2, total_tokens=50, provider="p-o"),
        })
        result = _run(loop)
        assert result.total_steps == 9
        assert result.total_tokens == 350
        assert result.provider == "p-o"  # Ω 优先

    def test_tool_calls_concatenated(self):
        loop = FakeLoop({
            "alpha": _ok_out(tool_calls_log=[{"tool": "a1"}]),
            "beta": _ok_out(tool_calls_log=[{"tool": "b1"}, {"tool": "b2"}]),
            "omega": _ok_out(tool_calls_log=[{"tool": "score_policy_minesweeper"}]),
        })
        result = _run(loop)
        assert [e["tool"] for e in result.tool_calls_log] == ["a1", "b1", "b2", "score_policy_minesweeper"]


# ============================================================
# 进度回调 + horizon 透传
# ============================================================

class TestProgressAndHorizon:
    def test_progress_callback_receives_role_tagged_events(self):
        loop = FakeLoop({"alpha": _ok_out(), "beta": _ok_out(), "omega": _ok_out()})
        events: List[Dict[str, Any]] = []
        _run(loop, cb=events.append)
        agents = {e.get("agent") for e in events if e.get("agent")}
        assert {"alpha", "beta", "omega"} <= agents
        # 至少 3 个阶段 thinking 标记
        thinkings = [e for e in events if e.get("type") == "thinking"]
        assert len(thinkings) >= 3

    def test_horizon_passed_into_messages(self):
        loop = FakeLoop({"alpha": _ok_out(), "beta": _ok_out(), "omega": _ok_out()})
        _run(loop, horizon="long")
        for role in ("alpha", "beta", "omega"):
            user_content = loop.calls[role][0]["messages"][-1]["content"]
            assert "long" in user_content


# ============================================================
# 默认 loop / max_workers
# ============================================================

class TestDefaults:
    def test_default_loop_used_when_not_injected(self):
        executor = PolicyMinesweeperExecutor(MagicMock(), MagicMock())
        assert executor._loop is _default_loop

    def test_max_workers_default_two(self):
        executor = PolicyMinesweeperExecutor(MagicMock(), MagicMock())
        assert executor.max_workers == 2


# ============================================================
# 纯函数辅助
# ============================================================

class TestHelpers:
    def test_ok_truthiness(self):
        assert _ok(LoopOut(success=True, content="x")) is True
        assert _ok(LoopOut(success=True, content="  ")) is False
        assert _ok(LoopOut(success=False, content="x")) is False
        assert _ok(LoopOut()) is True  # 默认 content="report"

    def test_omega_messages_include_both_legs(self):
        msgs = _build_omega_messages("BASE", "600519", "茅台", "short",
                                     _ok_out("α-文"), _ok_out("β-文"))
        assert msgs[0]["role"] == "system"
        assert "α-文" in msgs[1]["content"] and "β-文" in msgs[1]["content"]
        assert "score_policy_minesweeper" in msgs[1]["content"]

    def test_omega_messages_note_missing_leg(self):
        msgs = _build_omega_messages("BASE", "600519", "茅台", "medium", _fail_out(), _ok_out("β-文"))
        assert "不可用" in msgs[1]["content"]

    def test_degraded_report_with_no_legs(self):
        md = _build_degraded_report("600519", "茅台", _fail_out(), _fail_out())
        assert "不可用" in md and "不构成投资建议" in md


# ============================================================
# 结果数据类
# ============================================================

class TestResultDataclass:
    def test_defaults(self):
        r = PolicyMinesweeperResult()
        assert r.success is False and r.status == "failed"
        assert r.alpha_ok is False and r.beta_ok is False and r.omega_ok is False
        assert r.tool_calls_log == [] and r.horizon == "medium"


# ============================================================
# 加载器（system_prompt 文件 / 兜底；_default_loop 委托）
# ============================================================

class TestLoaders:
    def test_load_system_prompt_reads_file(self):
        text = _load_system_prompt()
        # 真实 data/policy_minesweeper/system_prompt.md 存在 → 读取成功
        assert "政策与公告双维度排雷" in text

    def test_load_system_prompt_fallback_on_missing(self, monkeypatch):
        from src.agent.policy_minesweeper_executor import _FALLBACK_SYSTEM_PROMPT

        monkeypatch.setattr(
            "src.agent.policy_minesweeper_executor._SYSTEM_PROMPT_PATH",
            "/definitely/missing/prompt.md",
        )
        assert _load_system_prompt() == _FALLBACK_SYSTEM_PROMPT

    def test_default_loop_delegates_to_run_agent_loop(self, monkeypatch):
        captured: Dict[str, Any] = {}

        def fake_run(**kwargs: Any) -> LoopOut:
            captured.update(kwargs)
            return LoopOut(content="ran")

        monkeypatch.setattr("src.agent.runner.run_agent_loop", fake_run)
        out = _default_loop(
            "alpha",
            messages=[{"role": "user", "content": "x"}],
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
            max_steps=5,
            max_wall_clock_seconds=10.0,
            progress_callback=None,
            stock_scope=None,
        )
        assert out.content == "ran"
        assert captured["max_steps"] == 5
