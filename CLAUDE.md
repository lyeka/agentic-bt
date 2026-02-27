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
  agenticbt/   - 12 个业务文件
examples/      - 策略注册表 + Mock Agent + LLM Prompt（8 策略）
tests/
  features/    - 10 个 Gherkin feature 文件（可执行规格说明）
  test_*.py    - BDD step definitions + E2E 策略测试
pyproject.toml - Python 包配置（venv: .venv/）
```

<directory>
docs/ - 完整设计文档集 (11 文件: architecture, engine, tools, compute, memory, context, eval, agent-protocol, runner, tracer, roadmap)
src/agenticbt/ - 核心业务代码 (13 文件: __init__, models, engine, indicators, memory, tools, sandbox, context, agent, runner, eval, data, tracer)
examples/ - 策略模块 (2 文件: __init__, strategies)
tests/ - BDD 测试 + E2E (25 文件: 11 features + 12 step definitions + 1 e2e)
</directory>

## 核心模块

| 模块 | 职责 | 设计文档 |
|------|------|---------|
| engine.py | 确定性市场模拟：数据回放、订单撮合、仓位核算、风控拦截 | docs/engine.md |
| indicators.py | pandas-ta 防前瞻包装，calc(name, df, bar_index) | - |
| engine.py | 确定性市场模拟：多资产数据/market+limit+stop+bracket 订单/多空/风控4检查/百分比滑点/部分成交 | docs/engine.md |
| indicators.py | pandas-ta 防前瞻包装，calc(name, df, bar_index) | - |
| memory.py | 文件式记忆：Workspace 隔离 + log/note/recall | docs/memory.md |
| tools.py | ToolKit：OpenAI function calling schema + 分发 + 调用追踪；market_observe 支持 symbol；含 compute 沙箱计算 | docs/tools.md, docs/compute.md |
| sandbox.py | exec_compute 沙箱执行器：eval-first/黑名单 builtins/print→_stdout/Trading Coreutils（含 bbands/macd helper）/SIGALRM 超时/traceback 增强/自动降维序列化 | docs/compute.md |
| agent.py | LLMAgent：ReAct loop（OpenAI SDK 兼容），AgentProtocol | docs/agent-protocol.md |
| runner.py | Runner 主循环；集成 ContextManager + TraceWriter，追踪 agent_step/context/decision | docs/runner.md |
| tracer.py | TraceWriter 本地 JSONL 追踪 + decision_to_dict 完整序列化；对齐 OTel GenAI | docs/tracer.md |
| context.py | ContextManager：五层认知上下文组装（recent_bars/pending_orders/recent_decisions）+ LLM 文本格式化 | docs/context.md |
| eval.py | Evaluator：绩效指标（真实 trade_log 盈亏）+ 遵循度报告 | docs/eval.md |
| data.py | load_csv 标准化加载 + make_sample_data 模拟数据生成（regime 多行情模式） | - |

## 快速开始

```bash
# 安装
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 全量测试（108 个 scenarios）
.venv/bin/pytest tests/ -v

# Mock demo（无需 API key，7 种策略）
python demo.py --mock
python demo.py --mock --strategy bracket_atr
python demo.py --mock --strategy all

# 使用内置模拟数据 + 真实 LLM（Claude）
ANTHROPIC_API_KEY=sk-ant-... python demo.py --strategy free_play

# 使用自定义 CSV + GPT
OPENAI_API_KEY=sk-... python demo.py --provider openai --csv your_data.csv
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

仿真度升级完成：133/133 BDD scenarios 全绿（Phase 1-7 + 上下文工程重构 + 可观测性追踪 + E2E 策略多样化 + compute 沙箱重构：黑名单 builtins/print _stdout/traceback 增强/bbands+macd helper/无状态语义明确化）
路线图：docs/roadmap.md

# currentDate
Today's date is 2026-02-25.
