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

## BDD 开发规范

本项目强制采用 **BDD（Behavior-Driven Development）** 驱动所有功能开发。

### 铁律：Feature 先行

任何新功能，必须严格遵循此顺序，禁止跳步：

```
① 写 Feature 文件（Gherkin，描述行为）
② 运行 pytest → RED（step 未找到，报错）
③ 写 step definitions + 最小实现代码
④ 运行 pytest → GREEN
⑤ Refactor（消除重复，提升优雅度）
```

**禁止**在没有对应 Feature scenario 的情况下写实现代码。

### Feature 文件规范

位置：`tests/features/{module}.feature`

```gherkin
Feature: {模块名} — {一句话职责描述}
  {背景说明：该模块的不变约束}

  Background:           ← 多 scenario 共享的前置条件
    Given ...

  Scenario: {具体行为名称}    ← 用业务语言，不用技术语言
    Given {初始状态}
    When  {触发动作}
    Then  {预期结果}
```

命名原则：
- Scenario 名称描述**业务行为**，不描述实现细节
- 用中文，贴近真实业务语境
- 每个 Scenario 只验证**一个行为**，不做多重断言

### Step Definitions 规范

位置：`tests/test_{module}.py`

```python
# 文件头部必须有 L3 契约注释

@scenario("features/{module}.feature", "{scenario 名称}")
def test_{snake_case}(): pass      # 空函数，仅注册

@given(parsers.parse("..."), target_fixture="{fixture_name}")
def given_xxx(...):
    return {...}                   # 返回状态容器 dict

@when(parsers.parse("..."), target_fixture="{fixture_name}")
def when_xxx(ctx, ...):
    ctx["result"] = ...
    return ctx                     # when 必须 return ctx

@then(parsers.parse("..."))
def then_xxx(ctx, ...):
    assert ...                     # then 不返回，只断言
```

关键约定：
- 每个模块用独立的 fixture 名（`ctx` / `ictx` / `mctx` / `tctx` / `actx` / `rctx` / `ectx`），**避免跨模块冲突**
- `target_fixture` 链式传递：Given → When → Then 共享同一 dict 对象
- 步骤文本中的引号要与 parsers.parse 模式**严格匹配**（`"{sym}"` vs `{sym}` 会导致 key 不一致）

### 运行命令

```bash
.venv/bin/pytest tests/ -v                  # 全量
.venv/bin/pytest tests/test_engine.py -v    # 单模块
.venv/bin/pytest tests/ -k "买入"           # 按关键词
.venv/bin/pytest tests/ --tb=short          # 简洁输出
```

### 新模块开发 checklist

- [ ] `tests/features/{module}.feature` — Gherkin 规格
- [ ] `src/agenticbt/{module}.py` — 实现（含 L3 头部注释）
- [ ] `tests/test_{module}.py` — step definitions（含 L3 头部注释）
- [ ] `src/agenticbt/CLAUDE.md` — 更新成员清单
- [ ] `tests/CLAUDE.md` — 更新成员清单
- [ ] `/CLAUDE.md` — 更新核心模块表

## 开发状态

MVP 完成：38/38 BDD scenarios 全绿
路线图：docs/roadmap.md

# currentDate
Today's date is 2026-02-25.
