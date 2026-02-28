---
title: 个人投资助手 — 设计文档
status: active
---

# 个人投资助手 — 设计文档

> 本文档是 Agent 项目的唯一设计真相源。代码变更时同步更新。
> 替代原 `agent-platform.md` 和 `tech-design.md`。

---

## 一、愿景与定位

**一个你自己运行的个人投资研究助手**，以仿生学设计模拟人类投资者的认知循环——能看行情、能计算、能记录、能反思、能成长；复杂能力通过 Skills 组合生长。

### 典型场景

- **投资研究**：说"帮我看看宁德时代"，agent 自动获取行情、计算指标、结合历史研究、生成分析笔记
- **定时复盘**："每周五帮我复盘本周的观察和判断"，生成反思报告
- **条件扫描**：用 compute 筛选符合条件的标的，写入扫描结果
- **长期跟踪**：维护关注列表，持续积累对标的的观察和判断
- **通用助手**：不限于投资——换 Default Profile，同一内核变成项目管理或学习助手

### 非目标（防止内核膨胀）

- 不做交易系统（不自动下单、不管理订单状态机、不做风控引擎）
- 不在内核里做领域专用数据结构（持仓表/投资账本由 skill 在 notebook 中管理）
- 不把特定数据源做成内核依赖（通过 Tool Provider 扩展）
- 不把复杂多层编排树作为默认架构

### 成功标准

- **可用性**：能稳定常驻，崩溃恢复后不丢任务与关键记忆
- **可控性**：用户能看懂、能编辑、能撤销 agent 的灵魂、记忆与自动化
- **可扩展性**：复杂能力主要通过 skills 迭代，不需要持续改内核
- **成长性**：长期使用后，agent 在研究深度、判断准确性、用户理解上有可观测的进步
- **安全性**：默认不越权；灵魂和核心信念的修改需用户确认

---

## 二、设计理念

### 2.1 仿生学设计

这个 agent 模拟人类投资者的认知系统：

```
人类投资者                      Agent

灵魂（价值观/性格/风格）  →     soul.md
大脑（推理/判断/决策）    →     LLM
眼睛（看行情）           →     market.ohlcv
计算器（扩展心算）        →     compute
笔记本（记录研究/想法）   →     notebook/
记忆（信念/经验/关注）    →     memory/
复盘日记（反思/成长）     →     reflections/
技能（学过的分析方法）    →     skills/
下属（专项委派）         →     subagents
闹钟（习惯/纪律/提醒）   →     scheduler
教练（指导成长的人）      →     用户
```

不只是器官清单——器官之间有**预连通的神经系统**：OHLCV 自动流入 compute，笔记自动索引到 memory，灵魂自动渗透每一次推理。这些预连通管道是内核保证的，LLM 不需要手动搬运数据。

**这是与通用 agent 的本质区别**：通用 agent 是一堆零件，用户自己组装；这个 agent 是一个协调的有机体，开箱即是一个能看行情、能算指标、能记笔记、能反思成长的投资助手。

### 2.2 领域驱动的通用设计

**"投资"不只是 skill 包，而是塑造内核抽象的 design pressure。**

OHLCV 是这个 agent 的内核数据原语——如同 Unix 的 file descriptor。它定义了 agent 的"视觉格式"，所有计算工具自动注入它，所有 skill 都能识别它。

但内核本身仍是通用的。换掉默认配置（Default Profile），同一个内核可以变成项目管理助手或学习助手。投资领域的需求**塑造了抽象的形状**，但不绑架抽象的本质。

类比：Unix 的 owner/group/permission 是通用抽象，但它的形状是被"多用户分时系统"的需求压出来的。

### 2.3 OHLCV 即原语

OHLCV 是这个 agent 的基本粒子，如同 Unix 的 file descriptor。

#### canonical format

```
┌────────────┬────────┬────────┬────────┬────────┬──────────┐
│ date       │ open   │ high   │ low    │ close  │ volume   │
│ datetime   │ float  │ float  │ float  │ float  │ int      │
├────────────┼────────┼────────┼────────┼────────┼──────────┤
│ 2024-01-15 │ 185.32 │ 187.50 │ 184.10 │ 186.90 │ 12345678 │
└────────────┴────────┴────────┴────────┴────────┴──────────┘

6 列。列名小写。不多不少。
```

这个格式是内核契约：
- `market.ohlcv` 返回的永远是这个格式（不管底层适配器是什么）
- `compute` 收到的 `df`/`open`/`high`/`low`/`close`/`volume` 永远是这个格式
- 任何 skill 读到的 OHLCV 永远是这个格式

#### 适配器模式

```
market.ohlcv(symbol, period)
       │
       ▼
  ┌─ MarketAdapter (内核接口) ─────────────┐
  │  fetch(symbol, period, start, end)      │
  │  → canonical OHLCV                      │  ← 内核保证归一化
  └─────────────────────────────────────────┘
       │ (具体实现可替换)
       ├─ TushareAdapter (默认)
       ├─ AkShareAdapter (可选)
       └─ CSVAdapter (可选，本地文件)
```

无论底层 API 返回什么列名/格式，适配器归一化为 canonical format。用户只需配置用哪个 adapter。

### 2.4 Pi 工具哲学 — 最小完备工具集

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
| `market_ohlcv(symbol, period)` | 领域核心 | 眼睛 | 内核数据原语，adapter pattern |
| `recall(query)` | 领域增强 | 回忆 | 全文搜索 memory + notebook |

#### 为什么不是 15 个工具

notebook.write 就是 `write("notebook/xxx.md", content)`。
memory.write 就是 `write("memory/xxx.md", content)`。
不需要单独的工具。

read/write/edit 的覆盖范围：
- 写研究报告 → `write("notebook/research/宁德时代/2024-01-15.md", content)`
- 更新信念 → `edit("memory/beliefs.md", "旧信念", "新信念+理由")`
- 修改灵魂 → `edit("soul.md", ...)` → 触发权限检查
- 读取历史研究 → `read("notebook/research/宁德时代/2024-01-15.md")`
- 自举工作区 → `write("soul.md", "# 我是谁\n...")`

#### 领域工具的不可替代性

`market.ohlcv` 不能用 read/write 替代——它需要 MarketAdapter 归一化 + canonical 格式契约 + OHLCV→DataStore→compute 预连通管道。

`recall` 不能用 read 替代——它需要全文索引跨越 memory/ + notebook/ 所有文件。

`compute` 不能用 bash 替代——它需要沙箱隔离 + OHLCV 自动注入 + Trading Coreutils 预装。

### 2.5 预连通管道 — 神经系统

内核保证以下数据流自动发生，LLM 不需要手动搬运：

| 数据流 | 仿生类比 | 触发条件 | 内核行为 |
|--------|---------|---------|---------|
| soul.md → 上下文 | 性格塑造思维 | 每轮 Turn 开始 | 自动注入 soul.md 到 system prompt |
| beliefs → 上下文 | 信念影响判断 | 每轮 Turn 开始 | 注入 beliefs.md 摘要 |
| MEMORY.md → 上下文 | 记忆索引 | 每轮 Turn 开始 | 注入索引前 N 行 |
| OHLCV → compute | 眼睛看到 → 大脑可用 | compute 调用时 | 自动将最近 market.ohlcv 结果注入执行环境 |
| notebook 写入 → memory 索引 | 写完笔记 → 记得写过 | write notebook/ 完成后 | MEMORY.md 索引自动更新 |
| beliefs 变更 → reflections | 信念变化 → 记录成长 | beliefs.md 被修改时 | 自动记录变更日志（之前→现在→原因） |

### 2.6 成长是第一公民

成长不是可选 skill，是内核支撑的核心循环：

```
感知 ──→ 思考 ──→ 行动 ──→ 记录 ──→ 反思 ──→ 成长
 │        │        │        │        │        │
 eyes    brain    hands   memory   diary    soul
 market   LLM   notebook  obser-  reflec-  beliefs
 .ohlcv          .write   vations  tions   soul.md
```

#### 自我修改的层级与权限

| 可修改项 | 修改方式 | 确认要求 |
|---------|---------|---------|
| tracking.md | agent 自由修改 | 无（开始关注新标的 = 低风险） |
| observations/ | agent 自由写入 | 无（记录事实） |
| reflections/ | agent 自由写入 | 无（私人日记） |
| beliefs.md | agent 修改需说明理由 | 无（但需记录"之前→现在→原因"） |
| preferences.md | 需用户确认 | 是（改变投资风格是大事） |
| soul.md | 需用户确认 | 是（改变人格需教练同意） |

这个层级反映人类自我修改的自然规律：你随时可以关注一只新股票（tracking），但你的核心价值观（soul）轻易不变——除非教练明确指导。

#### 用户作为教练

用户不只是"命令发出者"，更是"成长教练"：

```
"你对科技股太乐观了"
  → reflections/ 记录反馈
  → beliefs.md 更新（需说明理由）
  → 后续分析科技股时自动加入审慎评估

"以后分析前先看大盘趋势"
  → 可能固化为 skill 的步骤调整
  → 或更新 soul.md 的"我的风格"（需确认）

"这次分析得好，保持这个深度"
  → reflections/ 记录正反馈
  → 强化当前分析模式
```

### 2.7 设计原则

1. **仿生学设计**：每个模块对应人体器官，数据流模拟神经反射弧
2. **领域驱动的通用设计**：用投资需求塑形抽象，但抽象本身不绑定领域
3. **OHLCV 即原语**：内核定义 canonical 数据格式，保证全系统互操作
4. **预连通优于手动编排**：器官之间的数据流是内核预设的，LLM 不需要手动搬运数据
5. **成长是第一公民**：感知→思考→行动→记录→反思→成长，这个循环是内核支撑的
6. **内核极小化**：内核只提供稳定原语与预连通管道；功能通过 skills 组合扩展
7. **渐进式上下文**：默认注入索引/摘要；需要时再加载细节，避免上下文膨胀
8. **安全默认拒绝**：高风险动作、灵魂修改默认需要显式确认
9. **可审计**：关键决策、灵魂/信念变更、工具调用都有事件日志可追溯
10. **渠道无关**：Telegram/CLI 都是适配器；会话、任务、skills 的语义一致

#### 关键取舍

以下做法短期看起来"更完整"，但会把系统做死：

- **把所有金融数据都做进内核**：内核膨胀，维护成本指数上升。替代：只有 OHLCV 进内核；其他数据通过 Tool Provider 注册。
- **把风控引擎做进内核**：定位偏移为交易系统。替代：个人投资助手不做自动交易，风控不是内核关切。
- **把成长循环做成 skill**：成长变成可选的，大多数用户不会主动启用。替代：成长循环是内核行为。

---

## 三、核心架构

### 3.1 Kernel-centric 设计

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

**没有 Brain 类**。ReAct loop 是 Kernel.turn() 的 30 行。
**没有 if/elif 管道**。管道通过 wire/emit + 路径模式驱动。

### 3.2 声明式管道 — wire/emit + fnmatch

整个系统的行为 = 一组声明式的路径模式规则。零 if/elif。

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

### 3.3 一次 Turn 的数据流

```
input → Kernel.turn(input, session)
         │
         ├─ 1. emit("turn.start") → 注入 soul + beliefs + memory_index
         ├─ 2. context assemble(session.history, input) → messages
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

### 3.4 自举 — Self-bootstrapping

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

### 3.5 关键接口

```python
class Kernel:
    """唯一协调中心：ReAct loop + 管道 + 数据 + 权限"""
    data: DataStore
    def boot(self, workspace: Path)
    def turn(self, input: str, session: Session) -> str
    def wire(self, pattern: str, handler: Callable)
    def emit(self, event: str, data: Any)
    def permission(self, pattern: str, level: Permission)
    def tool(self, name: str, description: str, parameters: dict, handler: Callable)

class DataStore:
    """内核数据注册表"""
    def set(self, key: str, data: Any)
    def get(self, key: str) -> Any | None

class Session:
    """会话容器"""
    history: list[dict]
    def save(self, path: Path)
    @classmethod def load(cls, path: Path) -> Session
    def repair(self)  # 修复崩溃后残缺历史

class MarketAdapter(Protocol):
    """数据源适配器接口"""
    name: str
    def fetch(self, symbol: str, period: str,
              start: str | None, end: str | None) -> pd.DataFrame

class Permission(Enum):
    FREE = "free"                    # agent 自由操作
    REASON_REQUIRED = "reason_required"  # 需说明理由
    USER_CONFIRM = "user_confirm"    # 需用户确认
```

---

## 四、器官设计

### 4.1 Soul — 灵魂系统

Soul 不是配置文件，是 agent 的**存在方式**。

Soul 不只决定输出语气，而是决定**分析路径**：

```
同一个问题："宁德时代值得买吗？"

价值投资 soul → 先看 PE/PB/ROE/自由现金流，再看行业地位
趋势交易 soul → 先看均线系统/动量/成交量，再看板块轮动
量化分析 soul → 先用 compute 算多因子得分，再看统计显著性
```

修改规则：Soul 轻易不变。修改需用户（教练）确认。

### 4.2 Eyes — 市场感知（market.ohlcv）

```python
class MarketAdapter(Protocol):
    name: str
    def fetch(self, symbol: str, period: str,
              start: str | None, end: str | None) -> pd.DataFrame
```

默认适配器：TushareAdapter（A 股日线 OHLCV）。用户可替换。

### 4.3 Calculator — 计算能力（compute）

compute 的执行环境中，以下变量自动可用（预连通管道）：

```python
# 数据（由内核从最近 market.ohlcv 结果注入）
df          # 完整 OHLCV DataFrame
open, high, low, close, volume, date  # Series

# 库
pd, np, ta, math

# Trading Coreutils（Default Profile 预装）
latest(), prev(), crossover(), crossunder(), bbands(), macd()
```

这是区别于通用 agent 的核心特性：

```
通用 agent：
  用户："帮我算宁德时代的 RSI"
  Agent：先写代码获取数据，解析 JSON，转 DataFrame，再算 RSI
  → 大量样板代码，LLM 容易出错

这个 agent：
  用户："帮我算宁德时代的 RSI"
  Agent：
    1. market.ohlcv("300750") → canonical OHLCV
    2. compute("ta.rsi(close, 14)")  ← OHLCV 自动注入
  → 一行代码搞定
```

安全边界：eval-first 策略 / 黑名单 builtins / 无网络 / SIGALRM 超时 / 输出自动序列化。

### 4.4 Notebook vs Memory

```
Notebook = 你写的东西（外化，桌上的笔记本）
Memory   = 你记住的东西（内化，脑子里的信念和经验）

流动方向：
  Notebook → Memory：写完研究后，关键结论内化为 belief
  Memory → Notebook：基于记忆和信念，产出新的研究

反例：
  "宁德时代 Q3 产能利用率分析报告" → notebook（产物）
  "宁德产能利用率在下降，这是个风险" → memory/beliefs（内化认知）
```

#### Memory 品类

| 品类 | 文件 | 内容 | 写入时机 |
|------|------|------|---------|
| 索引 | MEMORY.md | 记忆与产物的总目录 | 自动维护 |
| 偏好 | preferences.md | 投资风格、风险态度 | 用户明确表达 |
| 关注 | tracking.md | 追踪中的标的、主题 | 用户/agent 添加 |
| 信念 | beliefs.md | 经验证的认知 | 分析/反思后确认 |
| 观察 | observations/ | 时间标记的市场观察 | 每次分析后 |
| 反思 | reflections/ | 复盘日记，教训与成长 | 定期/用户触发 |

### 4.5 Scheduler — 任务调度

核心交互（先设计后确认）：
1. 用户用自然语言描述意图
2. Agent 生成"任务设计稿"（触发条件、频率、输入、产物、通知、失败策略）
3. 用户确认后才落地为 Task

任务类型：定时（cron/interval）、事件（消息关键词/文件变更/webhook）。
输出策略：默认写入 notebook + 发送摘要；支持静默任务。

### 4.6 Skills — 技能系统

#### Tool 来源层次

```
1. 内核内置 — 需要内核级集成（安全/状态/预连通），不可外部提供
   market.ohlcv    适配器归一化 + canonical format
   compute         沙箱安全 + OHLCV 自动注入
   read/write/edit 与 memory 索引预连通 + 权限检查

2. Tool Provider 注册 — 外部模块向内核注册工具，LLM 可直接调用
   tushare.financial    财务数据（非 OHLCV，不进内核）
   web.search           网络搜索
   任何第三方...         用户自己接入的 API

3. Skill 编排 — 工作流，不提供新能力，只组织已有工具
   /research     调 market.ohlcv + compute + write + recall
   /review       调 recall + read + compute
```

**判断标准**：需要内核级集成？→ 内核内置。提供新原子能力？→ Tool Provider。编排已有工具？→ Skill。

#### 默认技能包

| 技能 | 命令 | 工作流 |
|------|------|--------|
| 研究 | `/research {topic}` | market.ohlcv → compute 指标 → 结合 memory → notebook 写分析笔记 |
| 复盘 | `/review {period}` | 回顾 observations/reflections → 生成复盘报告 |
| 扫描 | `/scan {criteria}` | compute 批量筛选 → notebook 写扫描结果 |
| 对比 | `/compare {a} {b}` | 两个标的并排对比分析 |

### 4.7 Subagent — 子代理

目的：并行研究加速、高不确定任务隔离。

约束：
- 子代理**继承 soul 的核心约束**（边界和禁忌），但不继承完整灵魂
- 子代理上下文更少（最小泄露）
- 子代理工具更少（最小风险）
- 子代理输出必须可汇总（结构化要点 + 指向 notebook 产物）

### 4.8 Tool Provider — 外部能力注册

```
Tool Provider ≠ Skill
  Provider = 提供新的原子能力（"我能查财务数据"）
  Skill    = 编排已有能力成工作流（"怎么做一份研究报告"）
```

---

## 五、Workspace 设计

```
soul.md                          ← 灵魂（人格/风格/边界/成长方向）

memory/                          ← 记忆（内化认知）
  MEMORY.md                      ← 索引（内核自动维护）
  preferences.md                 ← 偏好
  tracking.md                    ← 关注列表
  beliefs.md                     ← 信念
  observations/                  ← 观察记录
  reflections/                   ← 反思日记

notebook/                        ← 笔记本（外化产物）
  research/                      ← 深度研究
  reports/                       ← 周期报告
  scratch/                       ← 草稿
```

### 三区的生命周期差异

| 区域 | 性质 | 修改频率 | 修改权限 |
|------|------|---------|---------|
| soul.md | 人格身份 | 极少变 | 需用户确认 |
| memory/ | 内化认知 | 渐进积累 | 分层级 |
| notebook/ | 外化产物 | 自由写入 | agent 自由 |

**铁律**：soul.md 可以被删除后 agent 仍能启动（只是没有人格），memory 可以被清空后 agent 仍能运行（只是没有记忆），notebook 可以被清空后 agent 仍能工作（只是没有历史产物）。任何区域都不是启动的硬依赖。

---

## 六、Default Profile

Default Profile 是介于内核和 Skills 之间的**发行版预设**。它决定了 agent 开箱即用的样子。

| 组件 | 内容 |
|------|------|
| soul.md 模板 | 个人投资研究助手人格 |
| memory 默认结构 | preferences/tracking/beliefs/observations/reflections |
| notebook 默认目录 | research/ + reports/ + scratch/ |
| 默认 MarketAdapter | TushareAdapter |
| 默认 Skills 包 | /research、/review、/scan、/compare |
| compute 预装 | pandas + pandas-ta + Trading Coreutils |

### 可替换性

换一个 Default Profile，同一个内核就变成不同的助手：

```
投资助手 Profile  → soul: 价值投资, adapter: tushare, skills: research/review
项目管理 Profile  → soul: GTD方法论, adapter: 无, skills: plan/track/report
学习助手 Profile  → soul: 费曼学习法, adapter: 无, skills: explain/quiz/review
```

内核不变，Profile 可以独立分发和安装。

**铁律**：Profile 中的任何文件都可以被删除，agent 仍能启动和运行。Profile 是"预设"，不是"依赖"。

---

## 七、关键用户旅程

### 旅程 A：投资研究（多工具自动编排）

```
用户："帮我看看宁德时代最近怎么样"

Agent 自动编排：
  1. market.ohlcv("300750") → 获取近期行情
  2. compute("ta.rsi(close, 14)") → 计算 RSI（OHLCV 自动注入）
  3. recall("宁德时代") → 找到历史研究和观察
  4. 综合分析，生成结构化观点（数据 + 推理 + 置信度）
  5. write("notebook/research/宁德时代/2024-01-15.md") → 保存研究笔记
  6. write("memory/observations/2024-01-15-宁德时代.md") → 记录观察
  7. 对话中返回摘要 + 关键结论
```

### 旅程 B：教练指导成长

```
用户："你最近总是低估市场情绪的影响，分析时要多考虑资金面。"

Agent 行为：
  1. write("memory/reflections/...") → 记录教练反馈
  2. 提议修改 beliefs.md → "增加：市场情绪和资金面对短期走势有显著影响"
  3. 提议修改 soul.md 成长方向 → 等待用户确认
  4. 用户确认后 → 后续分析自动包含资金面评估
```

### 旅程 C：定时复盘（先设计后确认）

```
用户："每周五收盘后，帮我复盘本周的观察和判断。"

Agent 输出任务设计稿：
  - 频率：每周五 16:00
  - 输入：memory/observations/ 本周条目 + memory/tracking.md
  - 产物：notebook/reports/weekly/YYYY-MM-DD.md
  - 通知：发送摘要到 IM
  - 失败策略：延迟 1h 重试，失败则通知

用户："确认执行。"
→ 系统创建 Task；每次触发生成周报 + 更新 reflections/
```

### 旅程 D：显式调用 skill

```
用户："/compare 比亚迪 vs 宁德时代"

/compare skill 运行：
  1. 分别获取两个标的的 OHLCV
  2. compute 计算对比指标
  3. 结合 memory 中的历史研究
  4. 生成 notebook/research/比亚迪-vs-宁德时代/2024-01-15.md
  5. 返回摘要 + 关键对比结论
```

---

## 八、功能需求清单

> 代码变更时同步更新状态。✅ 已实现 / ⚠️ 部分实现 / ❌ 未实现

### 内核

| 功能 | 状态 | 说明 |
|------|------|------|
| Kernel ReAct loop | ✅ | turn() 30 行，max_rounds 保护 |
| wire/emit 声明式管道 | ✅ | fnmatch 模式匹配 |
| DataStore | ✅ | key-value 注册表 |
| Permission 权限系统 | ✅ | 3 级 + fnmatch |
| Session 持久化 | ✅ | JSON save/load + repair |
| 自举（boot） | ✅ | soul + beliefs + memory_index 注入 |
| Per-turn 上下文刷新 | ❌ | 当前 boot 时固化，会话中变更不感知 |
| Observation Masking | ❌ | 长对话 tool result 压缩 |

### 6 工具

| 工具 | 状态 | 说明 |
|------|------|------|
| read | ✅ | 读文件 + 列目录 |
| write | ✅ | 写文件 + 权限检查 + emit |
| edit | ✅ | diff-based 修改 + 权限检查 + emit |
| compute | ✅ | 沙箱 + OHLCV 自动注入 |
| market_ohlcv | ✅ | MarketAdapter + DataStore |
| recall | ⚠️ | 简单文本匹配（设计目标 FTS5） |

### 预连通管道

| 管道 | 状态 | 说明 |
|------|------|------|
| soul → 上下文 | ✅ | boot 时注入 |
| beliefs → 上下文 | ✅ | boot 时注入 |
| MEMORY.md → 上下文 | ✅ | boot 时注入前 30 行 |
| OHLCV → compute | ✅ | DataStore 自动注入 |
| notebook write → MEMORY.md 索引 | ❌ | handler 未实现 |
| beliefs 变更 → reflections 记录 | ❌ | handler 未实现 |

### 适配器

| 功能 | 状态 | 说明 |
|------|------|------|
| CLI adapter | ✅ | 完整生命周期 |
| TushareAdapter | ✅ | A 股日线 OHLCV |
| CsvAdapter | ✅ | 测试用 |
| Telegram adapter | ❌ | |
| Adapter 公共 Setup | ❌ | 工具注册/权限/管道逻辑提取 |

### 高级能力

| 功能 | 状态 | 说明 |
|------|------|------|
| Scheduler | ❌ | APScheduler 定时任务 |
| Skill Engine | ❌ | 技能发现/加载/执行 |
| Subagent Runner | ❌ | fork 上下文 + 汇总 |
| Tool Provider Registry | ❌ | 外部工具注册 |
| 成长循环 | ❌ | 定时反思 → belief 更新 → soul 微调 |

### 权限粒度

| 功能 | 状态 | 说明 |
|------|------|------|
| soul.md → USER_CONFIRM | ✅ | |
| notebook/** → FREE | ✅ | |
| memory/** 分层权限 | ❌ | 当前全 FREE，应按品类分级 |

### 可观测性

| 功能 | 状态 | 说明 |
|------|------|------|
| JSONL trace | ✅ | wire/emit 零侵入 |
| 产物可追溯 | ❌ | MEMORY.md 索引自动维护 |
| 成长可追溯 | ❌ | beliefs 变更历史 |

---

## 九、安全与合规

1. **IM 输入默认不可信**：必须有 prompt injection 防护与规则优先级
2. **灵魂修改强确认**：soul.md 和 preferences.md 的修改需用户确认
3. **信念变更可审计**：beliefs.md 的每次修改自动记录到 reflections/，含变更理由
4. **权限最小化**：skills 声明 allowed-tools；未声明不得调用高风险工具
5. **审计与可追溯**：任务触发、工具调用、关键决策、灵魂/信念变更都产生事件日志

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
