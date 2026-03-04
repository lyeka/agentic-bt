# AgenticBT

> **Agent 时代的个人投资助手**
> 仿生学设计 · 有灵魂 · 有记忆 · 能看行情 · 能计算 · 能成长

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![BDD Tests](https://img.shields.io/badge/tests-211%20passed-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## 这是什么

一个你自己运行的**个人投资研究助手**。说"帮我看看宁德时代"，它自动获取行情、计算指标、生成分析笔记。

它不是一堆零件让你自己组装，而是一个**预连通的有机体**——OHLCV 自动流入 compute，soul 变更自动刷新 system prompt，memory 超限自动压缩。首次启动时 Agent 通过对话了解你的投资风格，然后自己创建身份（`soul.md`）和记忆（`memory.md`）。

底层还包含一个 LLM 量化回测框架（agenticbt），让 Agent 像交易员一样做策略回测——"Backtest the Trader, Not Just the Strategy."

### 仿生学设计

```
人类投资者                        Agent

灵魂（价值观/性格/风格）    →    soul.md
记忆（经验/观察/偏好）      →    memory.md（单文件，倒排，自动压缩）
笔记本（研究报告/草稿）    →    notebook/
眼睛（看行情）              →    market.ohlcv（Tushare A 股日线）
计算器（扩展心算）          →    compute（沙箱 Python + Trading Coreutils）
手（操作文件）              →    read / write / edit
终端（执行命令）            →    bash
```

### 两个系统，一套哲学

**Agent 说意图，Framework 说真相。** LLM Agent 像人类一样思考和决策，确定性引擎负责数据、计算和执行。

| 系统 | 定位 | 状态 |
|------|------|------|
| **agent** | 持久投资助手 — Kernel + 6 工具 + 自举 + Soul/Memory | Phase 1 完成，活跃开发中 |
| **agenticbt** | 量化回测框架 — 确定性引擎 + LLM Agent + 11 工具 | 完成 |
| **core** | 公共基础 — 沙箱 / 指标 / 追踪，两个系统共享 | 完成 |

两个系统独立：`agent` 和 `agenticbt` 互不依赖，各自 import `core`。

---

## 快速开始

### 安装

```bash
git clone <repo-url> && cd agentic-bt
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

### 投资助手 CLI

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env：设置 API_KEY、MODEL、BASE_URL（可选）、TUSHARE_TOKEN

# 2. 启动
python -m agent.adapters.cli
```

首次启动时工作区为空，Agent 通过种子对话了解你的投资风格，然后用 `write` 工具自己创建 `soul.md` 和 `memory.md`。之后每次启动自动加载身份与记忆。

### Telegram Bot（Polling）

```bash
# 1) 安装 Telegram 依赖
.venv/bin/pip install -e ".[telegram]"

# 2) 配置 .env（最少需要这三项）
# API_KEY=...
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_ALLOWED_USER_IDS=123456789

# 3) 启动
python -m agent.adapters.telegram
```

说明：
- `WORKSPACE`（默认 `~/.agent/workspace`）用于 `soul.md/memory.md/notebook/`
- `STATE_DIR`（默认 `~/.agent/state`）用于 session/trace 等运行状态
- 默认 owner-only（`TELEGRAM_ALLOWED_USER_IDS`），未配置时只回显你的 `user_id` 并拒绝执行
- `TELEGRAM_SHOW_PROCESS_MESSAGES` 默认 `false`：关闭中间过程消息（如 tool 调用进度）
- `TELEGRAM_RENDER_MODE` 默认 `html`：对 LLM markdown 做基础渲染（支持标题/列表/粗斜体/代码块）

### 回测框架 Demo

```bash
# Mock 模式（无需 API key，6 种策略有 Mock Agent）
python demo.py --mock
python demo.py --mock --strategy bracket_atr
python demo.py --mock --strategy all

# 真实 LLM
ANTHROPIC_API_KEY=sk-ant-... python demo.py --strategy free_play
OPENAI_API_KEY=sk-... python demo.py --provider openai --csv your_data.csv
```

### 运行测试

```bash
.venv/bin/pytest tests/ -v                 # 全量测试
.venv/bin/pytest tests/test_kernel.py -v   # 单模块
.venv/bin/pytest tests/ -k "market"        # 按关键词
```

---

## 架构

### agent — 持久投资助手

```
Adapters (CLI / Telegram)
       │
    Kernel
    ├── turn()  ← ReAct loop
    ├── wire()  ← 声明式管道（fnmatch 路径模式）
    ├── emit()  ← 管道触发
    ├── boot()  ← 自举（检测 soul.md → 注入系统提示词）
    ├── data    ← DataStore（OHLCV 自动注入 compute）
    └── 6 Tools
        read · write · edit · compute · market.ohlcv · bash
```

### agenticbt — 回测框架

```
Runner
  ├── Engine (确定性)  →  ContextManager (五层上下文)  →  LLMAgent (ReAct Loop)
  │     ▲                                                      │
  │     └──────────── ToolKit ◀────────────────────────────────┘
  │                   11 工具: market · indicator · account · trade · memory · order · compute
  ├── Memory (文件式)
  └── Evaluator (绩效 + 遵循度)
```

---

## Python API

### 投资助手 Kernel

```python
from pathlib import Path
from agent.kernel import Kernel, Session, Permission
from agent.tools import read, write, edit, compute, market, bash
from agent.adapters.market.csv import CsvAdapter

workspace, cwd = Path("./workspace"), Path.cwd()
kernel = Kernel(model="gpt-4o-mini", api_key="sk-...")

# 注册工具
read.register(kernel, workspace, cwd)
write.register(kernel, workspace, cwd)
edit.register(kernel, workspace, cwd)
compute.register(kernel)
market.register(kernel, CsvAdapter({"300750": your_dataframe}))  # OHLCV DataFrame
bash.register(kernel, cwd=cwd)

# 自举（检测 soul.md，无则进入种子对话）
kernel.boot(workspace)

# 声明式管道 + 权限
kernel.wire("write:soul.md", lambda e, d: kernel._assemble_system_prompt())
kernel.permission("soul.md", Permission.USER_CONFIRM)

# 对话
session = Session(session_id="demo")
reply = kernel.turn("分析一下宁德时代最近的走势", session)
```

### 一行回测

```python
from agenticbt import run, BacktestConfig, make_sample_data

result = run(BacktestConfig(
    data=make_sample_data("AAPL", periods=252),
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

---

## LLM Provider 切换

统一使用 OpenAI SDK，通过 `base_url` 切换提供商：

| Provider | `base_url` | 环境变量 |
|----------|-----------|---------|
| OpenAI GPT | `None`（默认） | `OPENAI_API_KEY` |
| Claude (Anthropic) | `https://api.anthropic.com/v1/` | `ANTHROPIC_API_KEY` |
| DeepSeek | `https://api.deepseek.com` | `API_KEY` |
| Ollama（本地） | `http://localhost:11434/v1/` | — |

投资助手 CLI 通过 `.env` 的 `MODEL` + `BASE_URL` + `API_KEY` 统一配置。回测 Demo 通过 `--provider` 参数或环境变量切换。

---

## 工具体系

### agent — 6 个工具

| 工具 | 说明 |
|------|------|
| `read(path)` | 读文件（行号 + 分页 + 截断 + 目录列表） |
| `write(path, content)` | 写文件（自动创建目录 + 权限检查） |
| `edit(path, old, new)` | 精确文本替换（模糊匹配 + diff 输出） |
| `compute(code)` | 沙箱 Python，自动注入 OHLCV + Trading Coreutils |
| `market_ohlcv(symbol)` | 获取行情，Adapter Pattern 解耦数据源 |
| `bash(command)` | Shell 命令执行（超时 + 进程树清理） |

### agenticbt — 11 个工具

| 类别 | 工具 | 说明 |
|------|------|------|
| 市场 | `market_observe` · `market_history` | 当前 Bar / 历史 OHLCV |
| 指标 | `indicator_calc` | RSI · SMA · EMA · ATR · MACD · BBANDS |
| 账户 | `account_status` | 现金 / 权益 / 持仓 |
| 交易 | `trade_execute` | market / limit / stop / bracket 订单 |
| 记忆 | `memory_log` · `memory_note` · `memory_recall` | 日志 / 笔记 / 检索 |
| 订单 | `order_query` · `order_cancel` | 查询 / 撤单 |
| 计算 | `compute` | 沙箱 Python + Trading Coreutils |

---

<details>
<summary><b>策略库 — 8 种预置策略</b></summary>

| 策略 | 行情模式 | Mock | 特性 |
|------|---------|------|------|
| `rsi` | 均值回归 | ✓ | RSI 均值回归，市价单 |
| `bracket_atr` | 趋势 | ✓ | SMA 交叉 + ATR bracket 订单 |
| `bollinger_limit` | 震荡 | ✓ | 布林带 + 限价单 + 撤单 |
| `adaptive_memory` | 均值回归 | ✓ | 记忆驱动仓位调节 |
| `multi_asset` | 牛熊切换 | ✓ | AAPL/GOOGL 轮动 |
| `quant_compute` | 趋势 | ✓ | 沙箱计算自定义指标 |
| `free_play` | 随机 | LLM-only | 激进交易，全工具链 |
| `reflective` | 随机 | LLM-only | 反思式交易，记忆 + 复盘 |

```bash
python demo.py --mock --strategy all      # 运行全部 Mock 策略
python demo.py --strategy free_play       # 需要 LLM API key
```

</details>

---

## 项目结构

```
agentic-bt/
├── demo.py                        # 回测 CLI 演示
├── pyproject.toml                 # 依赖: openai + pandas + pandas-ta + tushare + python-dotenv
├── .env.example                   # 环境变量模板
│
├── src/
│   ├── agent/                     # 持久投资助手（活跃开发）
│   │   ├── kernel.py              # Kernel（ReAct + wire/emit + DataStore + Permission + boot）
│   │   ├── tools/
│   │   │   ├── read.py            # 文件读取
│   │   │   ├── write.py           # 文件写入
│   │   │   ├── edit.py            # 文本替换
│   │   │   ├── compute.py         # 沙箱 Python
│   │   │   ├── market.py          # MarketAdapter + market.ohlcv
│   │   │   └── bash.py            # Shell 执行
│   │   ├── adapters/
│   │   │   ├── cli.py             # CLI REPL
│   │   │   └── market/            # TushareAdapter · CsvAdapter
│   │   └── bootstrap/seed.py      # 自举种子 prompt
│   │
│   ├── agenticbt/                 # 回测框架
│   │   ├── engine.py              # 确定性市场模拟（多资产/bracket/风控/部分成交）
│   │   ├── agent.py               # LLMAgent（三层 System Prompt + ReAct）
│   │   ├── runner.py              # 回测主循环
│   │   ├── context.py             # 五层认知上下文 + XML 格式化
│   │   ├── tools.py               # 11 工具 schema + 分发
│   │   ├── eval.py                # 绩效 + 遵循度
│   │   ├── memory.py              # 文件式记忆
│   │   └── data.py                # 数据加载 + 模拟生成
│   │
│   └── core/                      # 公共基础
│       ├── sandbox.py             # 沙箱执行器
│       ├── indicators.py          # pandas-ta 防前瞻包装（6 指标）
│       └── tracer.py              # JSONL 追踪（对齐 OTel GenAI）
│
├── tests/
│   ├── features/                  # 16 个 Gherkin feature 文件
│   └── test_*.py                  # 17 个 step definitions + E2E
│
├── examples/strategies.py         # 8 策略注册表（Mock Agent + LLM Prompt）
├── scripts/                       # trace 分析脚本
└── docs/                          # 13 篇设计文档（agent-design.md 是 Agent 唯一活文档）
```

---

## 开发

本项目强制 **BDD 驱动**：Feature 先行，禁止无 scenario 的实现代码。开发规范详见 [CLAUDE.md](CLAUDE.md)。

---

## 路线图

| 阶段 | 状态 | 亮点 |
|------|------|------|
| **agent Phase 1** | 完成 | Kernel + 6 工具 + Soul/Memory + 自举 + Session 持久化 |
| **agent Phase 2** | 计划中 | Telegram 通道 · APScheduler 定时任务 · Skill Engine |
| **agent Phase 3** | 未来 | 成长循环（reflections → beliefs → soul 微调）· Subagent · /backtest skill |
| agenticbt V1 | 完成 | 单资产 · 市价单 · BDD 驱动 · Mock + 真实 LLM |
| agenticbt V2 | 完成 | 多资产 · bracket/limit/stop · 风控 4 检查 · ~190 BDD scenarios |

设计文档：[docs/agent-design.md](docs/agent-design.md)（Agent 唯一活文档）· [docs/skills.md](docs/skills.md)（Skill Engine 集成）· [docs/roadmap.md](docs/roadmap.md)

---

## License

MIT
