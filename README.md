# AgenticBT

> **Backtest the Trader, Not Just the Strategy.**
> 回测交易员，而不仅仅是策略。

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![BDD Tests](https://img.shields.io/badge/BDD%20tests-170%20scenarios-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

两个系统，一套哲学：**Agent 说意图，Framework 说真相。**

| 系统 | 定位 | 状态 |
|------|------|------|
| `agenticbt` | 量化回测框架 — LLM Agent 像交易员一样决策，确定性引擎负责数据/计算/执行 | 完成 |
| `agent` | 持久投资助手 — Kernel-centric 架构，6 工具 + 声明式管道 + 自举 | Phase 1 完成 |
| `core` | 公共基础 — 沙箱/指标/追踪，两个系统共享 | 完成 |

---

## 架构

### agenticbt — 回测框架

```
Runner
  ├── Engine (确定性)  →  ContextManager (五层上下文)  →  LLMAgent (ReAct Loop)
  │     ▲                                                      │
  │     └──────────── ToolKit ◀────────────────────────────────┘
  │                   market · indicator · account · trade · memory
  ├── Memory (文件式)
  └── Evaluator (绩效 + 遵循度)
```

### agent — 持久投资助手

```
Adapters (CLI / Telegram)
       │
    Kernel
    ├── turn()  ← ReAct loop
    ├── wire()  ← 声明式管道（fnmatch 路径模式）
    ├── emit()  ← 管道触发
    ├── boot()  ← 自举（检测 soul.md → 注入系统提示词）
    ├── data    ← DataStore
    └── 6 Tools
        read · write · edit · compute · market.ohlcv · recall
```

Pi-inspired 工具哲学：read/write/edit 是通用原语，覆盖所有文件操作；compute/market.ohlcv/recall 是不可替代的领域工具。

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/agentic-bt.git
cd agentic-bt
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

### 回测框架

```bash
# Mock demo（无需 API key，8 种策略）
python demo.py --mock
python demo.py --mock --strategy bracket_atr
python demo.py --mock --strategy all

# 真实 LLM — Claude
ANTHROPIC_API_KEY=sk-ant-... python demo.py --strategy free_play

# GPT + 自定义 CSV
OPENAI_API_KEY=sk-... python demo.py --provider openai --csv your_data.csv
```

### 投资助手 CLI

```bash
# 启动 CLI 对话（需要 LLM API key）
OPENAI_API_KEY=sk-... python -m agent.adapters.cli
```

首次启动时工作区为空，Agent 通过种子对话了解你的投资风格，然后用 write 工具自己创建 soul.md 和 memory/ 结构。

### 运行测试

```bash
# 全量 BDD（170 scenarios）
.venv/bin/pytest tests/ -v

# 单模块
.venv/bin/pytest tests/test_kernel.py -v
.venv/bin/pytest tests/test_engine.py -v

# 按关键词
.venv/bin/pytest tests/ -k "market"
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
    strategy_prompt="RSI < 35 时买入，RSI > 65 时平仓",
    model="claude-sonnet-4-20250514",
    base_url="https://api.anthropic.com/v1/",
    api_key="sk-ant-...",
))

p = result.performance
print(f"总收益率  {p.total_return:+.2%}")
print(f"最大回撤  {p.max_drawdown:.2%}")
print(f"夏普比率  {p.sharpe_ratio:.3f}")
```

### 投资助手 Kernel

```python
from agent.kernel import Kernel, Session
from agent.tools import market, compute, primitives, recall
from agent.adapters.market.csv import CsvAdapter

kernel = Kernel(model="gpt-4o-mini", api_key="sk-...")
kernel.boot(Path("./workspace"))

# 注册工具
primitives.register(kernel, Path("./workspace"))
market.register(kernel, CsvAdapter({"300750": df}))
compute.register(kernel)
recall.register(kernel, Path("./workspace"))

# 声明式管道
kernel.wire("write:notebook/**", my_index_handler)
kernel.permission("soul.md", Permission.USER_CONFIRM)

# 对话
session = Session(session_id="cli-1")
reply = kernel.turn("分析一下宁德时代最近的走势", session)
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

---

## 工具体系

### agenticbt — 回测工具（5 个）

| 工具 | 参数示例 | 返回 |
|------|---------|------|
| `market_observe` | `{}` | `{open, high, low, close, volume, datetime}` |
| `indicator_calc` | `{"name": "RSI", "period": 14}` | `{"value": 32.5}` |
| `account_status` | `{}` | `{cash, equity, positions}` |
| `trade_execute` | `{"action": "buy", "symbol": "AAPL", "quantity": 100}` | `{"status": "submitted"}` |
| `memory_log/note/recall` | `{"content": "..."}` | `{"ok": true}` |

支持指标：RSI · SMA · EMA · ATR · MACD · BBANDS

### agent — 投资助手工具（6 个）

| 工具 | 类型 | 说明 |
|------|------|------|
| `read(path)` | 通用原语 | 读 workspace 任意文件 |
| `write(path, content)` | 通用原语 | 写 workspace 任意文件（自动创建目录） |
| `edit(path, old, new)` | 通用原语 | diff-based 精准修改 |
| `compute(code)` | 领域增强 | 沙箱 Python，自动注入 OHLCV + Trading Coreutils |
| `market.ohlcv(symbol)` | 领域核心 | 获取行情，adapter pattern 解耦数据源 |
| `recall(query)` | 领域增强 | 全文搜索 memory + notebook |

---

## 项目结构

```
agentic-bt/
├── demo.py                     # CLI 端到端演示
├── pyproject.toml              # 依赖: openai + pandas + pandas-ta
├── src/
│   ├── core/                   # 公共基础（两个系统共享）
│   │   ├── sandbox.py          # 沙箱执行器（eval-first/黑名单/Trading Coreutils/超时）
│   │   ├── indicators.py       # pandas-ta 防前瞻包装（6 指标）
│   │   └── tracer.py           # JSONL 追踪（对齐 OTel GenAI）
│   │
│   ├── agenticbt/              # 回测框架（13 文件）
│   │   ├── models.py           # 数据结构基础层
│   │   ├── engine.py           # 确定性市场模拟（多资产/bracket/风控/部分成交）
│   │   ├── agent.py            # LLMAgent（三层 System Prompt + ReAct loop）
│   │   ├── runner.py           # 回测主循环
│   │   ├── context.py          # 五层认知上下文 + XML 格式化
│   │   ├── tools.py            # 工具 schema + 分发
│   │   ├── eval.py             # 绩效指标 + 遵循度
│   │   ├── memory.py           # 文件式记忆
│   │   ├── data.py             # 数据加载 + 模拟生成
│   │   └── tracer.py           # decision_to_dict 序列化
│   │
│   └── agent/                  # 持久投资助手
│       ├── kernel.py           # Kernel（ReAct + wire/emit + Permission + boot）
│       ├── tools/
│       │   ├── primitives.py   # read / write / edit
│       │   ├── compute.py      # 沙箱 Python
│       │   ├── market.py       # MarketAdapter Protocol
│       │   └── recall.py       # 全文搜索
│       ├── adapters/
│       │   ├── cli.py          # CLI REPL
│       │   └── market/csv.py   # 测试用 CsvAdapter
│       └── bootstrap/
│           └── seed.py         # 自举种子 prompt
│
├── tests/
│   ├── features/               # 12 个 Gherkin feature 文件
│   │   ├── engine.feature      # 引擎行为规格
│   │   ├── kernel.feature      # Kernel 核心行为（5 scenarios）
│   │   ├── kernel_tools.feature # 工具与工作区（10 scenarios）
│   │   └── ...                 # indicators/memory/tools/agent/runner/eval/context/data/tracer/compute
│   └── test_*.py               # 14 个 step definition 文件 + 1 E2E
│
├── examples/                   # 8 策略（Mock Agent + LLM Prompt）
├── scripts/                    # trace 分析脚本
└── docs/                       # 12 篇设计文档
```

---

## BDD 开发规范

本项目强制 BDD 驱动，铁律：Feature 先行。

```
① 写 Feature 文件（Gherkin）  →  RED
② 写 step definitions + 最小实现  →  GREEN
③ Refactor
```

禁止在没有对应 Feature scenario 的情况下写实现代码。

---

## 核心模块参考

### core/ — 公共基础

| 模块 | 职责 |
|------|------|
| `sandbox.py` | exec_compute 沙箱：eval-first / 黑名单 builtins / Trading Coreutils（bbands/macd/crossover）/ SIGALRM 超时 |
| `indicators.py` | IndicatorEngine，pandas-ta 防前瞻包装，6 指标 |
| `tracer.py` | TraceWriter 本地 JSONL 追踪，对齐 OTel GenAI |

### agenticbt/ — 回测框架

| 模块 | 职责 | 设计文档 |
|------|------|---------|
| `engine.py` | 确定性市场模拟：多资产 / market+limit+stop+bracket 订单 / 风控 4 检查 / 部分成交 | docs/engine.md |
| `agent.py` | LLMAgent：三层 System Prompt + ReAct loop | docs/agent-protocol.md |
| `runner.py` | 主循环：advance → match → assemble_context → decide → record | docs/runner.md |
| `context.py` | 五层认知上下文 + XML 格式化 + 持仓盈亏注入 + 风控约束注入 | docs/context.md |
| `tools.py` | OpenAI function calling schema + 分发 + 调用追踪 | docs/tools.md |
| `eval.py` | 绩效指标（sortino/calmar/cagr/max_dd_duration）+ 遵循度 | docs/eval.md |
| `memory.py` | 文件式记忆：Workspace 隔离 + log/note/recall | docs/memory.md |
| `data.py` | load_csv 多格式兼容 + make_sample_data（regime 多行情模式） | - |

### agent/ — 持久投资助手

| 模块 | 职责 | 设计文档 |
|------|------|---------|
| `kernel.py` | Kernel 核心：ReAct loop + wire/emit 声明式管道 + DataStore + Permission + boot 自举 | docs/tech-design.md |
| `tools/primitives.py` | read/write/edit 通用原语，经权限检查 + emit 管道事件 | docs/tech-design.md |
| `tools/market.py` | MarketAdapter Protocol + market.ohlcv，adapter pattern 解耦数据源 | docs/tech-design.md |
| `tools/compute.py` | 沙箱 Python，自动从 DataStore 注入 OHLCV | docs/tech-design.md |
| `tools/recall.py` | 全文搜索 workspace .md 文件 | docs/tech-design.md |
| `bootstrap/seed.py` | 首次启动种子 prompt，引导 Agent 自举创建工作区 | docs/tech-design.md |

---

## 路线图

| 阶段 | 状态 | 亮点 |
|------|------|------|
| agenticbt V1 | ✅ 完成 | 单资产 · 市价单 · RSI 策略 · BDD 驱动 · mock + 真实 LLM |
| agenticbt V2 | ✅ 完成 | 多资产 · bracket/limit/stop 订单 · 风控 4 检查 · 部分成交 · 155 BDD scenarios |
| core/ 提取 | ✅ 完成 | sandbox + indicators + tracer 共享基础 |
| agent Phase 1 | ✅ 完成 | Kernel + 6 工具 + 权限 + 自举 + Session 持久化 · 15 BDD scenarios |
| agent Phase 2 | 计划中 | Telegram 通道 · APScheduler 定时任务 · Skill Engine |
| agent Phase 3 | 未来 | 成长循环（reflections → beliefs → soul 微调）· Subagent · /backtest skill |

---

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `openai` | `>=1.0` | OpenAI 兼容 SDK，覆盖所有 LLM Provider |
| `pandas` | `>=2.0` | OHLCV 数据容器 |
| `pandas-ta` | latest | 130+ 技术指标 |
| `tushare` | latest | A 股数据源（agent 可选） |
| `pytest` / `pytest-bdd` | dev | BDD 测试框架 |

Python 3.10+

---

## License

MIT
