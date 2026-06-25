# 端到端个股分析测试报告

**日期**: 2026-06-25  
**测试环境**: macOS，Python 3.11.14，本地 FastAPI 服务 (`main.py --serve-only`)  
**测试分支**: main（已同步远程最新代码）  
**测试股票**: 600519 贵州茅台、000858 五粮液  

---

## 1. 测试目标

验证本地启动后，通过 API 触发个股分析的完整链路是否可用：

1. 服务启动成功，健康检查通过。
2. `POST /api/v1/analysis/analyze` 能成功提交异步分析任务。
3. `GET /api/v1/analysis/status/{task_id}` 能正确返回任务进度和最终结果。
4. 分析结果能成功保存到 `analysis_history` 表。
5. `GET /api/v1/history/stocks` 能正确返回历史记录。

---

## 2. 测试环境

### 2.1 启动命令

```bash
tmux new-session -d -s dsa_server ".venv/bin/python main.py --serve-only --host 0.0.0.0 --port 8000"
```

### 2.2 关键配置（来自 `.env`）

- LLM 渠道: `minimax` / `claude-sonnet-4-6`
- 通知: 未配置
- Tushare Token: 未配置（使用其他数据源 fallback）
- 深度投研双源验证: 开启

### 2.3 已知前置问题

启动日志中出现以下警告，但**不影响**分析主流程：

- `未配置 STOCK_LIST`
- `未配置 Tushare Token，将使用其他数据源`
- `未配置通知渠道，将不发送推送通知`
- 某 SearXNG 实例返回 500/429
- 东财某接口连接被远端断开（有 akshare/新浪 fallback）

---

## 3. 测试用例与结果

### 3.1 健康检查

**请求**:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

**结果**:

```json
{"status":"ok","timestamp":"2026-06-25T17:01:45.223645"}
```

✅ 通过

---

### 3.2 用例 1：600519 贵州茅台（修复前）

**请求**:

```bash
POST /api/v1/analysis/analyze
Content-Type: application/json

{
  "stock_code": "600519",
  "report_type": "brief",
  "async_mode": true,
  "analysis_phase": "auto",
  "notify": false,
  "report_language": "zh"
}
```

**执行时间**: 约 6 分 30 秒  
**最终状态**: `completed`  
**诊断状态**: `failed`  
**失败原因**: `报告历史保存失败：未知错误`

**底层错误**（来自 `logs/stock_analysis_debug_20260625.log`）：

```
(sqlite3.OperationalError) table analysis_history has no column named research_framework
[SQL: INSERT INTO analysis_history (... research_framework, bayesian_framework, supply_chain, value_scenarios, investment_conclusion ...) VALUES (...)]
```

**分析**: 代码模型 `AnalysisHistory` 已新增 5 个字段（`research_framework`、`bayesian_framework`、`supply_chain`、`value_scenarios`、`investment_conclusion`），但本地已有的 SQLite 数据库表未同步更新。

⚠️ **测试结论**: 分析生成成功，但历史保存失败；属于数据库 schema 漂移问题。

---

### 3.3 用例 2：000858 五粮液（修复数据库后）

**修复操作**:

```sql
ALTER TABLE analysis_history ADD COLUMN research_framework TEXT;
ALTER TABLE analysis_history ADD COLUMN bayesian_framework TEXT;
ALTER TABLE analysis_history ADD COLUMN supply_chain TEXT;
ALTER TABLE analysis_history ADD COLUMN value_scenarios TEXT;
ALTER TABLE analysis_history ADD COLUMN investment_conclusion TEXT;
```

并确认 `scheduled_task_log` 表已存在。

**请求**:

```bash
POST /api/v1/analysis/analyze
Content-Type: application/json

{
  "stock_code": "000858",
  "report_type": "brief",
  "async_mode": true,
  "analysis_phase": "auto",
  "notify": false,
  "report_language": "zh"
}
```

**执行时间**: 约 4 分 30 秒  
**最终状态**: `completed`  
**诊断状态**: `degraded`  
**历史保存**: `ok`

**诊断摘要**:

| 组件 | 状态 | 说明 |
|---|---|---|
| realtime_quote | ok | 实时行情获取成功 |
| daily_data | degraded | 日线数据 TencentFetcher 成功，前置数据源失败后已继续 |
| news | unknown | 新闻未进入本次分析输入 |
| llm | ok | LLM claude-sonnet-4-6 成功 |
| notification | unknown | 未配置通知渠道 |
| history | ok | 报告历史保存成功 |

**返回结果摘要**（000858 五粮液）:

- 当前价: 75.0
- 建议: 观望
- 情绪评分: 32（悲观）
- 趋势预测: 看空
- 模型: claude-sonnet-4-6

✅ **测试结论**: 端到端分析链路打通，结果可正常保存和查询。

---

### 3.4 历史记录查询

**请求**:

```bash
curl -s "http://127.0.0.1:8000/api/v1/history/stocks"
```

**结果**:

```json
{
  "total": 1,
  "items": [
    {
      "id": 2,
      "stock_code": "000858",
      "stock_name": "五粮液",
      "report_type": "brief",
      "sentiment_score": 32,
      "operation_advice": "观望",
      "action": "watch",
      "analysis_count": 1,
      "last_analysis_time": "2026-06-25T17:13:01.049356",
      "model_used": "claude-sonnet-4-6"
    }
  ]
}
```

✅ 通过

---

## 4. 发现的问题

### 4.1 🔴 数据库 schema 漂移（阻断首次测试）

**问题**: `analysis_history` 表缺少 `research_framework` 等 5 个新字段，导致分析完成后无法保存历史记录。

**影响**: 首次 600519 测试分析生成成功但保存失败；前端历史列表、个股栏状态均无法更新。

**根因**: 新功能（五段式长线投研 / 评分框架）在 `src/storage.py` 模型中新增字段，但未提供数据库迁移脚本；已有本地数据库按旧 schema 创建。

**建议**:

1. 新增数据库迁移脚本（如 `scripts/migrate_analysis_history.py` 或引入 Alembic）。
2. 或在 `DatabaseManager` 启动时自动检测并补齐缺失列。
3. 在部署文档中说明升级时需要执行迁移。

---

### 4.2 🟡 部分数据源不稳定（非阻断）

**现象**:

- 东财 `push2.eastmoney.com` 接口多次 `RemoteDisconnected`。
- 某 SearXNG 实例返回 500 / 429。
- iFinD MCP 端点返回 405 Not Allowed。

**影响**: 分析流程有 fallback，最终仍能完成，但耗时增加（多次重试）。

**建议**: 监控数据源健康度，对频繁失败的源增加快速失败或降级逻辑。

---

### 4.3 🟢 分析耗时较长

**现象**: 单只股票 `brief` 报告约需 4-6 分钟。

**原因**: Agent 多步推理 + LLM 调用 + 多数据源获取 + 双源交叉验证。

**建议**: 若需批量定时分析，建议增加超时控制、并发限制和进度通知。

---

## 5. 验证总结

| 检查项 | 第一次（600519） | 第二次（000858，修复后） |
|---|---|---|
| 服务启动 | ✅ | ✅ |
| 健康检查 | ✅ | ✅ |
| 任务提交 | ✅ | ✅ |
| 进度轮询 | ✅ | ✅ |
| LLM 分析 | ✅ | ✅ |
| 报告历史保存 | ❌ schema 缺失 | ✅ |
| 历史记录查询 | - | ✅ |

**总体结论**: 个股分析端到端功能可用，但首次部署/升级时必须处理 `analysis_history` 表的 schema 迁移，否则历史保存会失败。

---

## 6. 后续建议

1. **立即处理**: 补充 `analysis_history` 表迁移脚本，避免其他环境踩坑。
2. **回归测试**: 在 CI 中增加一个轻量级端到端 smoke 测试（可使用 mock LLM）。
3. **性能优化**: 评估 `brief` 报告 4-6 分钟的耗时是否可接受，考虑增加缓存或精简数据获取。
4. **数据源监控**: 对东财/SearXNG/iFinD 的失败增加告警或自动降级。

---

## 7. 附录

### 7.1 关键日志路径

- 常规日志: `logs/stock_analysis_20260625.log`
- 调试日志: `logs/stock_analysis_debug_20260625.log`
- 服务日志: `logs/e2e_server_test_v5.log`

### 7.2 测试脚本参考

```bash
# 启动服务
tmux new-session -d -s dsa_server ".venv/bin/python main.py --serve-only --host 0.0.0.0 --port 8000"

# 提交分析任务
curl -s -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H "Content-Type: application/json" \
  -d '{"stock_code":"000858","report_type":"brief","async_mode":true,"notify":false}'

# 查询状态
curl -s "http://127.0.0.1:8000/api/v1/analysis/status/{task_id}"

# 查询历史
curl -s "http://127.0.0.1:8000/api/v1/history/stocks"
```
