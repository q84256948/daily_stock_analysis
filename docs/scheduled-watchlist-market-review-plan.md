# 自选股与大盘复盘定时分析方案

> 决策前提：**以 `STOCK_LIST` 作为自选股唯一数据源**。前端自选股和后端定时任务均从 `STOCK_LIST` 读取；不使用外部任务作为定时或兜底执行入口。
>
> 审计结论（2026-06-25）：仓库已经完成部分 P0 能力，后续实现应以“补缺口”为主，避免新增平行实现。已存在能力包括：watchlist API 直接读写 `STOCK_LIST`、定时模式每次运行前重载配置、多任务调度基本能力、交易日检查、API/CLI/调度共用的大盘复盘文件锁。

## 1. 目标

1. 每天早上 **北京时间 9:00**，自动对 `STOCK_LIST` 中的全部股票执行个股分析，保存报告。
2. 每天晚上 **北京时间 21:00**，自动执行大盘复盘，保存报告。
3. 保证高可用：不重复执行、不遗漏、失败可感知。
4. 成本可控：节假日不跑、任务互斥、超时可控。

---

## 2. 现状

- 后端 `main.py --schedule` 已支持两个独立定时任务：`WATCHLIST_ANALYSIS_TIME`、`MARKET_REVIEW_TIME`。
- `STOCK_LIST` 已在 `src/core/config_registry.py` 注册为可编辑数组，支持通过 Web 设置页修改。
- 前端 `useWatchlist.ts` 通过 `systemConfigApi.getWatchlist/addToWatchlist/removeFromWatchlist` 管理自选股；后端 `/api/v1/stocks/watchlist*` 当前已直接读写 `STOCK_LIST`。
- 默认配置中 `SCHEDULE_ENABLED=false`，`WATCHLIST_ANALYSIS_TIME=`，`MARKET_REVIEW_TIME=`，定时任务未启用。
- 定时模式会忽略启动时传入的 `--stocks` 快照，并在每次任务触发前通过 `_reload_runtime_config()` 重读当前保存的 `STOCK_LIST`。
- 已有 `TRADING_DAY_CHECK_ENABLED` 和 `src/core/trading_calendar.py`，支持按 A/H/美市场交易日过滤；不需要新增 `SCHEDULE_SKIP_HOLIDAY` 平行开关。
- 已有 `src/core/market_review_lock.py`，大盘复盘在 CLI、API、调度入口共用锁；缺口是自选股分析任务仍缺少同级别互斥。
- 主要缺口：多任务模式不会热更新 `WATCHLIST_ANALYSIS_TIME` / `MARKET_REVIEW_TIME`；调度状态、执行日志、健康检查、失败告警和前端状态卡片尚未形成统一闭环。

---

## 3. 数据源统一：以 STOCK_LIST 为准

### 3.1 目标数据流

```
┌─────────────────┐     ┌─────────────────────────────┐
│  前端 StockBar   │────▶│  watchlist API (CRUD)       │
│  / SettingsPage  │     │  实际读写持久化配置中的       │
└─────────────────┘     │  key=STOCK_LIST              │
                        └─────────────────────────────┘
                                      │
        ┌─────────────────────────────┴─────────────────────────────┐
        ▼                                                           ▼
┌───────────────┐                                         ┌─────────────────┐
│ 后端定时任务   │                                         │  main.py CLI    │
│ --schedule    │                                         │  --stocks ...   │
└───────────────┘                                         └─────────────────┘
```

### 3.2 后端改造

- **持久化配置中的 `STOCK_LIST` 为唯一真源**。当前仓库的系统配置服务以 `.env` / `ConfigManager` 持久化为主，不按“system_config 表”设计新增表。
- 环境变量 `STOCK_LIST` 只作为进程启动输入；Web 设置页和 watchlist API 保存后应写回同一个持久化配置文件。
- 复用现有 `Config.refresh_stock_list()`、`_reload_runtime_config()` 和 `/api/v1/stocks/watchlist*`，仅在发现重复解析时再收敛一个小函数：
  ```python
  def get_stock_list() -> List[str]:
      # 优先从 Config / SystemConfigService 已加载配置读取
      # 回退到环境变量 STOCK_LIST
      # 去重、过滤空值、校验格式
  ```
- 所有定时入口必须继续在任务触发时读取最新配置，不能把启动时股票列表闭包进任务。
- `main.py --stocks` 保持手动 CLI 覆盖语义；只有 `--schedule` / `SCHEDULE_ENABLED=true` 模式忽略 `--stocks` 快照。

### 3.3 前端改造

- `useWatchlist.ts` 继续调用现有 `systemConfigApi.getWatchlist/addToWatchlist/removeFromWatchlist`。
- **后端 watchlist API 实际读写 `STOCK_LIST` 配置项**，不再维护独立 watchlist 表。
- 前端设置页中 `STOCK_LIST` 文本框与首页自选股增删保持一致：
  - 在首页增删股票后，同步更新 `STOCK_LIST`。
  - 在设置页修改 `STOCK_LIST` 后，首页自选股列表立即刷新。
- 在设置页 `STOCK_LIST` 字段旁增加说明："该列表即为定时分析的股票清单。"

### 3.4 不采用的方案

- **不以 watchlist 表为准**：避免后端已大量依赖 `STOCK_LIST` 的代码需要大规模重构。
- **不维护双写**：避免两边数据漂移，只保留单一真源。

---

## 4. 时区统一：强制北京时间

### 4.1 原则

- `WATCHLIST_ANALYSIS_TIME` 和 `MARKET_REVIEW_TIME` 统一按 **Asia/Shanghai** 解析。
- 所有运行环境（本地、Docker、服务器）统一设置 `TZ=Asia/Shanghai`。

### 4.2 后端

- `src/scheduler.py` 当前使用 `schedule.every().day.at(...)`，按进程本地时区解释。实现时优先在进程入口设置/校验 `TZ=Asia/Shanghai`，不要引入额外调度库。
- 启动日志中打印当前生效时区、所有已注册任务名和下次执行时间，便于排查。
- 增加配置项描述："时间为北京时间（Asia/Shanghai）。"
- 若继续使用 `schedule` 库，验收必须覆盖：本地非 Asia/Shanghai 时区下启动会给出明确 warning，或被启动脚本强制注入 `TZ=Asia/Shanghai`。

### 4.3 部署

- Docker：`docker-compose.yml` 增加 `TZ=Asia/Shanghai`。
- systemd：服务单元增加 `Environment=TZ=Asia/Shanghai`。

---

## 5. 执行互斥：防止重复跑任务

### 5.1 方案

采用**文件锁**，适合当前 SQLite + 单机/单容器部署。不要替换已有大盘复盘锁；只补齐自选股分析和调度任务级互斥。

### 5.2 实现

- 已有大盘复盘锁：`src/core/market_review_lock.py`。保留它作为 API / CLI / scheduler 共享锁。
- 新增最小通用锁仅覆盖缺口，例如 `src/core/scheduled_task_lock.py`：
  ```python
  class TaskLock:
      def acquire(self, task_name: str, timeout_seconds: int = 7200) -> bool
      def release(self, task_name: str)
      def is_locked(self, task_name: str) -> bool
  ```
- 锁文件放在 `Path(config.database_path).parent / "locks" / "{task_name}.lock"`，避免写死 `data/`。
- 锁内容包含 PID、开始时间、任务名、计划触发时间。
- 锁超时时间可配置：`SCHEDULE_LOCK_TIMEOUT=7200`（默认 2 小时）。

### 5.3 使用

- `watchlist_analysis_task` 开头获取 `watchlist_analysis` 锁。
- `market_review_task` 继续通过 `_run_market_review_with_shared_lock()` 使用现有大盘复盘锁；不要再包一层新锁，避免锁顺序复杂化。
- 获取失败则跳过并记录：`"{task} is already running (pid={pid}), skip this run."`
- 任务完成或异常退出时释放锁（`try/finally`）。
- 启动时清理过期锁（根据文件中的时间戳和 `SCHEDULE_LOCK_TIMEOUT`）。

### 5.4 后续扩展

如果未来改为多机部署，可将文件锁替换为 Redis 分布式锁，接口保持不变。

---

## 6. 节假日/非交易日过滤

### 6.1 原则

- 非交易日不执行对应市场的自选股分析和大盘复盘，避免浪费 token。
- 当前仓库已经支持 A/H/美市场识别，不能退化为“全部按 A 股交易日处理”。

### 6.2 实现

- 复用现有配置：
  ```bash
  TRADING_DAY_CHECK_ENABLED=true
  ```
- 复用 `src/core/trading_calendar.py`：
  - 依赖 `exchange-calendars` 按 `cn` / `hk` / `us` 判断交易日。
  - 失败时 fail-open，避免日历源异常导致真实交易日任务被误跳过。
  - 自选股按股票所属市场逐只过滤；大盘复盘按 `MARKET_REVIEW_REGION` 计算有效市场。
- 在定时任务启动前判断：
  ```python
  if no_open_market_for_this_task:
      logger.info("非交易日，跳过 %s", task_name)
      return
  ```

### 6.3 手动覆盖

- 设置页沿用 `TRADING_DAY_CHECK_ENABLED`："启用交易日检查"。
- 首页手动触发按钮不受节假日限制，用户可随时手动跑。
- CLI 可继续用 `--force-run` 覆盖交易日检查。

---

## 7. 失败重试与告警

### 7.1 重试策略

| 任务 | 策略 |
|---|---|
| 自选股分析 | 单只股票失败继续跑其余股票；整体任务失败时，整体重试 1 次（间隔 5 分钟）。 |
| 大盘复盘 | 失败时重试 1 次（间隔 10 分钟），仍失败则告警。 |

### 7.2 告警

- 复用项目已有通知能力（`src/notification_sender/`）。
- 新增配置：
  ```bash
  SCHEDULE_ALERT_ENABLED=true
  SCHEDULE_ALERT_CHANNELS=wechat   # 可选 wechat/email/lark/dingtalk
  ```
- 告警内容：任务名、计划时间、失败原因、最后成功时间。
- 告警必须走既有通知路由和脱敏规则；不要在日志、告警正文或 API 响应中输出密钥、webhook、完整 prompt 或原始 provider response。
- 任务被锁跳过、非交易日跳过、空 `STOCK_LIST` 跳过应记录为 `skipped`，默认不告警；只有连续 N 次失败或任务运行异常才告警，避免节假日/空列表噪声。

### 7.3 执行记录

- 扩展 `analysis_history` 表或新增 `scheduled_task_log` 表，记录：
  - `task_name`
  - `scheduled_at`
  - `started_at`
  - `finished_at`
  - `status`：success / partial_failure / failed
  - `detail`：JSON，含成功数、失败数、错误摘要
  - `report_path`
- 前端通过该表展示最近执行时间和状态。
- 推荐新增 `scheduled_task_log` 而不是扩展 `analysis_history`：调度跳过、锁冲突、空列表和失败重试不一定有报告产物，强塞进分析历史会污染历史报告列表。
- `scheduled_task_log.detail` 只存摘要 JSON：股票数量、成功/失败/跳过数量、失败代码列表、错误类型和截断后的错误摘要。

---

## 8. 报告保存策略

### 8.1 当前行为

- 个股报告：`reports/report_YYYYMMDD.md`
- 大盘复盘报告：`reports/market_review_YYYYMMDD.md`
- 同一天多次执行会覆盖。

### 8.2 优化

- **大盘复盘**：保持 `market_review_YYYYMMDD.md`（每天一份最新）。
- **个股总报告**：保持 `report_YYYYMMDD.md`（每天一份最新）。
- **个股独立报告**：新增 `reports/stocks/{code}/report_YYYYMMDD.md`，便于前端按股票查询历史。
- **归档**：每次运行前，将旧的 `report_YYYYMMDD.md` / `market_review_YYYYMMDD.md` 复制到 `reports/archive/report_YYYYMMDD_HHMMSS.md`。
- 数据库 `analysis_history` 中记录最新报告路径。
- 归档必须放在报告写入的同一文件系统内，并使用原子替换/复制失败不阻塞主报告保存。
- 个股独立报告属于后续增强，不应作为 P0 阻断项；当前前端历史主要依赖 `analysis_history`，先保证历史记录和报告内容一致。

---

## 9. 进程保活与部署

### 9.1 Docker Compose（推荐）

在 `docker/docker-compose.yml` 中新增 `scheduler` 服务：

```yaml
services:
  scheduler:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    command: python main.py --schedule
    env_file: ../.env
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ../data:/app/data
      - ../reports:/app/reports
      - ../logs:/app/logs
    restart: unless-stopped
    deploy:
      replicas: 1   # 关键：必须只跑一个实例
```

> 必须确保 `replicas=1`，否则文件锁会失效。

### 9.2 systemd（服务器裸跑）

创建 `/etc/systemd/system/dsa-scheduler.service`：

```ini
[Unit]
Description=DSA Daily Stock Analysis Scheduler
After=network.target

[Service]
Type=simple
User=dsa
WorkingDirectory=/opt/daily_stock_analysis
Environment=TZ=Asia/Shanghai
Environment=PATH=/opt/daily_stock_analysis/.venv/bin:/usr/local/bin:/usr/bin
ExecStart=/opt/daily_stock_analysis/.venv/bin/python main.py --schedule
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable dsa-scheduler
sudo systemctl start dsa-scheduler
```

### 9.3 健康检查

- 调度进程每分钟向 scheduler heartbeat 文件写入时间戳。
- 外部监控检查该文件是否 5 分钟内未更新，则告警。
- heartbeat 路径应基于 `Path(config.database_path).parent / "scheduler_heartbeat"`，不要写死 `data/`。
- heartbeat 内容包含 ISO 时间、PID、已注册任务、下次执行时间、最近一次 scheduler loop 错误摘要。

---

## 10. 前端增强

### 10.1 设置页

- 审计现状：`apps/dsa-web/src/utils/systemConfigI18n.ts` 已有 `STOCK_LIST`、`SCHEDULE_ENABLED`、`SCHEDULE_RUN_IMMEDIATELY`、`TRADING_DAY_CHECK_ENABLED` 等标签；`apps/dsa-web/src/locales/settingsHelp.ts` 已有 `WATCHLIST_ANALYSIS_TIME` / `MARKET_REVIEW_TIME` 帮助。
- 后续只补齐缺失字段，不重复新增同义文案：
  - `STOCK_LIST`：自选股列表（定时分析股票）
  - `WATCHLIST_ANALYSIS_TIME`：自选股分析时间
  - `MARKET_REVIEW_TIME`：大盘复盘时间
  - `SCHEDULE_ENABLED`：启用定时任务
  - `TRADING_DAY_CHECK_ENABLED`：启用交易日检查
  - `SCHEDULE_ALERT_ENABLED`：任务失败告警
- `STOCK_LIST` 文本框旁增加说明文案。

### 10.2 首页状态卡片

新增 `ScheduleStatusCard` 组件：

- 最近个股分析时间、状态、成功数/失败数。
- 最近大盘复盘时间、状态。
- 下次计划执行时间。
- "立即分析自选股"、"立即大盘复盘" 手动按钮。
- 数据来源：`GET /api/v1/schedule/status`。
- 每 5 分钟轮询，或用户手动刷新。
- 卡片应复用现有首页 dashboard 视觉组件，避免新增一套卡片样式。
- 状态接口返回空日志时展示“尚无定时执行记录”，不要当作失败。

### 10.3 自选股同步

- 首页 `useWatchlist.ts` 增删股票时，后端 watchlist API 写入 `STOCK_LIST` 配置。
- 设置页修改 `STOCK_LIST` 后，前端缓存失效，首页自动刷新。

---

## 11. 后端接口

### 11.1 新增接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/schedule/status` | 返回最近执行记录、下次执行时间、任务健康状态 |
| POST | `/api/v1/schedule/trigger` | 手动触发一次指定任务（watchlist/market_review） |
| GET | `/api/v1/schedule/logs` | 返回最近调度日志（分页） |

接口约束：
- 复用现有 API 认证依赖；`ADMIN_AUTH_ENABLED=true` 时必须要求管理员会话。
- `POST /api/v1/schedule/trigger` 只接受 `watchlist` / `market_review`，返回现有异步任务语义或调度日志 id；重复运行时返回明确 `409 duplicate_task`。
- 手动触发默认不受交易日检查限制；如后续要支持检查，必须显式请求字段控制，避免和现有 `POST /api/v1/analysis/market-review` 人工触发语义冲突。
- `/schedule/logs` 默认分页、限制最大 page size，并只返回脱敏摘要。

### 11.2 改造现有接口

- `systemConfigApi.getWatchlist` / `addToWatchlist` / `removeFromWatchlist` 已经操作 `STOCK_LIST` 配置。
- 后续只补测试和文档验收：等价代码匹配、并发保存冲突、设置页修改后首页刷新。

---

## 12. 配置清单

更新 `.env.example`：

```bash
# 定时任务总开关
SCHEDULE_ENABLED=true

# 自选股分析时间（北京时间）
WATCHLIST_ANALYSIS_TIME=09:00

# 大盘复盘时间（北京时间）
MARKET_REVIEW_TIME=21:00

# 启动 schedule 时是否立即执行一次
SCHEDULE_RUN_IMMEDIATELY=false

# 是否启用交易日检查
TRADING_DAY_CHECK_ENABLED=true

# 任务锁超时时间（秒）
SCHEDULE_LOCK_TIMEOUT=7200

# 任务失败告警
SCHEDULE_ALERT_ENABLED=true
SCHEDULE_ALERT_CHANNELS=wechat

# 时区
TZ=Asia/Shanghai

# 手动补充节假日：不新增，继续使用 exchange-calendars；
# 如未来确需手动覆盖，再单独设计 per-market 覆盖项。
```

已存在配置不重复新增：`SCHEDULE_ENABLED`、`SCHEDULE_TIME`、`SCHEDULE_RUN_IMMEDIATELY`、`RUN_IMMEDIATELY`、`MARKET_REVIEW_ENABLED`、`WATCHLIST_ANALYSIS_TIME`、`MARKET_REVIEW_TIME`、`DAILY_MARKET_CONTEXT_ENABLED`、`MARKET_REVIEW_REGION`、`TRADING_DAY_CHECK_ENABLED`。

---

## 13. 实施优先级

| 阶段 | 内容 |
|---|---|
| P0 | 后端：确认并补测试覆盖 watchlist API 读写 `STOCK_LIST`、定时模式每次触发重读 `STOCK_LIST`；启用 `SCHEDULE_ENABLED` + `WATCHLIST_ANALYSIS_TIME=09:00` + `MARKET_REVIEW_TIME=21:00` + `TZ=Asia/Shanghai` |
| P0 | 后端：补自选股分析任务锁；保留已有大盘复盘锁 |
| P0 | 后端：补多任务模式热更新或明确保存后需重启 scheduler；当前单任务 `SCHEDULE_TIME` 已有热更新，多任务时间尚未闭环 |
| P1 | 后端：复用现有 `TRADING_DAY_CHECK_ENABLED` / `trading_calendar` 完成多市场交易日验收 |
| P1 | 后端：新增 `/schedule/status`、`/schedule/trigger` 接口和 `scheduled_task_log` |
| P1 | 前端：只补缺失 i18n/help 文案，新增 `ScheduleStatusCard` |
| P2 | 后端：失败告警接入通知通道 |
| P2 | 部署：Docker Compose scheduler 服务 + systemd 配置 |
| P2 | 报告归档与个股独立报告 |

---

## 14. 测试与验证

### 14.1 本地快速验证

新增 `scripts/test_schedule.py`：

```bash
# 验证调度逻辑（不等待真实时间）
python scripts/test_schedule.py --task watchlist --time 09:00 --dry-run
python scripts/test_schedule.py --task market_review --time 21:00 --dry-run
```

验证点：
- 是否正确读取 `STOCK_LIST`
- 是否正确按交易日过滤任务
- 是否正确获取锁
- 是否正确保存报告
- 是否正确写入执行记录

### 14.2 单元测试

- `tests/test_scheduled_task_lock.py`：自选股任务锁、过期锁清理、锁冲突跳过。
- `tests/test_market_review_lock.py`：保留并补充已有大盘复盘锁覆盖，确保 API/CLI/scheduler 共享。
- `tests/test_scheduler_multi_task.py`：补多任务热更新或“配置变更需重启”的明确行为。
- `tests/test_main_schedule_mode.py`：覆盖定时任务重读 `STOCK_LIST`、忽略 `--stocks` 快照、交易日过滤、锁跳过。
- `tests/test_trading_calendar.py` 或现有交易日历测试：覆盖 A/H/美多市场过滤，不新增 A 股-only 日历。
- `tests/test_stock_list_config_sync.py` / `tests/test_system_config_api.py`：覆盖 watchlist API 与 `STOCK_LIST` 同源、等价代码去重、并发版本冲突。
- Web：补 `ScheduleStatusCard` 和设置页文案测试；如修改 watchlist 刷新逻辑，补 `useWatchlist` / `SettingsPage` 回归。

### 14.3 验收命令

后端改动默认执行：

```bash
python -m pytest tests/test_scheduler_multi_task.py tests/test_main_schedule_mode.py tests/test_market_review_lock.py
python -m py_compile main.py src/scheduler.py src/core/market_review_lock.py
```

Web 改动默认执行：

```bash
cd apps/dsa-web
npm run lint
npm run build
```

若新增配置项，必须同步 `.env.example`、`src/core/config_registry.py`、`apps/dsa-web/src/utils/systemConfigI18n.ts`、`apps/dsa-web/src/locales/settingsHelp.ts` 和相关测试。

---

## 15. 回滚方案

| 场景 | 回滚操作 |
|---|---|
| 定时任务费用激增 | 设置 `SCHEDULE_ENABLED=false` 并重启 scheduler 服务 |
| 任务重复执行 | 清理数据库目录旁 `locks/` 下过期锁；检查是否启动了多个 scheduler 实例 |
| 报告被覆盖 | 从 `reports/archive/` 恢复上一版本 |
| 时区错误 | 检查 `TZ=Asia/Shanghai` 是否生效，修正后重启 |
| 新代码导致崩溃 | 回滚代码/镜像，恢复旧 `.env`，重启服务 |
| 自选股同步异常 | 回滚 watchlist API 到上一版 `STOCK_LIST` 读写实现；不要恢复独立 watchlist 表，避免重新制造双真源 |

---

## 16. 关键决策记录

| 决策 | 选择 | 原因 |
|---|---|---|
| 自选股数据源 | 以 `STOCK_LIST` 为准 | 后端已大量依赖 `STOCK_LIST`，改造成本最低；`STOCK_LIST` 已支持 Web 设置页编辑。 |
| 定时执行方式 | 服务器常驻进程为主 | 已具备、无冷启动、可直接读写本地数据库和报告文件。 |
| 互斥方案 | 文件锁 | 当前 SQLite 单机架构下成本最低，未来可无缝替换为 Redis 分布式锁。 |
| 交易日过滤 | 复用 `exchange-calendars` | 仓库已有 `src/core/trading_calendar.py`，支持 A/H/美多市场且失败 fail-open。 |
| 报告策略 | 每天保留最新一份 + 归档 | 保证前端读取路径稳定，同时保留历史。 |
