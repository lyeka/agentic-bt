# AgenticBT

> **Backtest the Trader, Not Just the Strategy.**
> 回测交易员，而不仅仅是策略。

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![BDD Tests](https://img.shields.io/badge/BDD%20tests-38%20scenarios-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

传统回测框架测试**信号规则**。AgenticBT 测试**一个 AI 交易员**——

它会使用工具查询行情、计算指标、执行订单、记录决策，就像一位实习分析师。你给它历史数据和策略描述，它用 LLM 推理做出每一个交易决策。框架记录整个过程，评估绩效与策略遵循度。

**换一个模型，就换了一位交易员。** 换一段 prompt，就换了一套策略。

---

## 特性

- **一行启动**：`run(BacktestConfig(...))` 驱动完整回测
- **Provider 无关**：`base_url` 参数切换 Claude / GPT / Ollama，代码零改动
- **确定性引擎**：数据回放、订单撮合、仓位核算、风控拦截——全部可重现
- **5 工具生态**：market · indicator · account · trade · memory，Agent 通过工具感知和行动
- **双维度评估**：绩效指标（收益率/夏普/胜率）× 策略遵循度（工具使用/行为分布）
- **BDD 驱动**：38 个 Gherkin scenarios，既是测试套件，也是模块规格说明
- **无 API key 即可运行**：`--mock` 模式用规则 Agent 验证完整回测链路

---

## 架构

```
┌────────────────────────────────────────────────────────────┐
│                         Runner                             │
│                                                            │
│  ┌──────────┐   ┌──────────────────┐   ┌──────────────┐   │
│  │  Engine  │──▶│  ContextManager  │──▶│   LLMAgent   │   │
│  │ (确定性) │   │  (六层上下文)    │   │ (ReAct Loop) │   │
│  └──────────┘   └──────────────────┘   └──────┬───────┘   │
│       ▲                                        │           │
│       │               ToolKit ◀────────────────┘           │
│       │          ┌──────────────────────┐                  │
│       └──────────│ market   indicator   │                  │
│                  │ account  trade       │                  │
│                  │ memory               │                  │
│                  └──────────────────────┘                  │
│  ┌──────────┐                            ┌─────────────┐   │
│  │  Memory  │                            │  Evaluator  │   │
│  │ (文件式) │                            │ 绩效 + 遵循 │   │
│  └──────────┘                            └─────────────┘   │
└────────────────────────────────────────────────────────────┘
```

**分工原则**：Agent 说意图，Engine 说真相。LLM 负责推理和决策，引擎负责数据、计算和执行。

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/agentic-bt.git
cd agentic-bt
pip install -e ".[dev]"
```

### Mock 模式（无需 API key，立即验证）

```bash
python demo.py --mock
```

输出完整的回测报告：绩效指标、遵循度统计、决策日志样本。

### 真实 LLM — Claude（推荐）

```bash
ANTHROPIC_API_KEY=sk-ant-... python demo.py --provider claude
```

### 切换其他 Provider

```bash
# GPT-4o
OPENAI_API_KEY=sk-... python demo.py --provider openai

# 本地 Ollama（无需 key）
python demo.py --provider ollama --model qwen2.5:7b

# 自定义 bar 数量和标的
python demo.py --mock --symbol TSLA --bars 120

# 加载本地 CSV
python demo.py --mock --csv AAPL_sample.csv
```

---

## Python API

### 一行回测

```python
from agenticbt import run, BacktestConfig, make_sample_data

df = make_sample_data("AAPL", periods=252)

result = run(BacktestConfig(
    data=df,
    symbol="AAPL",
    strategy_prompt="RSI < 35 时买入，RSI > 65 时平仓，每次必须先 market_observe 再 indicator_calc",
    model="claude-sonnet-4-20250514",
    base_url="https://api.anthropic.com/v1/",
    api_key="sk-ant-...",
))

p = result.performance
print(f"总收益率  {p.total_return:+.2%}")
print(f"最大回撤  {p.max_drawdown:.2%}")
print(f"夏普比率  {p.sharpe_ratio:.3f}")
print(f"胜率      {p.win_rate:.1%}  ({p.total_trades} 笔)")
print(f"工作空间  {result.workspace_path}")
```

### 加载真实 CSV

```python
from agenticbt import load_csv

# 兼容 Yahoo Finance / AKShare / Tushare 等常见格式
df = load_csv("path/to/AAPL.csv")
```

### 自定义 Agent

只需实现 `decide(context, toolkit) -> Decision`：

```python
from agenticbt.models import Decision
from agenticbt.tools import ToolKit

class MyRuleAgent:
    def decide(self, context: dict, toolkit: ToolKit) -> Decision:
        market = toolkit.execute("market_observe", {})
        rsi    = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14})

        action, symbol, qty = "hold", None, None
        if rsi.get("value", 50) < 35 and not context["account"]["positions"]:
            qty    = int(context["account"]["cash"] * 0.9 / market["close"])
            action = "buy"
            symbol = context["market"]["symbol"]
            toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})

        return Decision(
            datetime=context["datetime"],
            bar_index=context["bar_index"],
            action=action, symbol=symbol, quantity=qty,
            reasoning=f"RSI={rsi.get('value'):.1f}",
            market_snapshot=context["market"],
            account_snapshot=context["account"],
            indicators_used={"RSI": rsi.get("value")},
            tool_calls=list(toolkit.call_log),
        )

result = run(BacktestConfig(data=df, symbol="AAPL", strategy_prompt=""), agent=MyRuleAgent())
```

---

## LLM Provider 切换

一个 `openai` SDK，`base_url` 覆盖所有提供商：

| Provider | `base_url` | `api_key` |
|----------|-----------|-----------|
| Claude (Anthropic) | `"https://api.anthropic.com/v1/"` | `ANTHROPIC_API_KEY` |
| OpenAI GPT | `None`（默认） | `OPENAI_API_KEY` |
| Ollama（本地） | `"http://localhost:11434/v1/"` | `"ollama"` |
| OpenRouter | `"https://openrouter.ai/api/v1/"` | OpenRouter key |
| 任意 OpenAI 兼容端点 | 自定义 URL | 对应 key |

```python
# 换 Provider = 改两个参数，零代码变更
config = BacktestConfig(
    ...,
    model="gpt-4o-mini",
    base_url=None,          # OpenAI 默认
    api_key="sk-...",
)
```

---

## 5 个核心工具

Agent 通过工具与世界交互，所有调用均被记录在 `Decision.tool_calls`：

| 工具 | 参数示例 | 返回 |
|------|---------|------|
| `market_observe` | `{}` | `{open, high, low, close, volume, datetime}` |
| `indicator_calc` | `{"name": "RSI", "period": 14}` | `{"value": 32.5}` |
| `indicator_calc` | `{"name": "MACD"}` | `{"macd": ..., "signal": ..., "histogram": ...}` |
| `account_status` | `{}` | `{cash, equity, positions: {symbol: {qty, avg_price}}}` |
| `trade_execute` | `{"action": "buy", "symbol": "AAPL", "quantity": 100}` | `{"status": "submitted"}` |
| `memory_log` | `{"content": "RSI 超卖，买入 AAPL"}` | `{"ok": true}` |
| `memory_note` | `{"key": "thesis", "content": "均值回归"}` | `{"ok": true}` |
| `memory_recall` | `{"query": "上次买入"}` | `{"results": [...]}` |

支持的技术指标：**RSI · SMA · EMA · ATR · MACD · BBANDS**

---

## 模块参考

| 模块 | 职责 |
|------|------|
| `models.py` | 所有 dataclass：Bar · Order · Fill · Position · Decision · BacktestConfig · ... |
| `engine.py` | 确定性市场模拟：数据回放 / 订单撮合（下一 bar 开盘价成交）/ 风控 |
| `indicators.py` | pandas-ta 包装，防前瞻（严格切片 `df[:bar+1]`） |
| `memory.py` | 文件式记忆：每次回测独立 workspace，journal / notes / recall |
| `tools.py` | OpenAI function calling schema + 工具分发 + 调用追踪 |
| `agent.py` | `LLMAgent`（ReAct loop，max_rounds 保护）+ `AgentProtocol`（鸭子类型） |
| `runner.py` | 主循环：advance → match → assemble_context → decide → record |
| `eval.py` | `Evaluator`：绩效（真实 PnL）+ 遵循度（行为分布 / 工具使用率） |
| `data.py` | `load_csv`（多格式兼容）+ `make_sample_data`（几何布朗运动） |

---

## 开发

### 运行测试

```bash
# 全部 BDD scenarios（38 个）
pytest tests/ -v

# 单模块
pytest tests/ -v -k "engine"
pytest tests/ -v -k "agent"

# 简洁输出
pytest tests/ --tb=short -q
```

### BDD 驱动开发循环

```
① 在 tests/features/<module>.feature 写 Gherkin 场景  →  RED
② 在 tests/test_<module>.py 实现 step definitions
③ 在 src/agenticbt/<module>.py 实现业务代码            →  GREEN
④ pytest 全通，提交
```

Feature 文件是活的规格说明——读 `.feature` 即读模块行为契约，无需查源码。

---

## 项目结构

```
agentic-bt/
├── demo.py                  # CLI 端到端演示（mock + 真实 LLM）
├── AAPL_sample.csv          # 252 根模拟 bar，开箱即用
├── pyproject.toml           # 依赖: openai + pandas + pandas-ta
├── src/
│   └── agenticbt/
│       ├── __init__.py      # 公共 API: run / BacktestConfig / LLMAgent / load_csv
│       ├── models.py        # 数据结构基础层
│       ├── engine.py        # 确定性市场模拟
│       ├── indicators.py    # 技术指标（防前瞻）
│       ├── memory.py        # 文件式记忆
│       ├── tools.py         # 工具 schema + 分发
│       ├── agent.py         # LLMAgent ReAct loop
│       ├── runner.py        # 回测主循环
│       ├── eval.py          # 评估系统
│       └── data.py          # 数据加载 + 生成
├── tests/
│   ├── features/            # 7 个 Gherkin feature 文件
│   │   ├── engine.feature
│   │   ├── indicators.feature
│   │   ├── memory.feature
│   │   ├── tools.feature
│   │   ├── agent.feature
│   │   ├── runner.feature
│   │   └── eval.feature
│   ├── test_engine.py
│   ├── test_indicators.py
│   ├── test_memory.py
│   ├── test_tools.py
│   ├── test_agent.py
│   ├── test_runner.py
│   └── test_eval.py
└── docs/                    # 9 篇设计文档（架构 / 引擎 / 工具 / 记忆 / ...)
```

---

## 路线图

| 版本 | 状态 | 亮点 |
|------|------|------|
| **V1 MVP** | ✅ 完成 | 单资产 · 市价单 · RSI 策略 · 38 BDD tests · mock + 真实 LLM |
| **V2** | 计划中 | 多资产 · 限价/止损单 · 矩阵对比实验 · OpenRouter 集成 |
| **V3** | 未来 | 指标缓存 · 向量召回记忆 · MCP 工具扩展 · Web 回测 UI |

---

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `openai` | `>=1.0` | OpenAI 兼容 SDK，覆盖所有 LLM Provider |
| `pandas` | `>=2.0` | OHLCV 数据容器 |
| `pandas-ta` | latest | 130+ 技术指标 |
| `pytest` / `pytest-bdd` | dev | BDD 测试框架 |

Python 3.10+

---

## License

MIT © 2024
