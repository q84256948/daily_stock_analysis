# 数据源与交叉验证

> 本文档说明 A 股深度投研报告（`/deep-research`）的数据源架构、主源分流策略、关键锚点交叉验证机制，以及置信度语义。
>
> 相关：[`deep-research.md`](./deep-research.md)（深度投研报告专题）、[`deep_research_executor.py`](../src/agent/deep_research_executor.py)（ReAct 编排）、[`system_prompt.md`](../data/deep_research/system_prompt.md)（五层穿透 prompt）。

## 1. 背景：fail-open fallback vs cross-validation

项目原有 `DataFetcherManager`（`data_provider/base.py`）实现的是 **fail-open fallback**（失败降级）：同一数据点按优先级链取，第一个成功返回的源即采用，**永远只来自一个源**。这对「数据存在」是够用的，但无法保证「数据真实」——单点依赖（如 A 股基本面靠 AkShare/东财爬虫）在网络封锁、源数据错误时无任何校验。

深度投研报告面向机构级分析，要求**有效性、真实性、实时性**。因此新增一层 **cross-validation**（交叉验证）：对报告关键锚点（PE/PB/市值/营收/净利/ROE/主力净流入/融资余额等），用**两个独立来源**独立取数、容差比对、标注置信度，让每个关键数字可追溯、可纠错、冲突不掩盖。

> **关键区别**：cross-validation 与 fail-open 是两层独立机制。fail-open 链保证「能取到数」，cross-validation 层保证「取到的数可被另一源佐证」。验证层是只读、fail-open、opt-in 的——任一源失败不阻塞主流程。

## 2. 三源职责

| 源 | 角色 | 类型 | 取数方式 | 失败行为 |
|---|---|---|---|---|
| **MX Data**（东财妙想） | **主源**（估值/财务/资金类锚点） | 结构化 HTTP API | 自然语言查询 `POST /claw/query`，header `apikey` | fail-open，30min 缓存控配额 |
| **同花顺 iFinD** | **验证源** | MCP streamablehttp | async client，单例连接池复用 | fail-open + breaker 熔断 |
| **AkShare / 东财 / sina / tencent** | **兜底** | 爬虫（既有链） | `DataFetcherManager` fallback 链 | 既有 fail-open 链不变 |

- **实时性**：盘中行情（当前价/涨跌幅）主源是 `get_realtime_quote`（已有 em→sina→tencent 实时 fallback），**不是** MX snapshot。MX snapshot 仅作验证。
- **token 安全**：`MX_APIKEY` / `IFIND_MCP_TOKEN` 只从环境变量读取，不入库、不写日志、`.env.example` 仅占位符。

## 3. 主源分流

```
行情类锚点（当前价/涨跌幅）──── get_realtime_quote(主,盘中实时) ◄── MX/iFinD 验证
估值类锚点（PE/PB/总市值/流通市值）── MX(主) ◄── iFinD 验证 ◄── AkShare 兜底
财务类锚点（营收/归母净利/ROE）───── MX(主,带报告期) ◄── iFinD 验证 ◄── AkShare 兜底
资金/筹码类（主力净流入/融资余额）── MX(主) ◄── iFinD 双向验证 ◄── AkShare 兜底
```

## 4. 关键锚点分级 · 容差 · 口径 · 报告期

定义见 `data_provider/cross_source_validator.py` 的 `ANCHOR_SPECS`。

| 分级 | 锚点 | 主源 | 验证源 | 容差/策略 | 口径·报告期要求 |
|---|---|---|---|---|---|
| 核心·双源 | `current_price` 当前价 | realtime_quote | MX/iFinD | ±1%（数值） | 同一时点 |
| 核心·双源 | `pe_ratio` / `pb_ratio` | MX | iFinD | ±10%（数值） | 记录口径（TTM），口径不同→medium |
| 核心·双源 | `total_mv` / `circ_mv` 市值 | MX | iFinD | ±5%（数值） | 总/流通口径一致 |
| 核心·双源 | `revenue` / `net_profit` | MX | iFinD | ±3%（数值） | **强制同报告期** |
| 核心·双源 | `roe` | MX | iFinD | ±3%（数值） | 强制同报告期 |
| 核心·双源 | `main_inflow` 主力净流入 | MX | iFinD | **方向+量级**（非数值） | 算法口径不同，见 §5 |
| 核心·双源 | `margin_balance` 融资余额 | MX | iFinD | ±0.5%（严格数值） | 交易所每日确定数据 |

> **报告期对齐（防误判）**：财务锚点 query 强制带报告期（如「2024年报」），MX/iFinD 同期比对；若两源返回报告期不一致（如 MX 取快报、iFinD 取正式报），直接判 `medium` 并标注「报告期不一致」，**不做数值容差比对**。
>
> **口径对齐（防误判）**：PE/PB 的 TTM / 静态 / 动态口径不同会导致数值本就不同。口径不一致时判 `medium` + 标注，**不做数值比对**。

## 5. 资金流锚点的特殊性（方向 + 量级，非严格数值）

主力净流入的东财口径（MX/AkShare）与同花顺口径（iFinD）**算法不同**（单笔阈值、大单分类不同），数值本就不同——盲目数值比对会误报。验证策略：

| 两源关系 | 判定 | 标注 |
|---|---|---|
| 方向一致（都净流入/流出）+ 量级同档（如都是「千万级」） | `high` | ✓ 双源验证，方向一致 |
| 方向一致但量级差异大 | `medium` | 两源算法口径差异，方向一致但量级分歧 |
| 方向相反 | `low` | ⚠ 冲突，需核对 |

- **融资余额**：沪深交易所每日公布的**确定数据**，MX/iFinD 应严格一致（±0.5%），不一致即冲突。
- **筹码集中度**：算法强依赖源（东财 `stock_cyq_em` vs 同花顺），差异大，仅作参考标注，不参与严格验证。

## 6. 置信度语义

`AnchorVerification.confidence` 三档：

| 置信度 | 含义 | 报告标注 |
|---|---|---|
| `high` | 双源取数成功，数值在容差内（或方向+量级一致） | `✓（MX+iFinD 双源，差异X%，口径=TTM，2024年报）` |
| `medium` | 口径/报告期不同、或单源可用、或方向一致量级分歧 | `（单源/口径不同/报告期不一致，未严格验证）` |
| `low` | 双源数值超容差 / 方向相反 | `⚠ 数据冲突：MX=X / iFinD=Y，差异X%，建议核对` |

LLM 按 [`system_prompt.md`](../data/deep_research/system_prompt.md) 原则 7「双源验证标注」据此在报告中标注关键数字，**冲突必须披露，不得掩盖**。

## 7. 工具注入点

`src/agent/tools/data_tools.py` 在开关开启时向三个工具的返回注入 `cross_validation` 块：

| 工具 | 注入锚点 | 主源 |
|---|---|---|
| `get_realtime_quote` | `current_price` | 盘中实时行情（realtime），MX/iFinD 验证 |
| `get_stock_info` | `pe_ratio`/`pb_ratio`/`total_mv`/`circ_mv`/`revenue`/`net_profit`/`roe` | MX（主），iFinD 验证 |
| `get_capital_flow` | `main_inflow`/`margin_balance` | MX（主），iFinD 双向验证 |

`cross_validation` 块结构（compact，省 token）：

```json
{
  "enabled": true,
  "anchors": {
    "pe_ratio": {"v": 30.5, "conf": "high", "src": ["mx","ifind"], "diff": 0.3, "caliber": "TTM", "period": "2024年报"}
  },
  "summary": "7/9 双源通过; 主力净流入单源"
}
```

## 8. 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `DEEP_RESEARCH_CROSS_VALIDATE` | `false` | 验证总开关，**opt-in**，关闭=零回归 |
| `MX_APIKEY` | （空） | 东财妙想 API key，未配置则 MX 源 fail-open 跳过 |
| `IFIND_MCP_ENDPOINT` | （空） | 同花顺 iFinD MCP endpoint |
| `IFIND_MCP_TOKEN` | （空） | iFinD MCP Authorization token |
| `IFIND_MCP_TIMEOUT_SECONDS` | `8.0` | 单次 iFinD 调用超时（独立 budget，不挤占 fundamental pipeline） |
| `MX_CALL_BUDGET` | `50` | 单次报告 MX 调用上限（控配额） |

**回滚**：`DEEP_RESEARCH_CROSS_VALIDATE=false` 时，三个工具返回与改动前完全一致，零行为变化。

## 9. Phase 0 可行性验证（已实测，2026-06-25）

启用真实 key 跑探测脚本验证数据源硬前提：

```bash
python scripts/probe_data_sources.py          # 连通性 + MX 字段结构 + iFinD 工具列表
python scripts/probe_e2e_cross_validate.py    # 真实双源交叉验证（600519 全锚点置信度）
python scripts/probe_e2e_data_tools.py        # data_tools 工具注入 cross_validation 块
```

**实测结论**：

| 项 | 结果 |
|---|---|
| MX Data 连通 + 字段 | ✅ snapshot/financials/capital 三类 query 全部返回，字段含中文金额单位（万亿/亿） |
| iFinD MCP 连通 + 工具 | ✅ stock MCP 10 个工具：`get_stock_info`/`get_stock_financials`/`get_stock_performance`/`stock_highfreq_quotes` 等 |
| iFinD 工具参数格式 | ⚠️ **全部为自然语言 `query` 字符串**，非结构化字段；返回 Markdown 表格（`data.answer`） |
| 600519 双源验证（9 锚点） | ✅ **7 high / 2 medium / 0 low**：PE 18.33(diff0.43%)、总市值1.516万亿(diff0.42%)、营收1709亿(diff0%)、归母净利862亿(diff0%)、融资余额199.4亿(diff0.19%) 全部双源一致 |
| 主力净流入方向验证 | ⚠️ MX -8.699亿 vs iFinD -37631（股单位，量级口径不同），方向一致（均净流出）→ 验证为方向参考 |
| MX 港股歧义 | ⚠️ `300750`（宁德时代）MX financials 误关联港股 03750.HK（返回「亿**港元**」），A 股代码需带 `.SZ` 后缀消歧 |

**已知限制**（fail-open 处理，不阻塞）：
- iFinD 主力净流入返回「股」单位量级异常，方向可参考但量级比对不可靠。
- MX 对部分代码（如 300750）有港股歧义，需 `.SH`/`.SZ` 后缀消歧（当前 query 仅用 6 位代码）。
- MX snapshot 在 `get_stock_info` 长流程中间歇性失败（并发/限流），fail-open 降级到 iFinD 单源 medium。

## 10. 验证（离线测试）

新增模块均以离线 mock 测试，100% 覆盖，不依赖真实 key：

```bash
# 单模块覆盖率（绕过 numpy+coverage C 扩展冲突的自定义 runner）
./.venv/bin/python scripts/run_module_coverage.py data_provider.cross_source_validator tests.test_cross_source_validator

# 全部新模块 + 深度投研回归
./.venv/bin/python -m pytest tests/test_cross_source_validator.py \
  tests/test_mx_data_adapter.py tests/test_ifind_fundamental_adapter.py \
  tests/test_cross_validation_helpers.py tests/test_deep_research.py -v
```
