# AgenticBT - Agent 时代的量化回测框架
Python 3.10+ · openai · pandas · pandas-ta · pytest-bdd

> "Backtest the Trader, Not Just the Strategy."
> 回测交易员，而不仅仅是策略。

## 架构哲学

Agent 说意图，Framework 说真相。LLM Agent 像人类交易员一样思考和决策，确定性引擎负责数据、计算和执行。

## 目录结构

```
docs/          - 设计文档 (9 篇，指导全部开发)
src/
  agenticbt/   - 9 个业务文件
tests/
  features/    - 7 个 Gherkin feature 文件（可执行规格说明）
  test_*.py    - BDD step definitions（38 个 scenarios）
pyproject.toml - Python 包配置（venv: .venv/）
```

<directory>
docs/ - 完整设计文档集 (9 文件: architecture, engine, tools, memory, context, eval, agent-protocol, runner, roadmap)
src/agenticbt/ - 核心业务代码 (9 文件: __init__, models, engine, indicators, memory, tools, agent, runner, eval)
tests/ - BDD 测试 (14 文件: 7 features + 7 step definitions)
</directory>

## 核心模块

| 模块 | 职责 | 设计文档 |
|------|------|---------|
| engine.py | 确定性市场模拟：数据回放、订单撮合、仓位核算、风控拦截 | docs/engine.md |
| indicators.py | pandas-ta 防前瞻包装，calc(name, df, bar_index) | - |
| memory.py | 文件式记忆：Workspace 隔离 + log/note/recall | docs/memory.md |
| tools.py | ToolKit：OpenAI function calling schema + 分发 + 调用追踪 | docs/tools.md |
| agent.py | LLMAgent：ReAct loop（OpenAI SDK 兼容），AgentProtocol | docs/agent-protocol.md |
| runner.py | Runner 主循环 + ContextManager 六层上下文组装 | docs/runner.md |
| eval.py | Evaluator：绩效指标 + 遵循度报告 | docs/eval.md |

## 快速开始

```bash
# 安装
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 全量测试（38 个 BDD scenarios）
.venv/bin/pytest tests/ -v

# 端到端（需要 API key）
OPENAI_API_KEY=sk-... .venv/bin/python -c "
from agenticbt import run, BacktestConfig
import pandas as pd
result = run(BacktestConfig(
    data=pd.read_csv('AAPL.csv', index_col='date', parse_dates=True),
    symbol='AAPL',
    strategy_prompt='RSI < 30 买入, RSI > 70 卖出',
    model='claude-sonnet-4-20250514',
    base_url='https://api.anthropic.com/v1/',
))
print(result.performance)
"
```

## LLM 提供商切换（零代码变更）

- Claude: `base_url="https://api.anthropic.com/v1/"`
- GPT: `base_url=None`（默认 OpenAI）
- Ollama: `base_url="http://localhost:11434/v1/"`

## 开发状态

MVP 完成：38/38 BDD scenarios 全绿
路线图：docs/roadmap.md

# currentDate
Today's date is 2026-02-25.
