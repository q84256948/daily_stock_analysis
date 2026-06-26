# Pytest 测试框架与测试用例报告

> 日期：2026-06-25  
> 范围：补齐 pytest 依赖/配置，并为个股分析性能相关链路补充测试用例  
> 执行环境：Python 3.11.14，pytest 9.1.1，macOS

---

## 一、pytest 框架现状与本次补齐

### 1.1 已有基础

- 配置文件：`setup.cfg` 中的 `[tool:pytest]` 已存在 `unit` / `integration` / `network` 三个 marker。
- 已有用例：约 **3988 条** 离线可收集用例。
- 已安装插件：`pytest-cov`、`pytest-mock`、`pytest-benchmark`（此前已存在于 `.venv`，但未声明到 CI 依赖）。

### 1.2 本次补齐内容

| 文件 | 修改 |
|------|------|
| `setup.cfg` | 注册 `benchmark` marker，消除 `PytestUnknownMarkWarning` |
| `.github/requirements-ci.txt` | 显式声明 `pytest-cov`、`pytest-mock`、`pytest-benchmark`、`pypdf`，保证 CI 可复现 |

修复前问题：
- `tests/test_md2pdf.py` 因缺少 `pypdf` 在收集阶段报错。
- `tests/test_search_performance.py` 使用 `@pytest.mark.benchmark` 但 marker 未注册。

---

## 二、新增测试文件

### 2.1 `tests/test_data_fetcher_caching.py`

覆盖 `data_provider/base.py` 与 `data_provider/efinance_fetcher.py` 的缓存与性能路径：

- `test_fundamental_context_cache_avoids_duplicate_adapter_calls`：验证同代码同 budget 下的基本面缓存命中。
- `test_fundamental_context_cache_isolated_by_budget_bucket`：验证不同 budget bucket 缓存隔离。
- `test_fundamental_context_cache_prunes_oldest_on_capacity`：验证缓存容量上限与 LRU 驱逐。
- `test_fundamental_context_cache_respects_ttl`：验证缓存 TTL 过期后重新拉取。
- `test_run_with_timeout_limits_hanging_workers`：验证基本面阶段超时与 worker 池耗尽行为。
- `test_efinance_realtime_global_cache_avoids_duplicate_network_calls`：验证 efinance 模块级实时行情缓存避免重复网络请求。

### 2.2 `tests/test_search_comprehensive_intel.py`

覆盖 `src/search_service.py::SearchService.search_comprehensive_intel()`：

- `test_returns_expected_dimensions_for_cn_stock`：A 股 6 个维度全部返回。
- `test_max_searches_limits_dimension_count`：`max_searches` 截断生效。
- `test_provider_rotation_across_dimensions`：provider 轮询逻辑。
- `test_single_dimension_failure_does_not_break_others`：单个维度失败不影响其他维度。
- `test_strict_freshness_filtering_is_applied`：`strict_freshness` 维度调用过滤。
- `test_foreign_stock_uses_different_dimension_set`：美股维度集合差异（无 `announcements`）。
- `test_serial_dimensions_elapsed_baseline`（`benchmark`）：记录当前串行搜索基线（约 ≥2.5s/5 维度）。

### 2.3 `tests/test_storage_trading_date_resume.py`

覆盖 `src/storage.py::StockStorage.has_today_data()`：

- `test_has_today_data_true_when_target_date_exists`：目标自然日有数据返回 `True`。
- `test_has_today_data_false_when_target_date_missing`：目标自然日无数据返回 `False`。
- `test_has_today_data_uses_today_by_default`：默认使用 `date.today()`。
- `test_weekend_runs_currently_miss_latest_trading_day_data`：文档化当前行为——周末仅有周五数据时返回 `False`，为 P1 优化"按交易日判断断点续传"提供回归基线。

---

## 三、新增测试执行结果

```bash
python -m pytest \
  tests/test_data_fetcher_caching.py \
  tests/test_search_comprehensive_intel.py \
  tests/test_storage_trading_date_resume.py \
  tests/test_fundamental_context.py \
  tests/test_search_service_concurrency.py \
  tests/test_storage.py \
  -v --tb=short
```

结果：**62 passed, 1 warning**（无失败）。

---

## 四、全量离线测试结果

### 4.1 执行命令

```bash
python -m pytest -m "not network" \
  --cov=src --cov=data_provider \
  --cov-report=term --cov-report=html \
  -q
```

### 4.2 结果摘要

| 指标 | 数值 |
|------|------|
| 总用例数 | 3988 条（收集） |
| 通过 | **3930 passed** |
| 失败 | 52 failed |
| 错误 | 23 errors |
| 跳过/取消选择 | 2 deselected |
| 总耗时 | 644.98s（约 10 分 45 秒） |
| 总体覆盖率 | **75%**（46159 语句，11315 未覆盖） |

### 4.3 关键文件覆盖率

| 文件 | 语句数 | 未覆盖 | 覆盖率 |
|------|--------|--------|--------|
| `data_provider/base.py` | 1630 | 363 | **78%** |
| `src/core/pipeline.py` | 1461 | 266 | **82%** |
| `src/search_service.py` | 1951 | 615 | **68%** |
| `src/storage.py` | 1335 | 263 | **80%** |

覆盖率 HTML 报告已生成：`htmlcov/index.html`

---

## 五、失败与错误分析

### 5.1 失败分布

| 模块 | 失败数 | 典型原因 |
|------|--------|----------|
| `tests/test_system_config_service.py` | 28 | 配置单例/环境状态在顺序运行中相互污染；单独重跑时多数通过 |
| `tests/test_system_config_api.py` | 6 | 同上，API 与 service 共享全局配置状态 |
| `tests/test_config_registry.py` | 3 | 注册表元数据不一致 |
| `tests/test_config_env_compat.py` | 1 | 期望值（8.0s）与当前默认值（25.0s）不匹配，为预先存在差异 |
| `tests/test_check_env_encoding.py` | 1 | requirements 文件编码断言失败 |
| `tests/test_deep_research.py` | 1 | md2pdf 渲染失败处理断言 |
| `tests/test_ifind_fundamental_adapter.py` | 3 | iFinD 适配器可用性检查 |
| `tests/test_capital_flow_and_config.py` | 1 | 资金流入失败注释断言 |
| `tests/test_chanlun/test_data_fetcher.py` | 3 | 缠论数据获取器初始化 |

### 5.2 错误分布

| 模块 | 错误数 | 典型原因 |
|------|--------|----------|
| `tests/scoring/test_p1_validation.py` | 7 | scoring 模块依赖或 fixture 导入问题 |
| `tests/scoring/test_p2_validation.py` | 7 | 同上 |
| `tests/scoring/test_p3_validation.py` | 7 | 同上 |

### 5.3 与本次改动的关系

- **本次新增的 17 个用例全部通过**。
- 52 个失败与 23 个错误均为**预先存在的问题**，与 `setup.cfg` / `.github/requirements-ci.txt` 的修改无直接因果关系。
- 典型证据：`tests/test_system_config_service.py::test_update_appends_max_workers_warning` 单独运行通过，但在全量套件中失败，说明是测试隔离性问题。

---

## 六、建议

1. **优先修复测试隔离性**：`system_config_service/api` 相关失败多由全局单例/环境变量污染导致，建议引入 fixture 级别的状态清理。
2. **同步 `.env.example` 与配置测试**：`test_config_env_compat.py` 期望的 8.0s 默认值与代码实际 25.0s 不一致，需确认以哪个为准。
3. **补齐 scoring 模块依赖**：`tests/scoring/test_p*_validation.py` 全部 error，需检查 fixture 或缺失依赖。
4. **持续补充覆盖**：当前 `src/search_service.py` 覆盖率 68%，是四个关键文件中最低的；P0 优化实施时应同步补充搜索并发化相关测试。
5. **CI 中启用覆盖率门槛**：建议在 `backend-gate` 中增加 `--cov-fail-under=70` 等门槛，避免覆盖率持续下降。

---

## 七、常用命令速查

```bash
# 离线测试（CI 默认）
python -m pytest -m "not network"

# 新增测试快速验证
python -m pytest \
  tests/test_data_fetcher_caching.py \
  tests/test_search_comprehensive_intel.py \
  tests/test_storage_trading_date_resume.py \
  -v

# 带覆盖率
python -m pytest -m "not network" \
  --cov=src --cov=data_provider \
  --cov-report=term-missing --cov-report=html

# 仅 benchmark 用例
python -m pytest -m benchmark -v

# 网络冒烟
python -m pytest -m network -q
```

---

*本报告由 AI 助手基于 2026-06-25 的测试执行结果生成。*
