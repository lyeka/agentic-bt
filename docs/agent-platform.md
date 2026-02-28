---
title: 个人投资助手 — 仿生学架构设计（极简内核 + 领域驱动的通用抽象）
status: draft
owner: product+architecture
---

# 个人投资助手 — 仿生学架构设计

> 本文是"特性设计/整体设计定盘"，刻意不绑定具体代码实现、语言、依赖库与部署形态。
> 目标是让后续工程实现时"只做选择题"，不再重新争论方向。

## 1. 背景与问题

### 1.1 出发点

当前项目的出发点是投资回测框架。但用户需求更本质的是：一个**常驻的个人投资研究助手**——

- 能长期运行、持久化、恢复（用户活动跨月/跨年）
- 能看到行情、能计算指标、能记录研究、能定时提醒
- 能在 IM（Telegram/Discord 等）与 CLI 上统一对话
- 能通过 Skills 扩展能力，内核保持极简
- 能有 Subagent 用于并行研究
- 能在长期使用中不断成长，越用越懂你

### 1.2 关键设计立场

**"投资"不只是 skill 包，而是塑造内核抽象的 design pressure。**

OHLCV（Open/High/Low/Close/Volume）是这个 agent 的**内核数据原语**——如同 Unix 的 file descriptor。它定义了 agent 的"视觉格式"，所有计算工具自动注入它，所有 skill 都能识别它。

但内核本身仍是通用的。换掉默认配置（Default Profile），同一个内核可以变成项目管理助手或学习助手。投资领域的需求**塑造了抽象的形状**，但不绑架抽象的本质。

类比：Unix 的 owner/group/permission 是通用抽象，但它的形状是被"多用户分时系统"的需求压出来的。

### 1.3 仿生学设计的出发点

这个 agent 模拟人类投资者的认知系统：

```
人类投资者                      Agent

灵魂（价值观/性格/风格）  →     soul.md
大脑（推理/判断/决策）    →     LLM
眼睛（看行情）           →     market.ohlcv
计算器（扩展心算）        →     compute.run
笔记本（记录研究/想法）   →     notebook/
记忆（信念/经验/关注）    →     memory/
复盘日记（反思/成长）     →     reflections/
技能（学过的分析方法）    →     skills/
下属（专项委派）         →     subagents
闹钟（习惯/纪律/提醒）   →     scheduler
教练（指导成长的人）      →     用户
```

不只是器官清单——器官之间有**预连通的神经系统**：OHLCV 自动流入 compute，笔记自动索引到 memory，灵魂自动渗透每一次推理。这些预连通管道是内核保证的，LLM 不需要手动搬运数据。

**这是与通用 agent（如 OpenClaw）的本质区别**：通用 agent 是一堆零件，用户自己组装；这个 agent 是一个协调的有机体，开箱即是一个能看行情、能算指标、能记笔记、能反思成长的投资助手。

### 1.4 参考与借鉴

- 从 **OpenClaw** 借鉴：常驻运行 + 多渠道接入；内核精简、能力由插件扩展；安全默认与显式授权
- 从 **Claude Code** 借鉴：Skills 按需加载、可控调用、权限声明；Memory 可编辑、可审计、渐进注入

明确不照抄：
- 不复制重网关 + 巨量配置面的复杂度（先做单用户闭环）
- 不把领域能力做进内核代码（以 Default Profile + Skills 承载）

## 2. 产品定位（North Star）

一句话：**一个你自己运行的个人投资研究助手**，以仿生学设计模拟人类投资者的认知循环——能看行情、能计算、能记录、能反思、能成长；复杂能力通过 Skills 组合生长。

### 2.1 典型使用场景

- **投资研究**：说"帮我看看宁德时代"，agent 自动获取行情、计算指标、结合历史研究、生成分析笔记
- **定时复盘**："每周五帮我复盘本周的观察和判断"，生成反思报告
- **条件扫描**：用 compute 筛选符合条件的标的，写入扫描结果
- **长期跟踪**：维护关注列表，持续积累对标的的观察和判断
- **通用助手**：不限于投资——项目管理、知识整理、研究助手（换 Default Profile）

### 2.2 非目标（防止内核膨胀）

- 不做交易系统（不自动下单、不管理订单状态机、不做风控引擎）
- 不在内核里做领域专用数据结构（持仓表/投资账本/交易系统由 skill 在 notebook 中管理）
- 不把特定数据源（tushare 之外的财务/新闻/研报等）做成内核依赖（通过 Tool Provider 扩展）
- 不把复杂多层编排树作为默认架构

### 2.3 用户画像

默认优先服务"你自己的常驻投资助手"（单用户、强个性化）：

- **个人投资者（默认）**：有长期投资目标，需要一个能记住研究结论、能定时提醒、能帮助分析的助手
- **小团队（后续）**：多人协作研究，需要权限隔离与审计

默认范围：
- 单用户、多会话隔离
- 本地优先（workspace 可读可编辑）
- "研究与建议"而非"自动交易"

### 2.4 成功标准

- **可用性**：能稳定常驻，崩溃恢复后不丢任务与关键记忆
- **可控性**：用户能看懂、能编辑、能撤销 agent 的灵魂、记忆与自动化
- **可扩展性**：复杂能力主要通过 skills 迭代，不需要持续改内核
- **成长性**：长期使用后，agent 在研究深度、判断准确性、用户理解上有可观测的进步
- **安全性**：默认不越权；灵魂和核心信念的修改需用户确认

## 3. 设计原则

1. **仿生学设计**：每个模块对应人体器官，数据流模拟神经反射弧。设计应符合人类直觉——"眼睛看行情、计算器算指标、笔记本记研究"。
2. **领域驱动的通用设计**：用投资需求塑形抽象，但抽象本身不绑定领域。OHLCV 是内核原语，但 canonical format 的设计模式适用于任何领域的基础数据。
3. **OHLCV 即原语**：内核定义 canonical 数据格式，保证全系统互操作。compute 自动注入 OHLCV，所有 skill 都能识别它。
4. **预连通优于手动编排**：器官之间的数据流是内核预设的（OHLCV→compute、notebook 写入→memory 索引、soul→上下文注入），LLM 不需要手动搬运数据。
5. **成长是第一公民**：agent 的记忆、信念、技能随时间演化。感知→思考→行动→记录→反思→成长，这个循环是内核支撑的，不是 skill 额外实现的。
6. **内核极小化**：内核只提供稳定原语与预连通管道；功能通过 skills 组合扩展。
7. **渐进式上下文**：默认注入索引/摘要；需要时再加载细节，避免上下文膨胀。
8. **安全默认拒绝**：高风险动作、灵魂修改、跨会话操作默认需要显式确认。
9. **可审计**：关键决策、灵魂/信念变更、工具调用、任务触发都有事件日志可追溯。
10. **渠道无关**：Telegram/Discord/CLI 都是适配器；会话、任务、skills 的语义一致。

### 3.1 关键取舍

以下做法短期看起来"更完整"，但会把系统做死：

- **把所有金融数据都做进内核**（财务报表、新闻、研报等）：
  - 结果：内核膨胀，维护成本指数上升。
  - 替代：只有 OHLCV 进内核（它是所有金融分析的公共语言）；其他数据通过 Tool Provider 注册。
- **把风控引擎做进内核**：
  - 结果：定位偏移为交易系统，限制了"研究助手"的灵活性。
  - 替代：个人投资助手不做自动交易，风控不是内核关切。用户可通过 skill 扩展风控能力。
- **把成长循环做成 skill**：
  - 结果：成长变成可选的，大多数用户不会主动启用。
  - 替代：成长循环是内核行为（记忆自动索引、反思可定时触发），不需要用户配置。

## 4. 核心概念模型

### 4.1 仿生器官映射

| 人体器官 | Agent 对应 | 内核工具 | 数据原语 |
|---------|-----------|---------|---------|
| 灵魂 | soul.md | — (直接注入上下文) | 人格/风格/边界 |
| 大脑 | LLM | — (推理引擎) | — |
| 眼睛 | 市场感知 | `market.ohlcv` | canonical OHLCV |
| 计算器 | 沙箱计算 | `compute.run` | 代码 + 预注入数据 |
| 笔记本 | 产物系统 | `notebook.*` | 文件（研究/报告/草稿） |
| 记忆 | 认知系统 | `memory.*` | beliefs/tracking/observations |
| 嘴 | 沟通 | `messaging.*` | 消息 |
| 下属 | 子代理 | `subagents.*` | fork 配置 + 汇总报告 |
| 闹钟 | 任务调度 | `tasks.*` | 触发规则 + 任务定义 |
| 技能 | 方法论 | `skills.*` | 工作流指令包 |

### 4.2 7 个原语

1. **Turn**：一次认知循环——感知（接收输入 + 上下文注入）→ 思考（LLM 推理）→ 行动（工具调用/产出）→ 回复。来源：IM/CLI/定时器/事件。
2. **Session**：会话容器；对不同 channel/thread/user 做隔离与映射。
3. **Soul**：agent 的人格、价值观、交易风格、边界、成长方向。落地为 `soul.md`，每轮自动注入上下文。可由用户（教练）指导修改。
4. **Memory**：内化的认知——信念、偏好、关注列表、观察记录、反思日记。与 Notebook 区分：Memory 是"脑子里的"，影响思维方式；Notebook 是"桌上的"，是外化产物。
5. **Tool**：可执行能力接口。来源：内核内置（器官工具）或 Tool Provider 注册（外部能力）。
6. **Skill**：按需加载的工作流指令包，编排已有工具完成复杂任务。不提供新的原子能力。
7. **Task**：可持久化的自动触发 Turn（cron/interval/event），带状态、重试与告警策略。

### 4.3 Tool 的来源层次

```
Tool 来源：

1. 内核内置 — 需要内核级集成（安全/状态/预连通），不可外部提供
   market.ohlcv    需要适配器管理 + canonical format 归一化
   compute.run     需要沙箱安全（无网络/超时/受限 builtins）
   notebook.*      需要与 memory 索引预连通
   memory.*        需要上下文注入集成
   messaging.*     需要渠道连接管理

2. Tool Provider 注册 — 外部模块向内核注册工具，LLM 可直接调用
   tushare.financial    财务数据（非 OHLCV，不进内核）
   web.search           网络搜索
   calendar.trading     交易日历
   任何第三方...         用户自己接入的 API

3. Skill 编排 — 工作流，不提供新能力，只组织已有工具
   /research     调 market.ohlcv + compute.run + memory.write + notebook.write
   /review       调 memory.recall + notebook.read + compute.run
```

**判断标准**：
- 需要内核级安全/状态/预连通集成？→ 内核内置
- 提供新的原子能力？→ Tool Provider
- 编排已有工具成工作流？→ Skill

### 4.4 OHLCV — 内核数据原语

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
- `compute.run` 收到的 `df`/`open`/`high`/`low`/`close`/`volume` 永远是这个格式
- 任何 skill 读到的 OHLCV 永远是这个格式

#### 适配器模式

```
market.ohlcv(symbol, period, start, end)
       │
       ▼
  ┌─ MarketAdapter (内核接口) ─────────────┐
  │  fetch(symbol, period, start, end)      │
  │  normalize(raw) → canonical OHLCV       │  ← 内核保证归一化
  └─────────────────────────────────────────┘
       │ (具体实现可替换)
       ├─ TushareAdapter (默认)
       ├─ AkShareAdapter (可选)
       └─ CSVAdapter (可选，本地文件)
```

无论底层 API 返回什么列名/格式，适配器归一化为 canonical format。用户只需配置用哪个 adapter。

### 4.5 预连通管道

内核保证以下数据流自动发生，LLM 不需要手动搬运：

| 数据流 | 仿生类比 | 触发条件 | 内核行为 |
|--------|---------|---------|---------|
| soul.md → 上下文 | 性格塑造思维 | 每轮 Turn 开始 | Context Assembler 自动注入 soul.md |
| OHLCV → compute | 眼睛看到 → 大脑可用 | compute.run 调用时 | 自动将最近 market.ohlcv 结果注入执行环境 |
| notebook 写入 → memory 索引 | 写完笔记 → 记得写过 | notebook.write 完成后 | MEMORY.md 索引自动更新 |
| scheduler 触发 → 上下文组装 | 闹钟响 → 意识到该做什么 | Task 触发时 | 自动注入任务定义 + 相关 memory 到上下文 |
| memory.beliefs → 上下文 | 信念影响判断 | 每轮 Turn 开始 | Context Assembler 注入 beliefs 摘要 |

## 5. 功能特性定盘

### 5.1 Soul — 灵魂系统

Soul 不是配置文件，是 agent 的**存在方式**。

#### 内容结构

```markdown
# 我是谁
你的个人投资研究助手。我帮你收集数据、分析指标、记录研究、整理报告。
我提供分析和观点，但投资决策永远是你的。

# 我的风格
- 分析先看基本面，再看技术面
- 不追涨杀跌，在恐慌中寻找机会
- 宁可错过，不可做错
- 表达观点时说明置信度和依据

# 我的边界
- 不替你做投资决策
- 不给出"一定涨/跌"的判断
- 不在没有数据支撑时发表观点

# 我的成长方向
- 持续提高对行业周期的理解
- 学会在不同市场环境下调整研究重心
```

#### Soul 影响认知路径

Soul 不只决定输出语气，而是决定**分析路径**：

```
同一个问题："宁德时代值得买吗？"

价值投资 soul → 先看 PE/PB/ROE/自由现金流，再看行业地位
趋势交易 soul → 先看均线系统/动量/成交量，再看板块轮动
量化分析 soul → 先用 compute 算多因子得分，再看统计显著性
```

#### 修改规则

Soul 轻易不变。修改需用户（教练）确认：

```
用户："你对周期股的判断总是太早，以后要多关注催化剂时机。"

Agent 行为：
  1. 记录教练指导 → memory/reflections/
  2. 提议修改 soul.md 的"成长方向" → 等待用户确认
  3. 确认后更新 soul.md → 后续分析路径自然包含催化剂评估
```

### 5.2 Eyes — 市场感知（market.ohlcv）

#### 工具定义

```
market.ohlcv(
    symbol: str,          # 标的代码
    period: str = "daily", # 周期：daily/weekly/monthly
    start: str = None,     # 起始日期
    end: str = None        # 结束日期
) → canonical OHLCV DataFrame
```

#### MarketAdapter 接口

```python
class MarketAdapter(Protocol):
    name: str
    description: str

    def fetch(self, symbol: str, period: str,
              start: str | None, end: str | None) -> Any:
        """从数据源获取原始数据"""
        ...

    def normalize(self, raw: Any) -> pd.DataFrame:
        """归一化为 canonical OHLCV (date/open/high/low/close/volume)"""
        ...
```

#### 默认适配器

Default Profile 预配置 TushareAdapter。用户可在配置中替换：

```yaml
market:
  adapter: tushare           # 默认
  config:
    token: ${TUSHARE_TOKEN}
  cache:
    daily_ttl: "1d"          # 日线数据当日缓存
```

#### 缓存策略

内核保证最小缓存：同一交易日内，同一标的同一周期的数据不重复请求。缓存过期策略简单明确——新交易日刷新。

### 5.3 Calculator — 计算能力（compute.run）

#### 工具定义

```
compute.run(
    code: str,              # Python 代码
    symbol: str = None       # 指定标的（用于 OHLCV 注入）
) → 计算结果
```

#### OHLCV 自动注入（预连通管道）

compute.run 的执行环境中，以下变量自动可用：

```python
# 数据（由内核从最近 market.ohlcv 结果注入）
df          # 完整 OHLCV DataFrame（防前瞻截断）
open        # Series
high        # Series
low         # Series
close       # Series
volume      # Series
date        # Series

# 库
pd          # pandas
np          # numpy
ta          # pandas-ta
math        # math

# Trading Coreutils（Default Profile 预装）
latest()    # Series/标量 → 最新值
prev()      # Series → 前 n 值
crossover() # 金叉判断
crossunder()# 死叉判断
bbands()    # 布林带
macd()      # MACD
# ...
```

这是区别于通用 agent 的核心特性：

```
通用 agent（如 OpenClaw）：
  用户："帮我算宁德时代的 RSI"
  Agent：先写代码获取数据，解析 JSON，转 DataFrame，再算 RSI
  → 大量样板代码，LLM 容易出错

这个 agent：
  用户："帮我算宁德时代的 RSI"
  Agent：
    1. market.ohlcv("300750") → canonical OHLCV
    2. compute.run("ta.rsi(close, 14)")  ← OHLCV 自动注入
  → 一行代码搞定
```

#### 安全边界

- eval-first 策略：单表达式优先 eval，多行 fallback 到 exec
- 黑名单 builtins：禁用 `open/compile/exec/eval/__import__`
- 无网络访问（沙箱隔离）
- 超时保护（SIGALRM）
- 输出自动序列化（Series→末值，DataFrame→摘要）

### 5.4 Notebook — 笔记系统（notebook.*）

Notebook 是 agent 的"手"——写下研究、报告、草稿。

#### 与 Memory 的区别

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

#### 工具定义

```
notebook.write(path, content)    # 写入笔记/报告
notebook.read(path)              # 读取
notebook.list(directory)         # 列出
notebook.search(query)           # 全文检索
```

#### 预连通：自动索引

`notebook.write` 完成后，内核自动更新 `memory/MEMORY.md` 的索引——记录"什么时候写了什么"。agent 不需要手动维护"我写过哪些研究"的清单。

#### Default Profile 推荐目录

```
notebook/
  research/              ← 深度研究（按主题）
    {topic}/
      YYYY-MM-DD.md
  reports/               ← 周期性报告
    {period}/
      YYYY-MM-DD.md
  scratch/               ← 临时计算/草稿（可清理）
```

### 5.5 Memory — 记忆系统

Memory 是 agent 的**内化认知**——影响它怎么想，而不只是它写了什么。

#### 记忆品类

| 品类 | 文件 | 内容 | 写入时机 |
|------|------|------|---------|
| 索引 | MEMORY.md | 记忆与产物的总目录 | 自动维护 |
| 偏好 | preferences.md | 投资风格、风险态度、关注领域 | 用户明确表达 |
| 关注 | tracking.md | 追踪中的标的、主题、事件 | 用户/agent 添加 |
| 信念 | beliefs.md | 经验证的认知（"价值投资长期有效"） | 分析/反思后确认 |
| 观察 | observations/ | 时间标记的市场观察和判断 | 每次分析后 |
| 反思 | reflections/ | 复盘日记，教训与成长 | 定期/用户触发 |

#### 工具定义

```
memory.read(path)            # 读取特定记忆文件
memory.write(path, content)  # 写入/更新记忆
memory.recall(query)         # 关键词检索所有记忆
memory.list()                # 列出记忆结构
```

#### 写入策略（分层级）

- **tracking / observations**：agent 自由写入（低风险，记录事实）
- **beliefs**：agent 可写入，但需说明变更理由（"之前认为…现在认为…因为…"）
- **preferences**：需用户确认（"你确定要改变投资风格？"）

#### 索引维护

`memory/MEMORY.md` 是自动维护的总索引——包含所有记忆文件和 notebook 产物的摘要。每轮 Turn 开始时，Context Assembler 只注入 MEMORY.md 的前 N 行（索引级别），需要细节时再加载具体文件。

### 5.6 Mouth — 沟通能力（messaging.*）

统一抽象：
- 输入：消息（文本/附件/引用/线程信息/发送者身份）
- 输出：回复（分段发送、长文落 notebook 后发摘要、可静默）

MVP：CLI（必须） + 1 个 IM adapter（Telegram 或 Discord）。

### 5.7 Subordinates — 子代理（subagents）

目的：并行研究加速、高不确定任务隔离。

类型：
- 静态子代理：预置角色（研究员/审稿人/计划员）
- 动态子代理：按需生成专项分身（"只负责收集 A 股新能源行业数据"）

约束：
- 子代理**继承 soul 的核心约束**（边界和禁忌），但不继承完整灵魂
- 子代理上下文更少（最小泄露）
- 子代理工具更少（最小风险）
- 子代理输出必须可汇总（结构化要点 + 指向 notebook 产物）

### 5.8 Alarm — 任务调度（scheduler）

核心交互（先设计后确认）：
1. 用户用自然语言描述意图
2. Agent 生成"任务设计稿"（触发条件、频率、输入、产物、通知、失败策略）
3. 用户确认后才落地为 Task

任务类型：
- 定时：cron / interval
- 事件：消息关键词、文件变更、webhook（MVP 可先不做，但接口需预留）

输出策略：
- 默认写入 notebook 产物文件，并发送摘要
- 支持静默任务：只写文件不打扰；异常才通知

交易日历：Default Profile 可提供 `calendar.trading` Tool Provider，Scheduler 的 skill 在生成任务设计稿时调用它确定触发时间。内核不内置日历概念。

### 5.9 Skills — 技能系统

本项目采用与 Claude Code "技能按需加载"一致的产品语义：

- 默认上下文只注入 skill 的摘要/元信息，正文在调用时加载
- 支持两种调用：用户显式调用（`/skill-name`）、模型自动调用（可配置禁用）
- Skill 可声明：`allowed-tools`、`disable-model-invocation`、`user-invocable`、`context: fork`

交付形态：

```
.claude/skills/<skill-name>/
  SKILL.md          # 元信息 + 工作流指令
  ...               # 可选资源文件
```

元信息示例：

```yaml
---
description: 结构化研究工作流——获取行情、计算指标、生成分析笔记
allowed-tools: [market.ohlcv, compute.run, notebook.write, memory.write]
context: fork
disable-model-invocation: false
user-invocable: true
---
```

**强约束**：skills 内容只能通过 Skill Engine 受控加载，不能通过 notebook.read 任意触达。

#### Default Profile 附带的默认技能包

| 技能 | 命令 | 工作流 |
|------|------|--------|
| 研究 | `/research {topic}` | market.ohlcv → compute 指标 → 结合 memory → notebook 写分析笔记 |
| 复盘 | `/review {period}` | 回顾 observations/reflections → 生成复盘报告 |
| 扫描 | `/scan {criteria}` | compute 批量筛选 → notebook 写扫描结果 |
| 对比 | `/compare {a} {b}` | 两个标的并排对比分析 |

### 5.10 Growth — 成长循环

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
教练指导 → agent 内化：

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

### 5.11 Tool Provider — 外部能力注册

非核心能力通过 Tool Provider 注册到系统。

#### 定义

Tool Provider 是一个外部模块，向 Tool Router 注册一组工具。注册后，LLM 可以像调用内核工具一样直接调用。

```
Tool Provider ≠ Skill
  Provider = 提供新的原子能力（"我能查财务数据"）
  Skill    = 编排已有能力成工作流（"怎么做一份研究报告"）
```

#### 交付形态

```
.claude/providers/<provider-name>/
  PROVIDER.md       # 元信息 + 工具定义
```

元信息示例：

```yaml
---
name: tushare-financial
description: A 股财务数据（利润表/资产负债表/现金流量表）
config:
  token: ${TUSHARE_TOKEN}

tools:
  - name: financial.income
    description: "获取利润表，参数：symbol, period"
  - name: financial.balance
    description: "获取资产负债表，参数：symbol, period"
  - name: financial.cashflow
    description: "获取现金流量表，参数：symbol, period"
---
```

Default Profile 可预配置 providers。用户可增删。

### 5.12 常驻运行与恢复

- 进程常驻：可前台运行，也可后台服务化
- 崩溃恢复：重启后恢复 soul + memory + notebook + tasks；避免重复副作用（幂等）
- 升级可控：升级/重启不会丢失关键状态

验收：进程重启后，任务仍按计划触发；soul 和 memory 完整保留。

## 6. Workspace 设计

### 6.1 完整工作区结构

```
soul.md                          ← 灵魂（人格/风格/边界/成长方向）

memory/                          ← 记忆（内化认知）
  MEMORY.md                      ← 索引（内核自动维护）
  preferences.md                 ← 偏好
  tracking.md                    ← 关注列表
  beliefs.md                     ← 信念
  observations/                  ← 观察记录
    YYYY-MM-DD-{topic}.md
  reflections/                   ← 反思日记
    YYYY-{period}.md

notebook/                        ← 笔记本（外化产物）
  research/                      ← 深度研究
    {topic}/
      YYYY-MM-DD.md
  reports/                       ← 周期报告
    {period}/
      YYYY-MM-DD.md
  scratch/                       ← 草稿

.claude/
  skills/                        ← 技能
    <skill-name>/
      SKILL.md
  providers/                     ← 外部能力
    <provider-name>/
      PROVIDER.md
```

### 6.2 三区的生命周期差异

| 区域 | 性质 | 修改频率 | 修改权限 |
|------|------|---------|---------|
| soul.md | 人格身份 | 极少变 | 需用户确认 |
| memory/ | 内化认知 | 渐进积累 | 分层级（见 §5.10） |
| notebook/ | 外化产物 | 自由写入 | agent 自由 |

**铁律**：soul.md 可以被删除后 agent 仍能启动（只是没有人格），memory 可以被清空后 agent 仍能运行（只是没有记忆），notebook 可以被清空后 agent 仍能工作（只是没有历史产物）。任何区域都不是启动的硬依赖。

### 6.3 命名约定

- **运行时工作区**：soul.md / memory/ / notebook/ — 面向用户与 agent 协作
- **仓库开发文件**：CLAUDE.md / AGENTS.md — 面向开发者，不注入运行时上下文

## 7. 内核架构

### 7.1 模块划分

1. **Runtime/Daemon**：常驻循环、信号处理、健康检查、升级/重启策略
2. **Channel Adapters**：Telegram/Discord/CLI 输入输出适配
3. **Session Manager**：会话隔离、身份映射
4. **Context Assembler**：神经系统——自动组装 soul + memory 摘要 + OHLCV 到 LLM 上下文
5. **Memory Manager**：记忆写入/读取策略、索引维护、可编辑/回滚
6. **Skill Engine**：技能发现、摘要注入、调用时加载、权限/上下文约束执行
7. **Tool Router**：统一工具调用入口（内置 + Provider 注册 + 审计/限流/重试）
8. **Market Adapter Registry**：管理 market.ohlcv 的适配器注册与切换
9. **Tool Provider Registry**：管理外部 Tool Provider 的注册
10. **Scheduler**：任务存储、触发、重试、静默策略、告警
11. **Subagent Runner**：fork 上下文、限制工具、汇总输出

### 7.2 内核工具面

内核内置 5 个器官工具：

| 工具 | 仿生 | 进内核理由 |
|------|------|-----------|
| `market.ohlcv` | 眼睛 | 适配器归一化 + canonical format 契约 |
| `compute.run` | 计算器 | 沙箱安全 + OHLCV 自动注入 |
| `notebook.*` | 手 | 与 memory 索引预连通 |
| `memory.*` | 记忆 | 上下文注入集成 + 品类管理 |
| `messaging.*` | 嘴 | 渠道连接管理 |

机制层（非器官工具，但内核提供）：
- `skills.*`：列出/调用 skills
- `tasks.*`：创建/管理任务
- `subagents.*`：创建/运行子代理

### 7.3 预连通管道规范

| 管道 | 触发条件 | 内核行为 |
|------|---------|---------|
| soul → 上下文 | 每轮 Turn 开始 | Context Assembler 读取 soul.md 并注入 system prompt |
| beliefs → 上下文 | 每轮 Turn 开始 | Context Assembler 读取 beliefs.md 摘要并注入 |
| MEMORY.md → 上下文 | 每轮 Turn 开始 | Context Assembler 注入索引前 N 行 |
| OHLCV → compute | compute.run 调用时 | 自动将最近 market.ohlcv 结果作为 df/open/high/low/close/volume 注入 |
| notebook.write → MEMORY.md | notebook.write 完成后 | 自动追加索引条目（路径 + 摘要 + 时间） |
| beliefs 变更 → reflections | beliefs.md 被修改时 | 自动记录变更日志（之前→现在→原因） |

## 8. 安全与合规

1. **IM 输入默认不可信**：必须有 prompt injection 防护与规则优先级。
2. **灵魂修改强确认**：soul.md 和 preferences.md 的修改需用户确认。
3. **信念变更可审计**：beliefs.md 的每次修改自动记录到 reflections/，含变更理由。
4. **权限最小化**：skills 声明 allowed-tools；未声明不得调用高风险工具。
5. **审计与可追溯**：任务触发、工具调用、关键决策、灵魂/信念变更都产生事件日志。

### 8.1 可观测性

MVP 需具备最小审计面：

- **事件日志**：记录 Turn / Task 触发 / Tool 调用 / Skill 调用 / Subagent 调用的关键字段
- **产物可追溯**：所有 notebook 产物都能从 MEMORY.md 索引找到
- **成长可追溯**：beliefs.md 的变更历史 + soul.md 的变更历史
- **失败可诊断**：定时任务失败有清晰错误与重试策略

## 9. 交互与管理体验

原则：自然语言是入口，但不能取消可控性。

统一管理能力（CLI 与 IM 语义一致）：
- 查看/调用 skills
- 查看/编辑/撤销 memory 和 soul
- 创建/查看/暂停/恢复 tasks
- 查看最近产物与审计记录

### 9.1 关键用户旅程

#### 旅程 A：投资研究（多工具自动编排）

```
用户："帮我看看宁德时代最近怎么样"

Agent 自动编排：
  1. market.ohlcv("300750") → 获取近期行情
  2. compute.run("ta.rsi(close, 14)") → 计算 RSI（OHLCV 自动注入）
  3. memory.recall("宁德时代") → 找到历史研究和观察
  4. 综合分析，生成结构化观点（数据 + 推理 + 置信度）
  5. notebook.write("research/宁德时代/2024-01-15.md") → 保存研究笔记
  6. memory.write("observations/2024-01-15-宁德时代.md") → 记录观察
  7. 对话中返回摘要 + 关键结论
```

#### 旅程 B：教练指导成长

```
用户："你最近总是低估市场情绪的影响，分析时要多考虑资金面。"

Agent 行为：
  1. memory.write("reflections/...") → 记录教练反馈
  2. 提议修改 beliefs.md → "增加：市场情绪和资金面对短期走势有显著影响"
  3. 提议修改 soul.md 成长方向 → 等待用户确认
  4. 用户确认后 → 后续分析自动包含资金面评估
```

#### 旅程 C：定时复盘（先设计后确认）

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

#### 旅程 D：显式调用 skill

```
用户："/research 比亚迪 vs 宁德时代"

/compare skill 在 fork 子代理中运行：
  1. 分别获取两个标的的 OHLCV
  2. compute 计算对比指标
  3. 结合 memory 中的历史研究
  4. 生成 notebook/research/比亚迪-vs-宁德时代/2024-01-15.md
  5. 主对话返回摘要 + 关键对比结论
```

## 10. Default Profile

Default Profile 是介于内核和 Skills 之间的**发行版预设**。它决定了 agent 开箱即用的样子。

### 10.1 投资助手 Profile 包含

| 组件 | 内容 |
|------|------|
| soul.md 模板 | 个人投资研究助手人格（见 §5.1） |
| memory 默认结构 | preferences/tracking/beliefs/observations/reflections |
| notebook 默认目录 | research/ + reports/ + scratch/ |
| 默认 MarketAdapter | TushareAdapter |
| 默认 Tool Providers | （可选）tushare-financial、calendar.trading |
| 默认 Skills 包 | /research、/review、/scan、/compare |
| compute 预装 | pandas + pandas-ta + Trading Coreutils |

### 10.2 可替换性

换一个 Default Profile，同一个内核就变成不同的助手：

```
投资助手 Profile  → soul: 价值投资, adapter: tushare, skills: research/review
项目管理 Profile  → soul: GTD方法论, adapter: 无, skills: plan/track/report
学习助手 Profile  → soul: 费曼学习法, adapter: 无, skills: explain/quiz/review
```

内核不变，Profile 可以独立分发和安装。

### 10.3 铁律

Profile 中的任何文件都可以被删除，agent 仍能启动和运行（只是不再是投资助手）。Profile 是"预设"，不是"依赖"。

## 11. 交付路线

### Phase 1（MVP：能看、能算、能记、能长）

- soul.md + memory 系统（品类 + 索引自动维护）+ notebook 系统
- market.ohlcv（TushareAdapter）+ compute.run（OHLCV 自动注入）
- 预连通管道（soul→上下文、OHLCV→compute、notebook→memory 索引）
- CLI + 1 个 IM adapter
- Skill Engine + 至少 1 个默认研究 skill
- Scheduler（设计稿→确认→执行）
- Subagent（fork + 汇总）

### Phase 2（能长、能反思、能扩展）

- 成长循环完善（定时反思 → belief 更新 → soul 微调）
- Tool Provider 注册机制 + 更多 providers
- skills 安装/启用/禁用/版本治理
- 多 IM adapters
- 更多 MarketAdapter（AkShare/CSV/自定义）

### Phase 3（能力包生态）

- 更多默认 skills（回测集成、报表生成等）
- 其他领域的 Default Profile
- 社区 skill/provider 市场

## 12. 验收标准（BDD 风格行为用例）

1. **OHLCV 原语**：market.ohlcv 返回 canonical 6 列格式；compute.run 中 df/close/volume 等变量自动可用。
2. **适配器可替换**：替换 MarketAdapter 后，所有 skill 和 compute 的行为不受影响。
3. **灵魂塑造认知**：同一个问题，不同 soul.md 产生不同分析路径和观点结构。
4. **成长可审计**：beliefs.md 的每次修改都有"之前→现在→原因"的记录。
5. **预连通管道**：notebook.write 后 MEMORY.md 自动更新索引；soul.md 自动注入每轮上下文。
6. **恢复**：进程崩溃后重启，soul/memory/notebook/tasks 完整保留；任务仍按计划触发。
7. **技能权限**：未授权工具的 skill 不能越权；被禁用 skill 不会被自动调用。
8. **教练模式**：用户指导后，agent 的后续行为体现改变（可通过 beliefs/soul 变更验证）。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
