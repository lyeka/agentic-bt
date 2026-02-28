---
title: 个人投资助手 — 技术架构设计 V3
status: approved
owner: architecture
---

# Tech Design V3: 个人投资助手 — 技术架构设计

## Context

产品设计文档 `docs/agent-platform.md` 已完成（仿生学架构）。V3 是在 V1 自我批评 + 用户反馈后的第三版。

### V2 → V3 的关键改进

| # | 改进 | 驱动力 |
|---|------|--------|
| 1 | 提取 `src/core/` 共享包，agent 不 import agenticbt | 保持 agenticbt 作为独立回测框架 |
| 2 | 取消 Brain 类，ReAct loop 内嵌 Kernel.turn() | 30 行代码不值得一个类 |
| 3 | Agent 自举能力 | Agent 从零开始，不依赖预设模板 |
| 4 | Pi 工具哲学：6 个工具替代 15 个 | read/write/edit 是通用原语 |
| 5 | 预连通管道改为文件路径模式匹配 | 比 tool-name 触发更优雅 |

---

## 一、核心技术框架选型：自建内核

### 决策：自建内核 + 基础设施库

**调研覆盖**：LangGraph、CrewAI、Pydantic AI、OpenAI Agents SDK、Agent Zero、smolagents、Agno、Microsoft Agent Framework、Google ADK

**核心矛盾**（适用于所有候选）：

| 我们需要 | 框架提供 | 冲突 |
|---------|---------|------|
| 文件式 workspace（用户可编辑 .md） | DB 序列化 state | 持久化哲学不同 |
| 器官模型（soul/memory/notebook 各有生命周期） | 图节点/pipeline 模型 | 编程模型不同 |
| 路径模式驱动的预连通管道 | 用户空间 hook | 集成深度不同 |
| 分层文件权限（tracking 自由 / soul 需确认） | 统一 state 管理 | 权限粒度不同 |

**LangGraph**（最近候选）：reducer-driven state 无法表达"write notebook/ 后自动更新 memory 索引"这种路径模式驱动的副作用。**Agent Zero**（第二候选）：完整自主 Agent 系统（含 Docker 沙箱），不是可嵌入框架。

### 技术栈

| 层级 | 选择 | 理由 |
|------|------|------|
| 异步运行时 | `asyncio` (stdlib) | Telegram/Scheduler 需 async |
| LLM 客户端 | `openai>=1.0` | 已验证可切 Claude/GPT/Ollama |
| Telegram | `aiogram>=3.25` | 全异步原生 |
| 定时调度 | `APScheduler>=3.11` | AsyncIOScheduler |
| 记忆检索 | `sqlite3` FTS5 (stdlib) | 零依赖全文搜索 |
| 沙箱 | 复用提取的 `core/sandbox.py` | 已验证安全机制 |
| 数据获取 | `tushare` (默认适配器) | A 股主流数据源 |
| 数据处理 | `pandas + pandas-ta` | OHLCV + 技术指标 |

---

## 二、与现有代码的关系

### 决策：提取 `src/core/` 共享包 + 新建 `src/agent/`

agenticbt 保留为独立的量化回测框架。agent 不直接 import agenticbt。公共代码提取到 `src/core/`：

```
src/
  core/                  ← 公共基础（从 agenticbt 提取）
    sandbox.py           ← 448 行，计算沙箱
    tracer.py            ← 72 行，JSONL 追踪
    indicators.py        ← 117 行，技术指标

  agenticbt/             ← 回测框架（import core/，86 BDD 保持绿色）
  agent/                 ← 持久投资助手（import core/）
```

**提取标准**：完全独立、无 Engine 依赖、两个包都需要。

**不提取 memory.py**（134 行）：现有 Memory 类的 Workspace 结构（playbook.md/journal/notes）是回测专有设计。持久 Agent 的记忆品类（soul/beliefs/tracking/observations/reflections）完全不同。Agent 自建记忆系统。

**总计提取**：637 行公共代码。其余 2544 行保留在 agenticbt。

---

## 三、工具哲学（Pi-inspired）

### 3.1 最小完备工具集

Pi/bub/ampcode 的核心洞见：**read/write/edit/bash 是最小完备工具集**。

- read/write = 基本 I/O（输入和输出）
- edit = 精准介入 + 缩短反馈链路
- bash = 对接现有生态的桥梁

映射到投资 Agent：**4 个通用原语 + 2 个领域工具 = 6 个工具**。

| 工具 | 类型 | 仿生 | 说明 |
|------|------|------|------|
| `read(path)` | 通用原语 | 看 | 读 workspace 任意文件 |
| `write(path, content)` | 通用原语 | 写 | 写 workspace 任意文件 |
| `edit(path, old, new)` | 通用原语 | 精准修改 | diff-based 修改 |
| `compute(code)` | 领域增强 | 计算器 | 沙箱化 Python（安全版 bash） |
| `market.ohlcv(symbol, period)` | 领域核心 | 眼睛 | 内核数据原语，adapter pattern |
| `recall(query)` | 领域增强 | 回忆 | FTS5 全文搜索 memory + notebook |

### 3.2 为什么不是 15 个工具

notebook.write 就是 `write("notebook/xxx.md", content)`。
memory.write 就是 `write("memory/xxx.md", content)`。
不需要单独的工具。

read/write/edit 的覆盖范围：
- 写研究报告 → `write("notebook/research/宁德时代/2024-01-15.md", content)`
- 更新信念 → `edit("memory/beliefs.md", "旧信念", "新信念+理由")`
- 修改灵魂 → `edit("soul.md", ...)` → 触发权限检查
- 读取历史研究 → `read("notebook/research/宁德时代/2024-01-15.md")`
- 自举工作区 → `write("soul.md", "# 我是谁\n...")`

### 3.3 领域工具的不可替代性

`market.ohlcv` 不能用 read/write 替代——它需要 MarketAdapter 归一化 + canonical 格式契约 + 缓存 + OHLCV→DataStore→compute 预连通管道。

`recall` 不能用 read 替代——它需要 FTS5 全文索引跨越 memory/ + notebook/ 所有文件。

`compute` 不能用 bash 替代——它需要沙箱隔离 + OHLCV 自动注入 + Trading Coreutils 预装。

---

## 四、整体架构

### 4.1 Kernel-centric 设计

```
                    ┌─────────────────────┐
                    │     Adapters         │
                    │  CLI  /  Telegram    │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │      Kernel         │
                    │                     │
                    │  turn()  ← ReAct    │
                    │  wire()  ← 管道注册  │
                    │  emit()  ← 管道触发  │
                    │  data    ← DataStore │
                    │                     │
                    └──┬──────────────┬───┘
                       │              │
              ┌────────┘              └────────┐
              ▼                                ▼
        ┌─ 6 Tools ─┐                  ┌─ Context ─┐
        │ read       │                  │ assemble   │
        │ write      │                  │ soul 注入  │
        │ edit       │                  │ beliefs    │
        │ compute    │                  │ obs mask   │
        │ market     │                  └────────────┘
        │ recall     │
        └────────────┘
```

**没有 Brain 类**。ReAct loop 是 Kernel.turn() 的 30-40 行。
**没有 if/elif 管道**。管道通过 wire/emit + 路径模式驱动。

### 4.2 声明式管道 — 路径模式匹配

```python
# 预连通管道（声明式）
kernel.wire("write:notebook/**",           memory_index.update)
kernel.wire("write:memory/beliefs.md",     tracer.record_belief_change)
kernel.wire("edit:memory/beliefs.md",      tracer.record_belief_change)
kernel.wire("market.ohlcv.done",           data_store.set_ohlcv)
kernel.wire("turn.start",                  context.inject_soul)
kernel.wire("turn.start",                  context.inject_beliefs)

# 文件权限（声明式）
kernel.permission("notebook/**",            Permission.FREE)
kernel.permission("memory/tracking.md",     Permission.FREE)
kernel.permission("memory/observations/**", Permission.FREE)
kernel.permission("memory/beliefs.md",      Permission.REASON_REQUIRED)
kernel.permission("memory/preferences.md",  Permission.USER_CONFIRM)
kernel.permission("soul.md",               Permission.USER_CONFIRM)
```

整个系统的行为 = 一组声明式的路径模式规则。零 if/elif。

### 4.3 一次 Turn 的数据流

```
input → Kernel.turn(input, session)
         │
         ├─ 1. emit("turn.start") → 注入 soul + beliefs + memory_index
         ├─ 2. context.assemble(session.history, input) → messages
         ├─ 3. LLM call(messages, 6 tools schema)
         │      │
         │      ├─ tool_call("write", path="notebook/...", content="...")
         │      │    → permission(path) → FREE → 执行
         │      │    → wire("write:notebook/**") → memory_index.update
         │      │
         │      ├─ tool_call("edit", path="memory/beliefs.md", ...)
         │      │    → permission(path) → REASON_REQUIRED
         │      │    → wire("edit:memory/beliefs.md") → tracer.record
         │      │
         │      └─ repeat until finish_reason == "stop"
         │
         ├─ 4. session.append(new_messages)
         ├─ 5. emit("turn.done") → tracer.write
         └─ 6. return reply
```

### 4.4 自举（Self-bootstrapping）

Agent 从零启动，使用与日常工作相同的工具自举：

```
首次启动：
  1. Kernel 检测 soul.md 不存在
  2. 注入种子 system prompt（bootstrap/seed.py）
  3. Agent 与用户对话 → 了解投资风格/偏好/关注领域
  4. Agent 用 write() 自己创建 soul.md / memory/*.md
  5. 后续按需创建 notebook/ 结构

非首次启动：
  1. soul.md 存在 → 加载注入 → 正常运行
```

Default Profile = 种子对话脚本 + 推荐结构，不是必须模板。

### 4.5 关键接口

```python
class Kernel:
    """唯一协调中心：ReAct loop + 管道 + 数据 + 权限"""
    data: DataStore
    async def boot(self, workspace: Path)
    async def turn(self, input: str, session: Session) -> str
    def wire(self, pattern: str, handler: Callable)
    async def emit(self, event: str, data: Any)
    def permission(self, pattern: str, level: Permission)

class DataStore:
    """内核数据注册表"""
    def set(self, key: str, data: Any)
    def get(self, key: str) -> Any | None

class ContextAssembler:
    """上下文组装 + Observation Masking"""
    def assemble(self, history: list[dict], input: str) -> list[dict]
    def compress(self, messages: list[dict]) -> list[dict]

class MarketAdapter(Protocol):
    """数据源适配器接口"""
    name: str
    async def fetch(self, symbol: str, period: str,
                    start: str | None, end: str | None) -> pd.DataFrame

class Session:
    """会话容器"""
    history: list[dict]
    def append(self, messages: list[dict])
    def compress(self, strategy: Callable)
```

---

## 五、硬问题与解法

### 5.1 Observation Masking

- Observation = tool result 中的数据（OHLCV table、compute 结果）
- Reasoning = LLM 推理文本、用户对话
- 超过 N 轮后，历史 observation 压缩为 1 行摘要，推理完整保留

### 5.2 错误处理

| 错误 | 策略 |
|------|------|
| LLM 无效 tool call | 返回错误消息，LLM 自我修正 |
| 网络错误 | 返回错误给 LLM，LLM 决定重试或告知用户 |
| Token 超限 | assemble 时触发 Observation Masking |
| 工具超时 | sandbox SIGALRM；其他 asyncio.wait_for(30s) |
| Kernel 崩溃 | Session 持久化 JSONL |

### 5.3 Session 语义

| 场景 | Session ID |
|------|-----------|
| CLI | `cli-{pid}` |
| Telegram chat | `tg-{chat_id}` |
| Scheduler 任务 | `task-{task_id}` |

### 5.4 async 桥接

`asyncio.to_thread` 包装同步函数（sandbox/tushare），零侵入。

---

## 六、目录结构

```
src/
  core/                    ← 公共基础（从 agenticbt 提取）
    __init__.py
    sandbox.py             ← 计算沙箱（448 行）
    tracer.py              ← JSONL 追踪（72 行）
    indicators.py          ← 技术指标（117 行）

  agenticbt/               ← 回测框架（import core/）

  agent/                   ← 持久投资助手
    __init__.py
    kernel.py              ← Kernel：turn + wire/emit + DataStore + 权限
    context.py             ← 上下文组装 + Observation Masking
    session.py             ← 会话管理 + 持久化

    tools/                 ← 6 个工具
      primitives.py        ← read / write / edit
      compute.py           ← 沙箱 Python（包装 core/sandbox）
      market.py            ← MarketAdapter Protocol + MarketTool
      recall.py            ← FTS5 搜索

    adapters/
      cli.py
      telegram.py          ← Phase 2
      market/
        tushare.py
        csv.py

    bootstrap/
      seed.py              ← 自举种子对话
      profiles/
        investor.md        ← 投资助手种子提示词
```

---

## 七、分阶交付

### Phase 1a：能对话
kernel.py + adapters/cli.py → CLI 聊天

### Phase 1b：能看能算
tools/market.py + adapters/market/tushare.py + tools/compute.py → 获取行情 + 计算指标

### Phase 1c：能读能写能记 + 自举
tools/primitives.py + tools/recall.py + context.py + session.py + bootstrap/seed.py → 完整研究流程

### Phase 2：能交流能定时
adapters/telegram.py + scheduler.py + Skill Engine

### Phase 3：能成长能委派
成长循环 + Subagent + /backtest skill

---

## 八、风险与缓解

| 风险 | 缓解 |
|------|------|
| tushare 频率限制 | 日线当日缓存 + 指数退避 |
| 长对话 token 爆炸 | Observation Masking + Session.compress |
| 崩溃状态丢失 | Session JSONL |
| soul.md 误修改 | Permission.USER_CONFIRM + git 追踪 |
| wire/emit 调试困难 | emit 自动写 trace |
| 自举质量不稳定 | 提供推荐 Profile 种子 |

---

## 九、依赖变更

```toml
[project]
dependencies = [
    "openai>=1.0",
    "pandas>=2.0",
    "pandas-ta",
    "tushare",
]

[project.optional-dependencies]
telegram = ["aiogram>=3.25"]
scheduler = ["apscheduler>=3.11"]
dev = ["pytest>=7.0", "pytest-bdd>=7.0", "pytest-asyncio"]
```

---

## 十、验证方式

1. Phase 1a：CLI 对话，LLM 能回复
2. Phase 1b：`market.ohlcv("300750")` → compute RSI → 返回分析
3. Phase 1c：完整研究流程 + 自举（从空 workspace 到完整设置）
4. 管道验证：write notebook/ → memory index 自动更新 → recall 能搜到
5. 权限验证：write soul.md → 拦截并请求确认
6. BDD 回归：agenticbt tests 持续绿色

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
