# 个股分析链路性能优化方案

> 日期：2026-06-25  
> 范围：A股/港股/美股个股分析主链路（`main.py` → `src/core/pipeline.py` → `src/search_service.py` / `data_provider/base.py` / `src/analyzer.py` 等）  
> 目标：定位性能瓶颈，给出可落地的分阶段优化方案与验证方式

---

## 一、当前主要性能瓶颈

### 1. 搜索维度串行 + 硬编码 sleep（影响最大，P0）

**位置：** `src/search_service.py::SearchService.search_comprehensive_intel()`

**问题：**
- 6 个搜索维度（`latest_news` / `market_analysis` / `risk_check` / `announcements` / `earnings` / `industry`）按 `for dim in search_dimensions` 串行执行。
- 每次维度调用后 `time.sleep(0.5)`，5 次搜索累计至少 **2.5s/股**。
- provider 轮询逻辑在维度间切换，各 provider 的搜索请求本身是独立网络 I/O，具备天然并发性。

**估算：** 单股搜索阶段占单股总耗时的 20%~40%，多股批量时搜索成为主要长尾瓶颈。

---

### 2. 单股内部多阶段串行预取（P0）

**位置：** `src/core/pipeline.py::StockAnalysisPipeline.analyze_stock()`

**问题：**
- `get_realtime_quote`、`get_daily_data`（首次需网络拉取）、`get_chip_distribution`、`get_stock_name`、`get_fundamental_context` 在单股内顺序执行。
- 实时行情、筹码、名称、基本面之间无数据依赖，可并发获取。
- 当前先等实时行情返回，再等筹码，再等基本面，时间叠加。

---

### 3. 实时行情缓存隔离与重复请求（P0）

**位置：**
- `data_provider/base.py::DataFetcherManager._prefetch_realtime_quotes()`
- `data_provider/efinance_fetcher.py` 全局缓存
- `data_provider/akshare_fetcher.py` 全局缓存

**问题：**
- `run()` 在股票数 `>=5` 时会批量预取全市场实时行情，但预取结果写入 efinance 全局缓存。
- 当配置优先级非 efinance 首位时，个股 `get_realtime_quote()` 会绕开缓存重新请求。
- efinance / akshare / tencent 各自维护独立缓存，TTL 不一致（600s / 1200s），无统一失效策略。
- 个股流程中可能重复调用 `get_realtime_quote`（如基本面阶段再次调用）。

---

### 4. 基本面阶段超时与 retry 叠加过长（P0）

**位置：** `data_provider/base.py::DataFetcherManager.get_fundamental_context()`

**问题：**
- 默认 `fundamental_stage_timeout_seconds=25s`，`fundamental_fetch_timeout_seconds=10s`。
- 内部 `_run_with_retry` + 各 fetcher 自身 `@retry(stop_after_attempt=3)` 叠加。
- 单源失败路径可能耗时：10s × 3 次（fetcher 内部 retry）+ 25s 阶段超时，极端情况下单股基本面阶段可达 **分钟级**。
- 当前虽有 `BoundedSemaphore(8)` 限制并发，但超时过长导致 worker 被长时间占用。

---

### 5. 断点续传按自然日判断，节假日重复分析（P1）

**位置：** `src/storage.py::StockStorage.has_today_data()`

**问题：**
- `target_date` 默认 `date.today()`，即自然日。
- 周末/节假日运行时，即使数据库已有最新交易日数据，也会返回 `False`，导致重复拉取网络数据。

---

### 6. 并发 worker 数保守（P1）

**位置：** `src/core/pipeline.py::StockAnalysisPipeline.run()`

**问题：**
- 默认 `max_workers=3`（由 `MAX_WORKERS` 控制）。
- 在搜索、LLM、数据源主要为 I/O 等待场景下，3 个 worker 无法充分利用带宽和 API 并发能力。
- `analysis_delay` 只作用于主线程收集结果的循环，对并发峰值控制效果有限。

---

### 7. LLM 调用与 JSON 重试成本（P2）

**位置：** `src/analyzer.py::GeminiAnalyzer.analyze()`

**问题：**
- `report_integrity_retry` 默认 1，JSON 解析失败时重新走完整 LLM 调用。
- 未对相同/相似 context 做结果缓存（相同股票短时间内重复分析会重复调用 LLM）。
- Router 使用 `simple-shuffle`，无延迟/成功率感知。

---

### 8. 缺乏端到端性能度量

**问题：**
- 没有 profiling 脚本输出各阶段耗时分解。
- 现有日志虽有部分 `elapsed=`，但缺少结构化、可聚合的耗时指标。
- 无法量化优化前后的实际收益。

---

## 二、完整优化方案

### P0：搜索维度并发化

**目标：** 把单股搜索阶段从串行 2.5s+ 降到并行 ≈0.6~1.0s。

**方案：**
1. 在 `search_comprehensive_intel()` 中，将维度列表拆分为无依赖的搜索任务。
2. 使用 `ThreadPoolExecutor`（维度数 <=6，线程开销可控）并发执行各维度搜索。
3. 移除/降低硬编码 `time.sleep(0.5)`，改为基于 provider 的 rate-limit 控制（如每个 provider 维级最小间隔）。
4. 保留 `max_searches` 上限语义：并发池大小由 `min(max_searches, len(dimensions))` 决定。
5. 异常处理：单个维度失败不影响其他维度，最终结果字典中该维度标记为失败。

**改动文件：** `src/search_service.py`

**关键代码示意：**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _search_one_dim(dim):
    provider = ...
    response = provider.search(...)
    # filter / rank / limit
    return dim['name'], filtered_response

with ThreadPoolExecutor(max_workers=min(max_searches, len(search_dimensions))) as executor:
    future_to_dim = {executor.submit(_search_one_dim, d): d for d in search_dimensions[:max_searches]}
    for future in as_completed(future_to_dim):
        name, response = future.result()
        results[name] = response
```

---

### P0：单股数据获取并发预取

**目标：** 把实时行情、筹码、名称、基本面等独立 I/O 阶段从串行改为并行，预计节省 1~3s/股。

**方案：**
1. 在 `analyze_stock()` 的 Step 1~2.5 阶段，将以下调用打包为并发任务：
   - `get_stock_name(code, allow_realtime=False)`
   - `get_realtime_quote(code)`
   - `get_chip_distribution(code)`
   - `get_fundamental_context(code)`
2. 使用 `ThreadPoolExecutor(max_workers=4)`，主线程等待全部完成。
3. 注意：后续 `_enhance_context` 和趋势分析依赖这些结果，所以这里是"并行获取 + 同步等待"。
4. 保留异常降级语义：每个任务失败独立捕获。

**改动文件：** `src/core/pipeline.py`

---

### P0：统一实时行情缓存

**目标：** 消除预取与个股流程、基本面阶段之间的重复实时行情请求。

**方案：**
1. 在 `DataFetcherManager` 实例层维护 `_realtime_quote_cache: Dict[str, Tuple[quote, timestamp]]`。
2. `get_realtime_quote()` 先查实例缓存，命中且未过期则直接返回。
3. `_prefetch_realtime_quotes()` 将批量结果写入同一缓存。
4. 缓存 TTL 统一从配置读取（默认 60~120s），避免 efinance/akshare 各自为政。
5. 缓存 key 使用规范化后的股票代码。

**改动文件：** `data_provider/base.py`

---

### P0：基本面阶段超时与降级优化

**目标：** 避免单股因基本面阶段卡住导致整个 worker 被长时间占用。

**方案：**
1. 将默认 `fundamental_fetch_timeout_seconds` 从 10s 降至 **5s**。
2. 将默认 `fundamental_stage_timeout_seconds` 从 25s 降至 **12~15s**。
3. 在 `get_fundamental_context()` 中，对每个 block 使用 `timeout_budget`，任一 block 超时立即返回 partial 结果，不阻塞后续 block。
4. 取消/减少 fetcher 内部 retry 次数：建议 fetcher 层 retry 从 3 次降至 1~2 次，manager 层负责 fallback。
5. 配置项暴露到 `.env.example`：
   - `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS`
   - `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS`
   - `FUNDAMENTAL_CACHE_TTL_SECONDS`

**改动文件：** `src/config.py`、`data_provider/base.py`、`.env.example`

---

### P1：断点续传按交易日判断

**目标：** 避免节假日/周末重复分析。

**方案：**
1. 在 `StockStorage.has_today_data()` 中，当 `target_date` 不是交易日时，改为查询该股票数据库中最新一条数据的日期。
2. 如果最新数据日期 >= 最近一个交易日，则返回 `True`。
3. 复用已有的 `src/core/trading_calendar.py` 中的 `get_effective_trading_date()` / `is_market_open()`。
4. 保留 `target_date` 参数供明确指定日期场景使用。

**改动文件：** `src/storage.py`

---

### P1：历史日线与筹码缓存

**目标：** 减少同一批股票分析失败重试时的重复拉取。

**方案：**
1. 在 `DataFetcherManager` 层对 `get_daily_data()` 增加进程内缓存，TTL 300s，容量 500。
2. 对 `get_chip_distribution()` 增加类似缓存，TTL 120s。
3. 缓存 key 包含规范化股票代码和请求参数（days / start_date / end_date）。
4. 使用 LRU 策略避免内存无限增长。

**改动文件：** `data_provider/base.py`

---

### P1：提高并发 worker 数并支持动态调整

**目标：** 提升多股批量分析的并发度。

**方案：**
1. 默认 `MAX_WORKERS` 从 3 提高到 **5**。
2. 根据股票数量动态调整：股票数 <=3 时 `max_workers=3`；>3 时 `max_workers=min(8, len(stock_codes))`。
3. 配置 `MAX_WORKERS` 仍然生效，作为上限。
4. 同步调整 `analysis_delay` 语义或提供 `REQUEST_INTER_STOCK_DELAY` 配置，使其真正作用于任务提交间隔（可选）。

**改动文件：** `src/core/pipeline.py`、`src/config.py`、`.env.example`

---

### P1：增加端到端 Profiling 脚本

**目标：** 量化优化效果，定位实际瓶颈。

**方案：**
1. 新增 `scripts/profile_pipeline.py`。
2. 对 5~10 只典型股票跑一遍 `pipeline.run()`，输出：
   - 总耗时
   - 每只股票各阶段耗时：数据获取、搜索、LLM、保存
   - 数据源命中/失败/熔断次数
   - 缓存命中率
3. 使用 `time.monotonic()` 在关键阶段打桩，写入 JSON/CSV。

**改动文件：** 新增 `scripts/profile_pipeline.py`

---

### P2：LLM 结果缓存与 Prompt 复用

**目标：** 降低相同/相似请求重复调用 LLM 的成本。

**方案：**
1. 对相同股票代码 + 相同交易日 + 相同 report_type 的 context 做结果缓存（TTL 1 小时）。
2. 缓存 key 使用 context 摘要 hash（排除 query_id 等动态字段）。
3. 将系统 prompt 与动态 context 分离，减少重复字符串构造。

**改动文件：** `src/analyzer.py`、`src/storage.py` 或新增缓存模块

---

### P2：LLM Router 策略优化

**目标：** 提升多 key 场景下的成功率与延迟。

**方案：**
1. 将 Router `routing_strategy` 从 `simple-shuffle` 改为 `latency-based-routing` 或 `least-busy`。
2. 配置 `num_retries` 保持 2，但增加 `retry_after` 和 `timeout` 控制。

**改动文件：** `src/analyzer.py`

---

### P2：缠论分析性能

**目标：** 降低纯 Python 循环处理 K 线的 CPU 开销。

**方案：**
1. 评估 `chanlun/chanlun_engine.py` 中分型、笔、线段、中枢计算的复杂度。
2. 对批量分析场景，考虑使用 numba 加速核心循环，或减少非必要计算列。
3. 当前未使用缠论主链路时，可延迟加载。

**改动文件：** `chanlun/chanlun_engine.py`

---

## 三、实施顺序建议

| 阶段 | 任务 | 预期收益 |
|------|------|----------|
| 第 1 周 | P0：搜索并发化、单股数据并发预取、统一实时行情缓存 | 单股耗时下降 30%~50% |
| 第 2 周 | P0：基本面超时/降级优化、P1：断点续传按交易日判断 | 长尾超时消失，节假日不再重复分析 |
| 第 3 周 | P1：历史日线/筹码缓存、worker 数提升、新增 profiling 脚本 | 批量场景整体吞吐提升，效果可量化 |
| 第 4 周 | P2：LLM 缓存、Router 优化、缠论评估 | 进一步降低 LLM 成本与延迟 |

---

## 四、验证方案

1. **基准测试：** 在优化前运行 `scripts/profile_pipeline.py`（或临时脚本），记录 10 只股票的各阶段耗时。
2. **CI 检查：** 每次修改后执行 `./scripts/ci_gate.sh` 和 `python -m py_compile <changed_files>`。
3. **离线测试：** 使用 `pytest -m "not network"` 确保不破坏现有逻辑。
4. **冒烟测试：** 对 3~5 只 A 股/港股/美股各跑一次完整分析，确认结果正确、通知正常。
5. **对比验证：** 优化后再次运行 profiling，对比各阶段耗时和缓存命中率。

---

## 五、风险点与回滚

| 风险 | 说明 | 回滚/缓解 |
|------|------|-----------|
| 并发提高触发反爬 | 搜索/数据并发增加可能被限流 | 保留 `MAX_WORKERS` 配置；provider 层保留 rate-limit 控制 |
| 缓存导致数据陈旧 | 实时行情缓存 TTL 过长可能返回旧数据 | TTL 默认 60~120s，可配置；禁用缓存可设 TTL=0 |
| 基本面超时缩短导致数据缺失 | 慢接口可能无法完成 | 失败时返回 partial，不阻断主流程；用户可手动调高超时 |
| 断点续传按交易日判断引入节假日逻辑错误 | 跨市场交易日不同 | 按股票所属市场分别计算交易日 |

---

## 六、关键文件清单

| 关注点 | 文件 | 函数/类 |
|--------|------|---------|
| 并发调度 | `src/core/pipeline.py` | `StockAnalysisPipeline.run()` |
| 单股流程 | `src/core/pipeline.py` | `StockAnalysisPipeline.analyze_stock()` |
| 数据管理层 | `data_provider/base.py` | `DataFetcherManager` |
| 实时行情预取 | `data_provider/base.py` | `_prefetch_realtime_quotes()` |
| 基本面获取 | `data_provider/base.py` | `get_fundamental_context()` |
| 搜索服务 | `src/search_service.py` | `SearchService.search_comprehensive_intel()` |
| 断点续传 | `src/storage.py` | `StockStorage.has_today_data()` |
| LLM 调用 | `src/analyzer.py` | `GeminiAnalyzer.analyze()` |
| 配置入口 | `src/config.py` | `Config` 类相关字段 |

---

*本方案由 AI 助手基于 2026-06-25 的代码现状整理，后续实施时应以仓库实际可执行内容为准。*
