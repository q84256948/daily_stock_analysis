# analysis_history 表字段迁移教程（2025-06-25）

> 适用场景：从旧版本升级后，本地/服务器上的 `data/stock_analysis.db` 已经存在，但代码中的 `AnalysisHistory` 模型已新增五段式投研相关字段，导致分析完成后保存历史记录失败。

---

## 1. 什么情况下需要执行本迁移

如果你遇到以下报错，说明当前数据库 schema 与代码模型不一致，需要执行迁移：

```
sqlite3.OperationalError: table analysis_history has no column named research_framework
```

或类似错误：

```
sqlite3.OperationalError: table analysis_history has no column named bayesian_framework
sqlite3.OperationalError: table analysis_history has no column named supply_chain
sqlite3.OperationalError: table analysis_history has no column named value_scenarios
sqlite3.OperationalError: table analysis_history has no column named investment_conclusion
```

### 典型触发场景

- 从只包含基础 `analysis_history` 字段的旧版本代码，升级到包含五段式长线投研/评分框架的新版本。
- 首次在新机器部署时如果直接复用了旧数据库文件。
- 定时任务或 API 分析完成后，日志提示“报告历史保存失败：未知错误”。

---

## 2. 迁移脚本位置

```
scripts/migrate_analysis_history_20250625.py
```

该脚本为**幂等脚本**：

- 已存在的字段不会重复添加。
- 已存在的 `scheduled_task_log` 表不会重复创建。
- 多次执行不会产生副作用。

---

## 3. 前置检查

### 3.1 确认数据库文件存在

默认数据库路径：

```bash
ls -la data/stock_analysis.db
```

如果通过环境变量 `DATABASE_PATH` 自定义了路径，请确保该路径可访问。

### 3.2 确认当前 schema

可以通过 SQLite 命令行查看当前表结构：

```bash
sqlite3 data/stock_analysis.db "PRAGMA table_info(analysis_history);"
```

如果输出中缺少以下字段，则需要迁移：

- `research_framework`
- `bayesian_framework`
- `supply_chain`
- `value_scenarios`
- `investment_conclusion`

---

## 4. 执行迁移

### 4.1 停止相关服务（推荐）

迁移前建议停止正在访问数据库的进程，避免写冲突：

```bash
# 如果正在运行 API 服务
pkill -f "main.py --serve"
pkill -f "main.py --serve-only"

# 如果正在运行定时调度
pkill -f "main.py --schedule"
```

> 注意：SQLite 在运行期间也可以执行 `ALTER TABLE`，但为了避免迁移期间恰好有写入导致锁等待，建议先停止服务。

### 4.2 备份数据库（强烈建议）

```bash
cp data/stock_analysis.db data/stock_analysis.db.bak.$(date +%Y%m%d_%H%M%S)
```

### 4.3 运行迁移脚本

```bash
.venv/bin/python scripts/migrate_analysis_history_20250625.py
```

预期输出：

```
[INFO] Migrating database: /Users/eric/dreame/code/daily_stock_analysis/data/stock_analysis.db
[ADD]  analysis_history.research_framework TEXT
[ADD]  analysis_history.bayesian_framework TEXT
[ADD]  analysis_history.supply_chain TEXT
[ADD]  analysis_history.value_scenarios TEXT
[ADD]  analysis_history.investment_conclusion TEXT
[CREATE] scheduled_task_log table and index
[DONE] Migration completed successfully
```

如果字段已经存在，则输出为：

```
[INFO] Migrating database: /Users/eric/dreame/code/daily_stock_analysis/data/stock_analysis.db
[SKIP] analysis_history.research_framework already exists
[SKIP] analysis_history.bayesian_framework already exists
[SKIP] analysis_history.supply_chain already exists
[SKIP] analysis_history.value_scenarios already exists
[SKIP] analysis_history.investment_conclusion already exists
[SKIP] scheduled_task_log table already exists
[DONE] Migration completed successfully
```

---

## 5. 验证迁移结果

### 5.1 检查表结构

```bash
sqlite3 data/stock_analysis.db "PRAGMA table_info(analysis_history);" | grep -E "research_framework|bayesian_framework|supply_chain|value_scenarios|investment_conclusion"
```

应输出 5 行，每行对应一个新增字段。

### 5.2 检查 scheduled_task_log 表

```bash
sqlite3 data/stock_analysis.db ".tables" | grep scheduled_task_log
```

### 5.3 启动服务并触发一次分析

```bash
.venv/bin/python main.py --serve-only --host 0.0.0.0 --port 8000
```

然后调用分析接口：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H "Content-Type: application/json" \
  -d '{"stock_code":"000858","report_type":"brief","async_mode":true,"notify":false}'
```

等待任务完成后，查询状态接口：

```bash
curl -s "http://127.0.0.1:8000/api/v1/analysis/status/{task_id}"
```

确认 `result.diagnostic_summary.components.history.status` 为 `ok`。

### 5.4 查询历史记录

```bash
curl -s "http://127.0.0.1:8000/api/v1/history/stocks"
```

如果能看到刚才分析的股票记录，说明迁移成功。

---

## 6. Docker 部署如何迁移

### 6.1 进入容器

```bash
docker exec -it <container_name> /bin/bash
```

### 6.2 执行迁移

```bash
python scripts/migrate_analysis_history_20250625.py
```

### 6.3 使用 docker-compose 时

如果 `data` 目录通过 volume 挂载到宿主机，也可以在宿主机上直接运行：

```bash
cd /path/to/project
.venv/bin/python scripts/migrate_analysis_history_20250625.py
```

然后重启容器：

```bash
docker-compose restart
```

---

## 7. 回滚方案

如果迁移后出现问题，可以使用迁移前备份的数据库文件恢复：

```bash
# 停止服务
pkill -f "main.py"

# 恢复备份
cp data/stock_analysis.db.bak.YYYYMMDD_HHMMSS data/stock_analysis.db

# 重新启动服务
.venv/bin/python main.py --serve-only
```

> 回滚会丢失迁移后新产生的分析记录，请谨慎操作。

---

## 8. 常见问题

### Q1：执行迁移时提示数据库不存在

确认 `data/stock_analysis.db` 是否存在。如果通过 `DATABASE_PATH` 环境变量指定了其他路径，请设置该变量后再运行：

```bash
DATABASE_PATH=/custom/path/stock_analysis.db .venv/bin/python scripts/migrate_analysis_history_20250625.py
```

### Q2：是否可以跳过迁移直接删除数据库重建

可以，但会丢失所有历史记录。如果历史数据不重要，可以：

```bash
mv data/stock_analysis.db data/stock_analysis.db.old
```

下次启动服务时会自动创建新表。但不推荐在生产环境使用这种方式。

### Q3：迁移脚本能否在数据库被其他进程占用时执行

SQLite 会在执行 `ALTER TABLE` 时获取写锁。如果其他进程持有写锁，脚本会短暂等待；如果长时间被占用，可能会报 `database is locked`。建议迁移前停止相关服务。

### Q4：迁移后是否需要重启服务

是的。服务启动时会建立数据库连接和模型映射，迁移完成后需要重启服务才能生效。

---

## 9. 后续维护建议

1. **纳入升级流程**：每次拉取新代码后，若 `src/storage.py` 中模型有变化，先检查是否需要执行迁移脚本。
2. **考虑引入 Alembic**：如果项目表结构变更频繁，建议引入 Alembic 等正式迁移工具，替代手写脚本。
3. **CI 检测**：在 CI 中增加 schema 一致性检查，提前发现模型与数据库不匹配的问题。

---

## 10. 相关文档

- 端到端测试报告：`docs/e2e-stock-analysis-test-report.md`
- 定时任务方案：`docs/scheduled-watchlist-market-review-plan.md`
- 数据模型定义：`src/storage.py`
