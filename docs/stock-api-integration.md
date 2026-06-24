# stock-api 数据源集成方案

> 状态：方案（待实施） · 日期：2026-06-23 · 上游：[`zhangxiangliang/stock-api`](https://github.com/zhangxiangliang/stock-api)（MIT）
> 决策已确认：① **链首优先**（直连源为 primary，akshare 降为字段补充） ② **范围 = 腾讯+新浪直连行情 + 股票代码搜索**

---

## 1. 背景与目标

本项目 A 股实时行情当前**全部经 `akshare` / `efinance` 库**间接命中腾讯/新浪/东方财富的公开端点。库层存在抖动：近期 E2E 验证中两次出现 `[efinance] 获取板块排行失败`、akshare 东财连接断开等问题。

[`stock-api`](https://github.com/zhangxiangliang/stock-api)（TypeScript，MIT，1.4k★，零运行时依赖）证明：**直连 HTTP**（不经过 akshare 库）即可稳定取回这些端点的行情，并自带成熟解析逻辑、自动兜底（`tencent → sina → eastmoney`）与在线接口状态监控。

**目标**：把 stock-api 的「直连取数」能力移植进本项目 Python 后端，作为 A 股实时行情的**链首 primary**，把 akshare 降为「字段补充」次源，降低实时行情对 akshare 库的依赖与抖动；同时补一个本项目缺失的「股票代码搜索」能力。

---

## 2. stock-api 项目分析

### 2.1 能力面

每个数据源（腾讯/新浪/东方财富）提供三类能力，统一归一化结构：

| 能力 | 方法 | 归一化输出 |
|---|---|---|
| 行情（实时） | `getStock` / `getStocks` | `Stock { name, code, now, low, high, percent, yesterday, source }` |
| K 线 | `getKlines` | `Kline { date, open, close, high, low, volume?, source }`，支持 `period`(day/week/month)、`count`、`adjust`(qfq/hfq/none) |
| 搜索 | `searchStocks` | 按关键字返回股票列表 |
| 诊断 | `inspectStock` | 多源探测结果（二期，不做） |

### 2.2 数据源能力矩阵（Node 后端运行时）

| 数据源 | 行情 | K 线 | 搜索 | 备注 |
|---|:---:|:---:|:---:|---|
| tencent | ✅ | ✅ | ✅ | A 股/港股/美股 |
| sina | ✅ | ✅ | ✅ | 行情/搜索需 `Referer`（仅后端可调） |
| eastmoney | ✅ | ✅ | ✅ | **A 股 only** |

### 2.3 架构

- `src/stocks/{tencent,sina,eastmoney}/index.ts`：各 provider，声明端点 URL、编码、分隔符、解析函数。
- `src/stocks/shared/provider.ts`：`createStockProvider` 工厂（quote/kline/search 配置驱动）。
- `src/stocks/auto/index.ts`：`stocks.auto` 自动兜底（tencent→sina→eastmoney，逐源尝试到非空）。
- `src/stocks/shared/{capabilities,normalize,code-mapper,kline}.ts`：能力声明、归一化、代码前缀映射。
- `test/fixtures/{tencent,sina,eastmoney}/*`：**原始 HTTP 响应 fixture**，可直接作为端口移植后的测试黄金集。

### 2.4 关键端点与解析索引（端口依据）

**腾讯**
- 行情：`GET https://qt.gtimg.cn/q=<codes>`（gbk，`~` 分隔）
  - 解析索引（`tencent/transforms/stock.ts`）：`name`=params[1]、`now`(现价)=params[3]、`pre_close`=params[4]、`high`=params[33]、`low`=params[34]；`percent = now/pre_close - 1`（比率）。
  - 缺失判定：`apiCode not in row`。
- 搜索：`GET https://smartbox.gtimg.cn/s3/?v=2&t=all&c=1&q=<key>`（gbk，`^` 分隔，`type~code`，type ∈ sz/sh/hk/us）

**新浪**
- 行情：`GET https://hq.sinajs.cn/list=<codes>`（**gb18030**，`,` 分隔，**必须 `Referer: https://finance.sina.com.cn/`**）
  - 解析索引（`sina/transforms/stock.ts`，按市场键）：SH/SZ `name`=0 / `now`=3 / `high`=4 / `low`=5 / `pre_close`=2；HK `name`=1 / `now`=6 / `high`=4 / `low`=5 / `pre_close`=3。
- 搜索：`GET https://suggest3.sinajs.cn/suggest/type=2&key=<key>`（gb18030）

**东方财富**（本项目已覆盖，**不移植**）：`push2(his).eastmoney.com/api/qt/stock/...`

---

## 3. 关键发现：上游重叠 + 本项目现状

**核心结论：stock-api 不是「新数据源」——它是对本项目已在用的同一批公开接口的零依赖、直连重实现。上游数据高度重叠：**

| 能力 | stock-api 端点 | 本项目现状 | 重叠 |
|---|---|---|---|
| 腾讯 K 线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | `TencentFetcher._KLINE_ENDPOINT` = **完全相同** | 🟰 同一端点 |
| 新浪行情 | `hq.sinajs.cn/list=` | 经 `akshare` 库间接调用 | 🟰 同上游 |
| 东财行情/K 线 | `push2(his).eastmoney.com/...` | `efinance` + `akshare_em` | 🟰 同上游 |
| 腾讯行情 | `qt.gtimg.cn/q=` | 经 `akshare`（`akshare_qq` token）间接 | 🟰 同上游 |

**因此集成的真正价值不是「多一个源」，而是：**

1. **去库依赖、降抖动（核心）**：把实时行情从「经 akshare 库」改为「直连 HTTP」，脱离 akshare 实时路径的脆弱性。
2. **补股票代码搜索**：本项目 `api/`、`src/agent/tools/` **均无**按名称查代码的能力，stock-api 的 `searchStocks` 正好补这块（纯增量，零冲突）。
3. **成熟解析 + 测试 fixture**：stock-api 的解析逻辑与 `test/fixtures/*` 原始响应可作 Python 测试黄金集，降低解析风险。

**K 线不做**：本项目 `TencentFetcher` 已直连同一腾讯 K 线端点，再做是纯重复。

---

## 4. 本项目数据源层现状（集成触点依据）

- **契约**：`data_provider/base.py` 的 `BaseFetcher`（`_fetch_raw_data` / `_normalize_data` 抽象方法）；实时行情统一结构 `UnifiedRealtimeQuote`（`realtime_types.py`）。
- **`RealtimeSource` 枚举**（`realtime_types.py:94`）：**早已声明** `tencent`="腾讯直连"、`sina`="新浪直连" —— 但派发逻辑从未落地（见下）。
- **实时行情派发**：`DataFetcherManager.get_realtime_quote`（`base.py:1611`）。A 股走 `realtime_source_priority` token 循环（`base.py:1709`），各 token 派发到对应 fetcher；首个成功源成为 primary，后续源经 `_SUPPLEMENT_FIELDS` 循环（`base.py:1858`，补 `volume_ratio/turnover_rate/pe/pb/total_mv/circ_mv/amplitude`）合并缺失字段。
  - **关键缺口**：派发把 `tencent` token 路由给了 **akshare**（`base.py:1746`），且**没有 `sina` 分支** —— 即枚举的「直连」意图在派发里从未实现。
- **`has_basic_data()`**（`realtime_types.py:181`）：仅要求 `price>0` → 直连行情（有现价）天然成为合法 primary。
- **配置**：`src/config.py:1025` `realtime_source_priority` 默认 `"tencent,akshare_sina,efinance,akshare_em"`；`_resolve_realtime_source_priority`（`config.py:2687`）在配了 `TUSHARE_TOKEN` 时自动 prepend `tushare`。
- **直连 K 线已存在**：`data_provider/tencent_fetcher.py`（直连腾讯 K 线，含 `_to_tencent_symbol` cn→sh/sz/bj 映射可复用）。
- **无股票代码搜索**：全仓无 `search_stock` 类能力（新闻/情报搜索不等于代码搜索）。

> **洞察**：把 `RealtimeSource` 枚举里早已标注的「直连」意图在派发里实现，再让现有 `_SUPPLEMENT_FIELDS` 循环用 akshare 补齐直连源缺失的字段 —— 这正是该循环的原生用法，**零新机制**即可达成「直连 primary + akshare supplement」。

---

## 5. 集成方式选型

| 方案 | 做法 | 评价 |
|---|---|---|
| **A. 端口移植成 Python 直连源（推荐 ✅）** | 把 stock-api 的腾讯/新浪行情解析 + 代码搜索用 Python 重写为 `data_provider/` 下的 provider，直连 HTTP，不经 akshare。 | 纯 Python、无 Node 依赖、进程内调用、契合现有 `BaseFetcher`+`realtime_source_priority` 契约。 |
| B. 子进程 / MCP 桥接 | `npx stock-api` 或起 MCP server，Python 调 JSON。 | ❌ 引入 Node 运行时依赖、每调一次 fork 进程（延迟+不稳定），供应链长任务几十次调用会放大问题。 |
| C. 自托管 HTTP sidecar | 跑 stock-api Node 服务，Python HTTP 调。 | ❌ 多一个进程要部署/运维/超时治理，与「FastAPI 单服务」模型相悖。 |

**采用 A。** stock-api 仅作「解析逻辑参考 + 测试 fixture 来源 + MIT 归属」，**不引入任何 Node/TS 依赖**。

---

## 6. 范围（做 / 不做）

**做（增量、补缺口）：**
- 腾讯**直连实时行情**（`qt.gtimg.cn/q=`）。
- 新浪**直连实时行情**（`hq.sinajs.cn/list=`，含 Referer）。
- **股票代码搜索**（腾讯 smartbox 优先，新浪 suggest3 兜底）。

**不做（已覆盖/无关）：**
- ❌ K 线（`TencentFetcher` 已直连同一端点）。
- ❌ 东财直连（`efinance`/`akshare_em` 已覆盖，增益小）。
- ❌ Node CLI / MCP / 浏览器构建（与 Python 后端无关）。
- ❌ `inspect_stock` 诊断面板（二期）。
- ❌ 港股/美股直连（沿用现有 Longbridge/Yfinance 双源路由；A 股 token 环只服务 cn/ETF）。

---

## 7. 详细技术方案（文件级）

### 7.1 新建 `data_provider/stockapi_realtime.py`（核心）

`class StockApiDirectQuoteProvider`（**非 `BaseFetcher`**，仿 `AkshareFundamentalAdapter` 由 manager 持有）：

- `get_realtime_quote(stock_code, *, source) -> Optional[UnifiedRealtimeQuote]`，`source ∈ {"tencent","sina"}`：
  - **腾讯**：`GET https://qt.gtimg.cn/q=<apiCode>`（gbk，`~`）。复用 `tencent_fetcher._to_tencent_symbol` 做 cn→`sh/sz/bj`。解析：`name`=p[1]、`price`=p[3]、`pre_close`=p[4]、`high`=p[33]、`low`=p[34]。
  - **新浪**：`GET https://hq.sinajs.cn/list=<apiCode>`（gb18030，**`Referer: https://finance.sina.com.cn/`**，`,`）。cn 用 `sh/sz`。解析（SH/SZ）：`name`=0、`price`=3、`high`=4、`low`=5、`pre_close`=2。
  - **缺失判定**：腾讯 `apiCode not in row`、新浪空值 → 返回 `None`（避免「无此股」误解析成 0 价）。
  - **字段映射** → `UnifiedRealtimeQuote`：`price=now`、`pre_close=yesterday`、`high`、`low`、`name`、`change_pct=(now/pre_close-1)*100`（**stock-api 的 percent 是比率，必须 ×100**）、`source=RealtimeSource.TENCENT/SINA`。volume/amount/pe/pb/mv **不填**（留 supplement）。
  - gbk/gb18030 解码：`resp.content.decode("gbk"/"gb18030")`；UA `Mozilla/5.0`；超时 5–8s。
- `search_stock_codes(query, limit=10) -> List[Dict]`：腾讯 `smartbox.gtimg.cn/s3/...`（gbk，`^`，`type~code` → sz/sh/hk/us 前缀）；失败兜底新浪 `suggest3.sinajs.cn`。返回 `[{code, name, market}]`。

### 7.2 改 `data_provider/base.py`

- `DataFetcherManager.__init__`（仿 `base.py:613-614` 持有 fundamental adapter 处）：懒加载实例化 `self._direct_quote_provider`（try/except 包裹，失败降级 `None` 不影响主流程）。
- `get_realtime_quote` 派发（`base.py:1746` 附近）：`source == "tencent"` 与新增 `source == "sina"` 指向 `self._direct_quote_provider.get_realtime_quote(stock_code, source=source)`；**保留 `akshare_qq`/`akshare_sina` 走 akshare**（作为直连之后的字段补充源）。`record_provider_run_started/record_provider_run` 埋点照搬（provider 名 `StockApiDirect:tencent`/`:sina`）。
- 新增 `DataFetcherManager.search_stock_codes(query, limit)`，委托 `self._direct_quote_provider`。

### 7.3 改 `src/config.py`

- 默认 `realtime_source_priority`（`:1025` 与 `_resolve_realtime_source_priority:2696`）：
  `"tencent,akshare_sina,efinance,akshare_em"` → **`"tencent,sina,akshare_qq,akshare_sina,efinance,akshare_em"`**
  （直连 primary 在前，akshare 紧随做 supplement，efinance 兜底；tushare 自动注入逻辑保留）。

### 7.4 暴露搜索能力（`api/` + `src/agent/tools/`）

- 新增 `GET /api/v1/search/stocks?q=<query>&limit=10`，调用 manager 的 `search_stock_codes`。
- 新增 agent 工具 `search_stock_code`（`data_tools.py` 模式），供问股/供应链 agent「按名称查代码」。

### 7.5 文档与归属

- `.env.example`：更新 `REALTIME_SOURCE_PRIORITY` 注释（`tencent`/`sina`=直连；`akshare_qq`/`akshare_sina`=经库）。
- 新增 `data_provider/LICENSE.stock-api.upstream`（MIT）+ 模块头注释注明来源。
- `docs/CHANGELOG.md [Unreleased]`：`[改进]` A 股实时行情新增腾讯/新浪直连源（链首优先，akshare 降为字段补充）；`[新功能]` 股票代码搜索。

---

## 8. 契约映射（stock-api `Stock` → `UnifiedRealtimeQuote`）

stock-api 行情结构比本项目更轻（无 volume/PE/PB/市值），定位为「**健壮的价格+涨跌幅 primary**」，缺字段由 `_SUPPLEMENT_FIELDS` 从 akshare 合并：

| stock-api `Stock` | 本项目 `UnifiedRealtimeQuote` | 说明 |
|---|---|---|
| `now` | `price` | 现价 |
| `high` / `low` | `high` / `low` | |
| `percent`（比率） | `change_pct`（%） | **×100** |
| `yesterday` | `pre_close` | |
| `name` / `code` | `name` / `code` | |
| `source` | `RealtimeSource.TENCENT/SINA` | |
| —（无） | `volume/amount/turnover/pe/pb/total_mv/circ_mv/amplitude` | **留给 supplement** 从 akshare 补 |

---

## 9. 测试策略

- **`tests/test_stockapi_realtime.py`（离线，进 CI）**：用 stock-api fixture 文本（`tencent/sh510500.txt`、`sina/sh510500-auction.txt`）作黄金集，`@patch("requests.get")` 喂回；断言字段映射正确（`price/pre_close/high/low/change_pct`×100）、缺行返回 `None`、gbk/gb18030 解码正确、code 前缀归一正确；`search_stock_codes` 喂 smartbox/suggest3 假响应断言前缀映射。
- **`tests/test_stockapi_realtime_routing.py`**：stub 直连 provider + akshare stub 进 `DataFetcherManager(fetchers=[...])`；断言「直连 primary 给价 + akshare supplement 补 volume/pe」合并顺序、`change_pct` 单位正确。
- **网络冒烟（`-m network`，非阻断）**：真请求 `qt.gtimg.cn`/`hq.sinajs.cn` 一只 A 股，验证在线可用。

---

## 10. 验证（端到端）

1. `python -m py_compile data_provider/stockapi_realtime.py data_provider/base.py src/config.py`
2. `python -m pytest tests/test_stockapi_realtime.py tests/test_stockapi_realtime_routing.py -v`（离线绿）
3. `python -m pytest -m "not network" -q`（无新增回归；既有 system_config 跨测试污染无关）
4. `./scripts/ci_gate.sh`
5. **在线冒烟**：重启后端，`curl` 既有实时行情端点，确认日志 `[实时行情] 600519 成功获取 (来源: tencent)` 且 `source=腾讯直连`、随后 `从 akshare_sina 补充了缺失字段`；并 `curl '/api/v1/search/stocks?q=茅台'` 返回 600519。

---

## 11. 风险 / 行为变更 / 回滚

| 项 | 说明 | 处置 |
|---|---|---|
| **行为变更**：`tencent` token 从「经 akshare」变「直连」 | 默认 priority 含 `tencent`，等价于默认链路改直连 | 决策①的预期；保留 `akshare_qq` 作「经库」逃生 token；CHANGELOG 注明 |
| 直连源缺 volume/pe/pb/mv | 非缺数据，由 supplement 补 | 复用既有 `_SUPPLEMENT_FIELDS` 循环，无需新机制 |
| 新浪必须 Referer / 反爬 | stock-api 明确浏览器不可用、仅后端可调 | 后端设 Referer；限频走 `CircuitBreaker`（`realtime_types.py:437`）+ 下个源 |
| stock-api fixture 是 TS 测试格式 | 需转 Python 字面量 | 移植时人工核对 `~`/`,` 切分位序与解析索引一致 |
| License | stock-api MIT | 加 `LICENSE.stock-api.upstream` + 头注释归属 |

**回滚**：还原 `realtime_source_priority` 默认串（直连带回到经 akshare）；删 `stockapi_realtime.py` + 派发分支 + 端点/工具；测试随之删除。无 DB/数据迁移。

---

## 12. 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| ① 直连源定位 | **链首优先**（primary） | 最大程度脱离 akshare 实时抖动，这正是集成核心价值；缺字段由 supplement 补 |
| ② 范围 | **腾讯+新浪直连行情 + 代码搜索** | 覆盖 A 股实时两大公开源 + 补本项目搜索缺口；K 线/东财直连增益小不做 |
| 集成方式 | **端口移植（方案 A）** | 纯 Python、无 Node 依赖、契合现有契约 |

---

## 13. 后续可选扩展（不在本期）

- 港股/美股直连（把直连 provider 接入 `base.py:1656` 的 US/HK 双源路由）。
- `inspect_stock` 多源诊断面板。
- 直连源命中率/熔断统计接入 `/api/v1/usage` 或监控。
