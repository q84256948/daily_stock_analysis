#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单模块覆盖率 runner —— 绕开 pytest+conftest 与 numpy C 扩展的 trace 冲突。

背景：直接 ``pytest --cov`` 在本环境会触发 ``numpy: cannot load module more than
once per process``（coverage 的 import 跟踪 + numpy 2.x C 扩展 + tests/conftest.py
的 asyncio patch 三者交互）。本脚本改用 unittest + coverage API，并在启动 coverage
**之前**预热 numpy/pandas/重量级包，使 C 扩展在 coverage trace 之前已加载完毕。

用法::

    python scripts/run_module_coverage.py <source_module> <test_module>

例::

    python scripts/run_module_coverage.py data_provider.cross_source_validator \\
        tests.test_cross_source_validator

退出码：0=测试全过，1=有失败，2=参数错误。
"""

from __future__ import annotations

import importlib
import sys
import unittest

import coverage


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_module_coverage.py <source_module> <test_module>", file=sys.stderr)
        return 2

    source_pkg, test_mod = sys.argv[1], sys.argv[2]
    sys.path.insert(0, ".")

    # 预热 C 扩展：在 coverage 启动前让 numpy/pandas 先加载，避免 trace 下重复加载。
    # 不预热 data_provider.base —— 否则会顺带 import 待测模块（经 __init__），
    # 导致其顶层定义在 coverage 之前执行而漏统计。
    for warm in ("numpy", "pandas"):
        try:
            importlib.import_module(warm)
        except Exception:  # noqa: BLE001 — 预热失败不阻塞
            pass

    cov = coverage.Coverage(source=[source_pkg])
    cov.start()
    try:
        module = importlib.import_module(test_mod)
        suite = unittest.TestLoader().loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        cov.stop()

    print(f"\n--- COVERAGE: {source_pkg} ---")
    cov.report(show_missing=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
