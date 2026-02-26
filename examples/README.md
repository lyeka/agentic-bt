# AgenticBT 策略系统

> Backtest the Trader, Not Just the Strategy.

7 种策略展示 AI Agent 的认知能力和框架全能力。5 个带 Mock Agent（确定性验证，无需 API key），2 个 LLM-only（AI 自由发挥）。

## 快速开始

```bash
# 单策略 mock 运行
python demo.py --mock --strategy rsi
python demo.py --mock --strategy bracket_atr

# 全量 mock 对比
python demo.py --mock --strategy all

# LLM 真实回测
ANTHROPIC_API_KEY=sk-ant-... python demo.py --strategy free_play

# 自动化 E2E 测试
.venv/bin/pytest tests/test_e2e_strategies.py -v
```

## 策略一览

| 策略 | 类型 | 框架能力覆盖 | 行情模式 | bars |
|------|------|-------------|---------|------|
| `rsi` | Mock+LLM | 市价单、单指标、memory_log | mean_reverting | 60 |
| `bracket_atr` | Mock+LLM | Bracket 订单、多指标融合(SMA+ATR)、动态止损止盈 | trending | 80 |
| `bollinger_limit` | Mock+LLM | 限价单、order_query/cancel、valid_bars 有效期 | volatile | 80 |
| `adaptive_memory` | Mock+LLM | memory_note/recall 全链路、自适应仓位 | mean_reverting | 100 |
| `multi_asset` | Mock+LLM | 多资产数据、跨资产对比、风控配置 | bull_bear | 80 |
| `free_play` | LLM-only | 全工具链自由探索，AI 涌现行为 | random | 60 |
| `reflective` | LLM-only | 记忆系统深度使用，自我反思进化 | random | 80 |

## 架构设计

### 三位一体：Mock + Prompt + Data

每个策略由三个维度定义，统一注册在 `StrategyDef` 数据类中：

```
┌─────────────────────────────────────────────┐
│              StrategyDef                     │
│                                             │
│  mock_cls ──→ 确定性 Mock Agent（E2E 验证） │
│  llm_prompt ──→ LLM 策略提示词（真实回测）  │
│  regime/seed/bars ──→ 匹配行情数据          │
│                                             │
│  --mock 时用 mock_cls                       │
│  非 --mock 时用 llm_prompt + LLMAgent       │
└─────────────────────────────────────────────┘
```

### 行情模式（regime）

`make_sample_data(regime=...)` 控制模拟数据的统计特征：

| regime | 漂移(μ) | 波动(σ) | 适用场景 |
|--------|---------|---------|---------|
| `random` | 0.0003 | 0.015 | 通用默认，随机漫步 |
| `trending` | 0.002 | 0.01 | 均线策略，需要明确趋势 |
| `mean_reverting` | 0.0 | 0.02 | RSI 策略，需要震荡产生超买超卖 |
| `volatile` | 0.0 | 0.03 | 布林带策略，需要频繁触及上下轨 |
| `bull_bear` | 分段 | 分段 | 多资产/自由策略，前半牛后半熊 |

### 文件结构

```
examples/
  __init__.py
  strategies.py      ← 策略注册表 + Mock Agent 类 + LLM Prompt
  README.md          ← 本文件

demo.py              ← CLI 入口，--strategy 选择策略
tests/
  test_e2e_strategies.py  ← 参数化 E2E 自动化测试
  features/data.feature   ← 数据生成 BDD 规格
  test_data.py            ← 数据生成 step definitions
```

## 策略详解

### 1. `rsi` — RSI 均值回归

最基础的策略，验证核心工具链。

- 信号：RSI(14) < 50 买入，> 55 卖出
- 工具：`market_observe` → `indicator_calc(RSI)` → `account_status` → `trade_execute` → `memory_log`
- 数据：`mean_reverting`（零漂移高波动，RSI 信号频繁）
- `decision_start_bar`: 14（RSI 预热期）

### 2. `bracket_atr` — 均线交叉 + Bracket 动态风控

展示 Bracket 订单和多指标融合。

- 信号：SMA(10)/SMA(30) 金叉买入，死叉平仓
- 风控：每笔交易自动带 Bracket 保护
  - `stop_loss = close - 2 × ATR(14)`
  - `take_profit = close + 3 × ATR(14)`
- 数据：`trending`（强趋势低波动，均线信号清晰）
- `decision_start_bar`: 30（SMA30 预热期）

### 3. `bollinger_limit` — 布林带 + 限价单生命周期

展示限价单和挂单管理全流程。

- 信号：下轨附近挂限价买单，上轨平仓
- 挂单管理：
  - `valid_bars=3`（3 根 bar 后自动过期）
  - 每轮用 `order_query` 检查 → `order_cancel` 清理
- 数据：`volatile`（极高波动，布林带频繁触及）
- `decision_start_bar`: 20（BBANDS(20) 预热期）

### 4. `adaptive_memory` — 记忆驱动自适应

展示 memory 系统全链路和自适应行为。

- 信号：RSI(14) < 45 买入，> 55 卖出（基础信号）
- 自适应：
  - 每次决策前 `memory_recall("performance")` 读取历史胜率
  - 胜率 > 50% → 正常仓位(90%)；≤ 50% → 减半仓位(45%)
  - 每次交易后 `memory_note("performance", ...)` 更新胜率
- 数据：`mean_reverting`，bars=100（需要足够交易产生学习数据）

### 5. `multi_asset` — 多资产轮动

展示多资产数据和风控配置。

- 信号：比较 AAPL/GOOGL 的 RSI，持有最超卖的资产
- 轮动：当持有资产不再最超卖时，平仓换入更超卖的
- 风控：`max_position_pct=0.45`, `max_open_positions=2`
- 数据：`bull_bear`，两资产不同 seed 产生差异化走势

### 6. `free_play` — AI 自由交易员 (LLM-only)

无预设规则，全工具链开放，展示 AI 涌现行为。

- `--mock` 时跳过，提示需要 LLM
- AI 自主决定观察什么、用什么指标、何时交易、如何管理风险

### 7. `reflective` — 反思型交易员 (LLM-only)

展示记忆系统深度使用和自我反思能力。

- 每次决策前回顾历史，分析对错
- 每次交易后记录反思笔记
- 交易风格随经验积累进化

## 新增策略指南

### 第一步：定义策略身份

在 `examples/strategies.py` 中确定三个问题：

1. 这个策略要展示框架的什么能力？（对应 `features`）
2. 需要什么样的行情数据？（对应 `regime`）
3. 是否需要 Mock Agent？（有 mock 才能自动化测试）

### 第二步：写 Mock Agent（如果需要）

Mock Agent 是一个实现了 `decide(context, toolkit) -> Decision` 方法的类：

```python
class MyMockAgent:
    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        # 1. 通过 toolkit.execute() 调用工具获取数据
        market = toolkit.execute("market_observe", {})
        rsi = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14})

        # 2. 决策逻辑
        action, symbol, qty, reasoning = "hold", None, None, "观望"

        # 3. 通过 toolkit.execute("trade_execute", ...) 执行交易

        # 4. 返回 Decision
        return Decision(
            datetime=context.datetime,
            bar_index=context.bar_index,
            action=action,
            symbol=symbol,
            quantity=qty,
            reasoning=reasoning,
            market_snapshot=context.market,
            account_snapshot=context.account,
            indicators_used={"RSI": rsi.get("value")},
            tool_calls=list(toolkit.call_log),
        )
```

可用工具一览：

| 工具 | 用途 | 参数 |
|------|------|------|
| `market_observe` | 当前 bar 行情 | `{symbol?}` |
| `market_history` | 最近 N 根 K 线 | `{bars, symbol?}` |
| `indicator_calc` | 技术指标 | `{name, period?, symbol?}` |
| `account_status` | 账户持仓 | `{}` |
| `trade_execute` | 执行交易 | `{action, symbol?, quantity?, order_type?, price?, valid_bars?, stop_loss?, take_profit?}` |
| `memory_log` | 追加日志 | `{content}` |
| `memory_note` | 创建/更新笔记 | `{key, content}` |
| `memory_recall` | 检索记忆 | `{query}` |
| `order_query` | 查询挂单 | `{}` |
| `order_cancel` | 取消挂单 | `{order_id}` |

可用指标：`RSI`, `SMA`, `EMA`, `ATR`, `MACD`, `BBANDS`

### 第三步：写 LLM Prompt

用自然语言描述策略规则，LLM 会通过 function calling 自动调用工具执行：

```python
_PROMPT_MY_STRATEGY = (
    "你是一位...交易员。\n"
    "规则：\n"
    "1. ...\n"
    "2. ...\n"
)
```

### 第四步：注册到 STRATEGIES

```python
STRATEGIES["my_strategy"] = StrategyDef(
    name="my_strategy",
    description="一句话描述",
    mock_cls=MyMockAgent,       # 或 None（LLM-only）
    llm_prompt=_PROMPT_MY_STRATEGY,
    regime="mean_reverting",    # 选择匹配的行情模式
    seed=500,                   # 唯一 seed，避免与其他策略冲突
    bars=80,
    decision_start_bar=14,      # 指标预热期
    features=["你的策略覆盖的框架能力"],
)
```

`StrategyDef` 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 策略唯一标识，用于 `--strategy` 参数 |
| `description` | str | 一句话描述 |
| `mock_cls` | type \| None | Mock Agent 类，None 表示 LLM-only |
| `llm_prompt` | str | LLM 策略提示词 |
| `regime` | str | 行情模式 |
| `seed` | int | 随机种子（确保可复现） |
| `bars` | int | 默认 bar 数量 |
| `decision_start_bar` | int | 指标预热跳过的 bar 数 |
| `symbol` | str | 主资产代码，默认 "AAPL" |
| `risk` | RiskConfig | 风控配置，默认宽松 |
| `features` | list[str] | 覆盖的框架能力标签 |
| `extra_symbols` | list[(str,int)] \| None | 多资产时的额外 symbol 和 seed |

### 第五步：验证

```bash
# Mock 运行
python demo.py --mock --strategy my_strategy

# E2E 测试（有 mock_cls 的策略自动被参数化测试覆盖）
.venv/bin/pytest tests/test_e2e_strategies.py -v

# 全量回归
.venv/bin/pytest tests/ -v
```

注册到 `STRATEGIES` 后，E2E 测试会自动发现并参数化测试你的新策略（前提是 `mock_cls` 不为 None）。无需手动修改测试文件。

## E2E 测试说明

`tests/test_e2e_strategies.py` 提供两类参数化测试：

### `test_mock_strategy_e2e[{name}]`

自动遍历 `STRATEGIES` 中所有 `mock_cls is not None` 的策略，每个跑完整回测并断言：

- `result.decisions` 非空（Agent 产生了决策）
- `performance.total_return` 在 [-100%, +1000%] 范围内
- `performance.max_drawdown` 在 [0%, 100%] 范围内
- `compliance.total_decisions` 与 decisions 列表长度一致

### `test_llm_only_strategy_has_no_mock[{name}]`

验证 LLM-only 策略的元数据完整性：`mock_cls is None` 且 `llm_prompt` 非空。

### 自动发现机制

测试通过动态读取 `STRATEGIES` 注册表生成参数化用例：

```python
MOCK_STRATEGIES = [
    (name, strat)
    for name, strat in STRATEGIES.items()
    if strat.mock_cls is not None
]
```

新增策略只要注册到 `STRATEGIES`，测试自动覆盖，零配置。

## CLI 参数

```
python demo.py [OPTIONS]

--strategy {rsi,bracket_atr,bollinger_limit,adaptive_memory,multi_asset,free_play,reflective,all}
    选择策略，默认 rsi。all 运行全部并输出对比表。

--mock
    使用 Mock Agent（无需 API key）。LLM-only 策略会被跳过。

--provider {claude,openai,ollama}
    LLM 提供商，默认 claude。

--model MODEL
    覆盖默认模型名称。

--csv PATH
    自定义 CSV 数据（覆盖策略默认的模拟数据）。

--bars N
    覆盖策略默认的 bar 数量。
```
