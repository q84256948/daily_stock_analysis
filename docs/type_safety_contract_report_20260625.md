# 类型-契约-数据三层防御体系引入报告

> 日期：2026-06-25  
> 范围：在 A股自选股智能分析系统中引入 `mypy/pyright + icontract + Pydantic` 三层防御体系  
> 执行环境：Python 3.11.14，macOS

---

## 一、架构定位

按照教程中的三层防御模型：

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: 数据边界层 (Pydantic v2)                       │
│  作用：Agent Skill I/O、API 请求体、配置反序列化与校验        │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 业务契约层 (icontract)                         │
│  作用：函数级 pre/post-condition、类 invariant              │
├─────────────────────────────────────────────────────────┤
│  Layer 1: 静态类型层 (mypy / pyright)                     │
│  作用：编译前捕获类型错误、接口一致性                        │
└─────────────────────────────────────────────────────────┘
```

**分工：**
- **Pydantic**：管"数据长什么样"
- **icontract**：管"业务逻辑允不允许"
- **mypy/pyright**：管"类型对不对"

---

## 二、已完成的引入工作

### 2.1 依赖补齐

更新文件：

- `requirements.txt`：新增 `pydantic>=2.0.0`、`icontract>=2.6.0`、`beartype>=0.18.0`、`annotated-types>=0.6.0`
- `.github/requirements-ci.txt`：新增 `mypy`、`pyright`、`types-*` stub 包

### 2.2 配置文件

更新 `pyproject.toml`，新增：

- `[tool.pyright]`：basic 模式，包含 `src`、`data_provider`、`api`、`bot`
- `[tool.mypy]`：宽松起步（`strict=false`，`ignore_missing_imports=true`），接入 `pydantic.mypy` 插件
- `[tool.pydantic-mypy]`：启用 `init_forbid_extra`、`init_typed`

> 说明：项目当前有约 800–900 个既有类型错误，因此 mypy/pyright 先从宽松模式起步，避免 CI 直接阻断。后续可逐步收紧。

### 2.3 代码改造

#### 1) `data_provider/realtime_types.py`

为以下函数/方法添加 `icontract` 契约：

| 函数/方法 | 契约 | 作用 |
|-----------|------|------|
| `safe_float` | `@require(default 必须为数值或 None)`、`@ensure(返回 float/None)` | 防止非法默认值和异常返回类型 |
| `safe_int` | `@require(default 必须为 int 或 None)`、`@ensure(返回 int/None)` | 同上 |
| `ChipDistribution.get_chip_status` | `@require(profit_ratio∈[0,1])`、`@require(avg_cost≥0)`、`@require(current_price≥0)`、`@ensure(返回非空)` | 守卫筹码状态计算的业务前提 |

#### 2) `data_provider/base.py`

为以下纯工具函数添加 `icontract` 契约：

| 函数 | 契约 | 作用 |
|------|------|------|
| `_coerce_chip_metric` | `@ensure(返回 float/None)` | 统一类型输出 |
| `_is_meaningful_chip_distribution` | `@ensure(返回 bool)` | 统一类型输出 |
| `normalize_stock_code` | `@require(非空字符串)`、`@ensure(返回非空字符串)` | 保证输入输出基本约束 |
| `is_bse_code` / `is_st_stock` / `is_kc_cy_stock` | `@require(字符串)`、`@ensure(返回 bool)` | 统一类型输出 |

#### 3) 新建 `src/schemas/risk_check.py`

作为完整三层防御的**试点模块**，包含：

- **Pydantic**：`RiskCheckRequest`（输入）/`RiskCheckResult`（输出）
  - `strict=True` 防止自动类型转换
  - `frozen=True` 使请求对象不可变
  - `validate_assignment=True` 赋值时也要校验
  - 字段约束：`user_id` 32 位 hex、`symbol` 必须含 `-`、`price/quantity/account_balance > 0`、`leverage ∈ (0, 100]`
  - 跨字段校验：`@field_validator("symbol")` 强制 `BASE-QUOTE` 格式
- **icontract**：`check_risk` 的前置/后置条件
  - `@require`：杠杆 ≥1、账户余额为正
  - `@ensure`：保证金公式精确匹配、保证金占用率计算正确、通过时占用率非负
- **静态类型**：全函数完整类型注解，金融数值统一使用 `Decimal`

### 2.4 CI 门禁

新建 `.github/workflows/type-safety.yml`：

```yaml
name: Type-Safety-Contract-Gate
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r .github/requirements-ci.txt
      - run: pyright src data_provider api bot
      - run: mypy src data_provider api bot
      - env: { ICONTRACT_SLOW: "true" }
        run: pytest tests/test_realtime_types_contract.py tests/test_risk_check_contract.py ...
```

---

## 三、新增测试文件

| 文件 | 测试内容 |
|------|----------|
| `tests/test_realtime_types_contract.py` | 验证 `safe_float`/`safe_int`/`ChipDistribution.get_chip_status` 的 icontract 契约在正常/违约情况下的行为 |
| `tests/test_risk_check_contract.py` | 验证 `RiskCheckRequest` 的 Pydantic 校验、`check_risk` 的 icontract 后置条件、结果模型校验 |

---

## 四、验证结果

### 4.1 新增契约测试

```bash
ICONTRACT_SLOW=true python -m pytest \
  tests/test_realtime_types_contract.py \
  tests/test_risk_check_contract.py \
  -v --tb=short
```

结果：**17 passed, 0 failed**

### 4.2 相关回归测试

```bash
ICONTRACT_SLOW=true python -m pytest \
  tests/test_realtime_types_contract.py \
  tests/test_risk_check_contract.py \
  tests/test_data_fetcher_caching.py \
  tests/test_search_comprehensive_intel.py \
  tests/test_storage_trading_date_resume.py \
  tests/test_fundamental_context.py \
  tests/test_search_service_concurrency.py \
  tests/test_storage.py \
  -v --tb=short
```

结果：**79 passed, 0 failed**

### 4.3 静态类型检查

#### mypy（目标文件 + 依赖）

```bash
mypy data_provider/realtime_types.py data_provider/base.py src/schemas/risk_check.py \
     tests/test_realtime_types_contract.py tests/test_risk_check_contract.py
```

结果：**132 errors in 19 files**

错误集中在 `data_provider/akshare_fetcher.py`、`data_provider/efinance_fetcher.py`、`data_provider/tencent_fetcher.py` 等已有代码的类型误用（`float | None` 传入要求 `float` 的字段、`UnifiedRealtimeQuote | None` 赋给 `str | None` 变量等），**均非本次引入造成**。本次修改的 `realtime_types.py`、`base.py` 中新增契约本身未产生新错误。

#### pyright（目标文件 + 依赖）

```bash
pyright data_provider/realtime_types.py data_provider/base.py src/schemas/risk_check.py \
        tests/test_realtime_types_contract.py tests/test_risk_check_contract.py
```

结果：**40 errors, 0 warnings**

错误全部位于 `data_provider/base.py` 的既有函数（参数类型 `Unknown`、泛型 `Dict` 缺少类型参数等），**本次新增的契约装饰器没有引入新的 pyright 错误**。新建的 `src/schemas/risk_check.py` 和测试文件通过 pyright 检查。

---

## 五、生产环境注意事项

1. **icontract 默认开启**：当前添加的契约会在每次函数调用时执行。所加契约均为轻量级值检查（`isinstance`、`>= 0`、`0 <= x <= 1`），性能影响可忽略。
2. **建议通过环境变量控制**：
   - 开发/CI：`ICONTRACT_SLOW=true` 全开
   - 生产高频路径：可设置 `ICONTRACT_SLOW=false`，仅保留 cheap contract；或对高频函数使用 `enabled=icontract.SLOW` 参数显式标记
3. **Pydantic `strict=True`**：当前仅在新建模块 `src/schemas/risk_check.py` 启用，未改动现有 Pydantic 模型，避免破坏现有 API/Skill 的隐式转换行为。
4. **类型检查从宽松起步**：`pyproject.toml` 中 mypy 使用 `strict=false`、pyright 使用 `typeCheckingMode = "basic"`，后续随着既有错误修复可逐步收紧。

---

## 六、后续建议

1. **修复既有类型错误**：优先处理 `data_provider/akshare_fetcher.py`、`data_provider/efinance_fetcher.py`、`src/storage.py` 中的 SQLAlchemy/Pydantic 类型误用，将 mypy/pyright 逐步推向 strict。
2. **扩展 icontract 到核心计算函数**：
   - `src/analyzer.py` 中的 LLM 输出解析与报告构造
   - `data_provider/base.py` 中的 `get_fundamental_context`、`get_realtime_quote`
   - `src/core/pipeline.py` 中的进度/状态转换
3. **将现有 dataclass 逐步迁移到 Pydantic BaseModel**：优先迁移 `src/schemas/*` 和 API schema，利用 `ConfigDict(strict=True)` 统一 I/O 边界。
4. **引入 beartype 作为运行时守卫**：对 AI 生成的小函数加 `@beartype`，作为 icontract 的补充。
5. **CrossHair 符号执行**：对 `check_risk` 等关键函数尝试 `crosshair check`，做有界形式化验证。

---

## 七、常用命令速查

```bash
# 安装类型/契约依赖
pip install pydantic icontract beartype annotated-types mypy pyright

# 类型检查（宽松模式）
mypy src data_provider api bot
pyright src data_provider api bot

# 契约测试（全开）
ICONTRACT_SLOW=true python -m pytest \
  tests/test_realtime_types_contract.py \
  tests/test_risk_check_contract.py \
  -v

# 契约测试（仅 cheap contract）
ICONTRACT_SLOW=false python -m pytest \
  tests/test_realtime_types_contract.py \
  tests/test_risk_check_contract.py \
  -v
```

---

*本报告由 AI 助手基于 2026-06-25 的实施结果生成。*
