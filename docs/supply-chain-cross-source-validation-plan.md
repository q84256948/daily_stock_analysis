# 供应链报告双源校验方案

本文审计并完善供应链分析报告的数据源校验方案。范围限定为 A 股，目标是在不阻断报告生成的前提下，让供应链关键判断至少经过东方财富与同花顺两类来源的结构化校验。

## 目标

- 对供应链报告中的公司归属、板块/概念、上下游角色、候选标的关系做双源校验。
- 东方财富与同花顺至少作为两条独立校验链路；同花顺优先 iFinD，未配置 iFinD 时允许公开同花顺/AkShare best-effort。
- 校验失败不阻断报告生成，但报告必须显式标注 `待核验`、`单源支持` 或 `双源冲突`。
- 只支持 A 股。港股、美股和无法归一到 A 股 6 位代码的标的直接标记 `not_applicable`，不强行拼接数据。

## 现状审计

现有供应链报告主链路在 `src/services/supply_chain_report_service.py` 与 `src/agent/supply_chain_executor.py`，通过 Agent 调研生成 Markdown 报告。Prompt 已要求“两类来源交叉验证”，但缺少结构化工具和可测试的判定层，LLM 仍可能把单源搜索结果写成已确认事实。

仓库已有可复用能力：

- `data_provider/cross_source_validator.py`：估值、财务、资金流锚点的纯逻辑跨源校验。适合作为设计参考，但不直接扩展为供应链关系校验，避免把数值锚点和实体关系混在一起。
- `data_provider/ifind_fundamental_adapter.py`：同花顺 iFinD MCP 的连接、Markdown 表格解析、fail-open 模式。
- `src/services/alphasift_service.py`：已有东方财富板块、同花顺概念成分股、板块概况的抓取和容错逻辑。
- `src/agent/tools/supply_chain_tools.py`：供应链专属工具注册点，适合新增双源校验工具。

主要缺口：

- 供应链事实不是 PE/PB 这类数值字段，不能复用现有容差判定。
- 当前报告没有强制展示“东财证据 / 同花顺证据 / 双源状态”。
- 公开同花顺源可能失败或页面结构变化，需要清晰降级状态，而不是静默当作确认。

## 最小设计

新增一个供应链专用校验层，不改现有报告存储结构，不新增配置项。

建议新增：

- `data_provider/supply_chain/cross_source.py`
- `verify_supply_chain_evidence` 工具，注册到 `ALL_SUPPLY_CHAIN_TOOLS`
- 对 `src/agent/supply_chain_executor.py` 的 prompt 增加双源校验输出约束

不建议：

- 不把供应链关系塞进 `data_provider/cross_source_validator.py`。现有模块是数值锚点判定，混入实体关系会让接口语义变脏。
- 不新增数据库表。校验结果直接进入报告 Markdown 和 Agent 工具结果即可。
- 不新增开关。失败时标注待核验，用户可见且不影响主流程。

## 数据契约

### 输入

`verify_supply_chain_evidence` 工具输入：

```json
{
  "stock_code": "300750",
  "stock_name": "宁德时代",
  "claim": "宁德时代是动力电池产业链核心中游制造商",
  "board_hint": "动力电池",
  "topic": "新能源车电池供应链"
}
```

字段说明：

- `stock_code`：A 股 6 位代码，允许 `SH/SZ/BJ` 前缀或 `.SH/.SZ/.BJ` 后缀，内部归一为 6 位。
- `stock_name`：用于名称匹配和报告展示。
- `claim`：需要校验的供应链事实陈述。
- `board_hint`：可选，优先用于查找东财/同花顺板块或概念。
- `topic`：可选，用于无明确板块时构造搜索关键词。

### 输出

工具输出保持 LLM 易读但结构化：

```json
{
  "stock_code": "300750",
  "stock_name": "宁德时代",
  "scope": "a_share",
  "status": "confirmed",
  "confidence": "high",
  "eastmoney": {
    "available": true,
    "matched": true,
    "boards": ["动力电池", "宁德时代概念"],
    "constituents": ["300750"],
    "source": "eastmoney"
  },
  "ths": {
    "available": true,
    "matched": true,
    "boards": ["动力电池"],
    "constituents": ["300750"],
    "source": "ifind|ths_public|akshare_ths"
  },
  "overlap": {
    "constituent_overlap_ratio": 0.42,
    "matched_by": ["code", "board_name"]
  },
  "note": "东方财富和同花顺均支持该公司属于动力电池相关板块"
}
```

状态枚举：

- `confirmed`：东财与同花顺均支持。
- `partial`：只有一源支持，另一源不可用或未命中。
- `conflict`：两源结论明显冲突，或板块成分股重合极低且目标公司归属相反。
- `unverified`：两源都不可用或都无可靠命中。
- `not_applicable`：非 A 股或无法归一到 A 股代码。

置信度枚举：

- `high`：双源命中，且代码/名称/板块至少两个维度一致。
- `medium`：单源命中，或双源板块近似但证据不完整。
- `low`：冲突、双源缺失、非适用范围。

## 数据源策略

### 东方财富链路

优先复用已有东财能力：

1. 东财概念/行业板块列表。
2. 东财概念/行业板块成分股。
3. 东财板块异动摘要，仅作为辅助证据，不作为归属确认的唯一依据。

建议实现上复用 `DsaEastMoneyHotspotProvider` 中已经存在的成分股、板块名称和缓存思路；如果直接 import 会造成服务层耦合过重，则抽出最小公共函数到 `data_provider/supply_chain/cross_source.py` 内部实现。

### 同花顺链路

顺序：

1. iFinD MCP 可用时优先使用，来源标记 `ifind`。
2. iFinD 不可用时，走公开同花顺/AkShare best-effort：
   - 同花顺概念列表
   - 同花顺概念成分股
   - 同花顺板块概况/驱动事件
3. 公开源失败时不抛异常，返回 `available=false` 和错误摘要。

公开源只能作为 best-effort，不应把一次抓取失败升级为“否定”。失败语义是“未核验”，不是“不存在”。

## 判定规则

先做代码归一：

- 只接受 A 股 6 位代码。
- `600/601/603/605/688` 默认沪市，`000/001/002/003/300/301` 默认深市，`8/4/9` 视情况北交所。
- 非 A 股返回 `not_applicable`。

匹配优先级：

1. 股票代码一致：强匹配。
2. 股票名称标准化后一致：强匹配。
3. 板块名完全一致：强匹配。
4. 板块名包含或同义词近似：中匹配。
5. 成分股集合重合度：辅助判断。

成分股重合度：

- `>= 30%`：两个板块大概率同一主题，提升置信度。
- `10%-30%`：主题相关但口径不同，维持中置信。
- `< 10%`：疑似不同口径，若目标公司只在一边出现则 `partial`，若两边给出相反归属则 `conflict`。

状态决策：

| 条件 | status | confidence |
| --- | --- | --- |
| 非 A 股 | `not_applicable` | `low` |
| 东财和同花顺均命中目标公司 | `confirmed` | `high` |
| 东财和同花顺均可用，但目标公司归属相反 | `conflict` | `low` |
| 仅东财命中 | `partial` | `medium` |
| 仅同花顺命中 | `partial` | `medium` |
| 两源均不可用或无命中 | `unverified` | `low` |

## 报告输出约束

供应链报告最终表格必须包含双源校验结果。建议表格字段：

```text
标的 | 卡住的环节 | 瓶颈分 | 东财校验 | 同花顺校验 | 双源状态 | 关键证据 | 主要风险
```

文案规则：

- `confirmed` 才能写“东财与同花顺均确认”。
- `partial` 只能写“单源支持，待另一源核验”。
- `conflict` 必须写明“东财/同花顺口径冲突”，不得继续作为强证据排序。
- `unverified` 必须写“待核验”，不得写“确认”“坐实”“实锤”。
- `not_applicable` 写“A 股双源校验不适用”，但本阶段范围限定 A 股，正常不应进入最终候选表。

## Prompt 修改要点

在供应链 system prompt 中补充：

- A 股候选标的进入最终候选表前，必须调用 `verify_supply_chain_evidence`。
- 用户提供线索且涉及 A 股公司/板块时，必须对线索中的公司或板块调用该工具。
- 未得到 `confirmed` 的结论不得写成已确认事实。
- 最终报告必须展示双源状态；工具不可用时展示 `待核验`，而不是省略。

## 实施步骤

1. 新增 `data_provider/supply_chain/cross_source.py`
   - 纯函数：代码归一、名称标准化、板块近似、成分股重合度、状态判定。
   - IO 函数：东财读取、同花顺读取，全部 fail-open。

2. 新增 `verify_supply_chain_evidence`
   - 放在 `src/agent/tools/supply_chain_tools.py`。
   - 只注册给供应链 executor，不污染问股/郑希/排雷工具集。

3. 更新 `src/agent/supply_chain_executor.py`
   - 补双源校验规则。
   - 补最终报告表格字段要求。

4. 更新 `docs/supply-chain-research.md`
   - 加“双源校验”能力说明和边界。

5. 更新测试
   - 新增 `tests/test_supply_chain_cross_source_validation.py`。
   - 更新 `tests/test_supply_chain_services.py` 工具注册断言。
   - 更新供应链 prompt 测试，确保包含双源校验约束。

## 测试矩阵

后端纯逻辑：

- A 股代码归一成功。
- 非 A 股返回 `not_applicable`。
- 东财 + 同花顺都命中返回 `confirmed/high`。
- 只有东财命中返回 `partial/medium`。
- 只有同花顺命中返回 `partial/medium`。
- 两源都失败返回 `unverified/low`。
- 两源口径冲突返回 `conflict/low`。
- 成分股重合度阈值正确。
- 单源异常不影响另一源。

工具层：

- `verify_supply_chain_evidence` 注册成功。
- 工具输出包含 `eastmoney`、`ths`、`status`、`confidence`、`note`。
- 无 iFinD 时可走公开同花顺/AkShare best-effort。

Prompt 层：

- system prompt 包含“东方财富”“同花顺”“双源校验”“待核验”。
- 最终报告契约包含“双源状态”。

推荐验证命令：

```bash
python -m pytest tests/test_supply_chain_cross_source_validation.py tests/test_supply_chain_services.py -v
python -m py_compile data_provider/supply_chain/cross_source.py src/agent/tools/supply_chain_tools.py src/agent/supply_chain_executor.py
```

## 风险与降级

- 同花顺公开网页结构可能变化：降级为 `partial` 或 `unverified`，报告继续生成。
- 东财和同花顺板块口径不同：用重合度和状态说明，不强行统一。
- iFinD 自然语言查询可能返回 Markdown 口径漂移：解析失败不抛出，保留 `source_error`。
- 搜索型线索与板块归属不是同一证据：`search_clue_hype` 只能证明“被提及”，`verify_supply_chain_evidence` 才证明“板块/公司归属支持”，报告中不能混用。

## 回滚方式

- 从 `ALL_SUPPLY_CHAIN_TOOLS` 移除 `verify_supply_chain_evidence`。
- 回退 `src/agent/supply_chain_executor.py` 的 prompt 修改。
- 保留新增 provider 文件不会影响运行；如需彻底回滚，删除 `data_provider/supply_chain/cross_source.py` 与对应测试。

## 最终结论

优化后的方案采用“新增供应链专用双源校验工具”的最小路径：复用现有东财/同花顺接入能力，不改报告存储，不阻断报告生成，通过结构化状态约束让报告不能把单源线索写成双源确认。下一步实现时，应先完成纯逻辑判定和离线测试，再接真实数据源 IO。
