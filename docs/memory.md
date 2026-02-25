# Memory — 文件式记忆系统

> 参考 [OpenClaw Memory System](https://docs.openclaw.ai/concepts/memory) 设计。
> 核心理念：**文件即真理，工具即接口。**

## 设计哲学

### 为什么是文件，不是数据库

```
LLM 不是数据库。LLM 是一个读写文本的人。
给它最自然的媒介——文本文件——它的表现反而最好。
```

| 维度 | 结构化记忆 (vector store) | 文件式记忆 (markdown) |
|------|-------------------------|---------------------|
| LLM 交互 | 需要序列化/反序列化 | 天然文本，零阻抗 |
| 人类审计 | 需要工具查看 | 直接打开阅读 |
| 可版本控制 | 困难 | Git diff 友好 |
| 实现复杂度 | 高（embedding + 检索） | 低（文件 IO） |
| 降级能力 | 依赖外部服务 | 文件永远可访问 |

### 借鉴 OpenClaw 的核心原则

1. **文件是 canonical source，索引是派生物** — 索引坏了可重建，文件不能丢
2. **始终注入 vs 按需检索** — 核心知识始终在上下文中，细节按需召回
3. **工具是接口，文件是存储** — Agent 通过工具操作记忆，不接触文件路径

## 工作空间隔离

每次回测运行创建独立的工作空间目录，互不污染。

```
.agenticbt/
  └── runs/
      ├── run_20240315_143022/          # 回测 A
      │   ├── playbook.md
      │   ├── journal/
      │   ├── notes/
      │   ├── reviews/
      │   ├── decisions.jsonl
      │   └── result.json
      │
      └── run_20240315_150811/          # 回测 B（完全隔离）
          ├── playbook.md
          └── ...
```

### 隔离规则

- Runner.run() 创建新的 workspace 目录
- 回测过程中所有文件操作限定在此目录内
- 回测结束后 workspace 完整保留
- 不同 run 之间可以对比（diff playbook 演化、比较 journal 风格）

### 预设记忆

回测启动时可注入预设记忆（模拟交易员的先验经验）：

```python
config = BacktestConfig(
    strategy_prompt="...",
    preset_memories={
        "notes/experience.md": "过去 3 年的交易经验总结...",
        "notes/sector_view.md": "当前对各行业的看法...",
    }
)
```

## 文件结构

```
workspace/
  ├── playbook.md              # 交易手册（始终注入上下文）
  ├── journal/                 # 每日复盘日志（按需召回）
  │   ├── 2024-01-15.md
  │   ├── 2024-01-16.md
  │   └── ...
  ├── notes/                   # 主题笔记（持仓笔记始终注入）
  │   ├── position_AAPL.md
  │   ├── market_regime.md
  │   └── ...
  ├── reviews/                 # 阶段性总结（按需召回）
  │   ├── week_03.md
  │   ├── month_01.md
  │   └── ...
  ├── decisions.jsonl          # 决策记录（框架自动写，非 Agent 工具）
  └── result.json              # 回测结果（框架自动写）
```

## 各文件角色

### playbook.md — 交易手册

```
特性:
  - 回测启动时由 strategy prompt 初始化
  - Agent 可在回测过程中追加经验教训
  - 始终注入上下文（类比 OpenClaw 的 MEMORY.md）
  - 必须保持精简（每次决策都消耗 token）

内容结构示例:
  ┌────────────────────────────────┐
  │ # 交易手册                      │
  │                                │
  │ ## 核心策略                     │
  │ 均值回归: 价格偏离均值时逆向交易 │
  │                                │
  │ ## 入场规则                     │
  │ - RSI < 30 且布林带下轨附近     │
  │ - 成交量 > 20日均量 1.5 倍      │
  │ - 200日均线之上                 │
  │                                │
  │ ## 经验教训 (回测中追加)         │
  │ - [2024-02] 财报季 RSI 信号失效 │
  │ - [2024-04] 连亏3笔后应暂停1天  │
  └────────────────────────────────┘
```

### journal/{date}.md — 每日复盘

```
特性:
  - Append-only，按时间戳记录
  - Agent 通过 memory.log() 在盘中随时记录
  - 交易日结束时，框架提示 Agent 写完整复盘
  - 不自动注入上下文，通过 memory.recall() 按需检索

内容示例:
  ┌────────────────────────────────┐
  │ # 2024-03-15                    │
  │                                │
  │ [14:30] RSI 降至 28, 放量企稳   │
  │ [14:32] 买入 AAPL 100 股 @172.5│
  │                                │
  │ ## 日终复盘                     │
  │ 今日买入 AAPL 符合策略规则      │
  │ 大盘偏弱但科技股抗跌            │
  │ 注意下周 FOMC 可能加大波动      │
  └────────────────────────────────┘
```

### notes/{key}.md — 主题笔记

```
特性:
  - Key-addressable，可覆盖更新
  - Agent 通过 memory.note(key, content) 操作
  - position_* 前缀的笔记在持仓存在时自动注入上下文
  - 其他笔记通过 memory.recall() 按需检索

持仓笔记示例:
  ┌────────────────────────────────┐
  │ # AAPL 持仓笔记                 │
  │                                │
  │ 持仓: 100 股 @172.5            │
  │ 止损: 168.0 (ATR 2x)           │
  │ 目标: 180.0                    │
  │                                │
  │ 入场理由: RSI超卖+放量+BB支撑   │
  │ 关注: 173关键位, FOMC前减仓     │
  └────────────────────────────────┘
```

### reviews/{period}.md — 阶段总结

```
特性:
  - 框架在周/月末触发 Agent 撰写
  - 浓缩旧 journal 的关键信息
  - 随时间推移，旧 journal 不再加载，只保留 review
  - 这就是"记忆巩固"——细节遗忘，经验留下
```

## Memory 工具

### memory.log(content)

```
用途: 往当日日志追加一条记录
文件: journal/{current_date}.md (append)
时机: Agent 在决策过程中随时可调用
      框架在日终提示 Agent 写复盘时调用

示例:
  memory.log("观察到 AAPL 连续 3 天缩量下跌, RSI 逼近 30")
  → 追加到 journal/2024-03-15.md
```

### memory.note(key, content)

```
用途: 创建或更新一个主题笔记
文件: notes/{key}.md (overwrite)
时机: 开平仓时更新持仓笔记
      观察到重要市场变化时记录
      总结阶段性经验时写 review

示例:
  memory.note("position_AAPL", "持仓 100 股 @172.5, 止损 168.0")
  → 写入 notes/position_AAPL.md

  memory.note("week_12", "本周总结: 震荡市中策略表现一般...")
  → 写入 notes/week_12.md
```

### memory.recall(query)

```
用途: 搜索相关记忆
范围: journal/ + notes/ + reviews/ + playbook.md
返回: 相关片段列表 [{source, content}, ...]

MVP 实现: 关键词匹配 + 时间衰减排序
后续可升级: OpenClaw 式 hybrid search (vector + BM25)

示例:
  memory.recall("上次 RSI 超卖时买 AAPL 的结果")
  → [
      { source: "journal/2024-02-20.md",
        content: "买入 AAPL 因 RSI=25, 最终止损出局 -1.8%" },
      { source: "notes/position_AAPL.md",
        content: "已平仓... RSI超卖+放量组合有效" },
    ]
```

## 上下文注入策略

```
始终注入 (每次决策消耗 token):
  └── playbook.md

条件注入 (有对应持仓时):
  └── notes/position_*.md

按需检索 (Agent 主动 recall):
  ├── journal/*.md
  ├── notes/*.md (非 position 类)
  └── reviews/*.md
```

## 框架驱动的记忆时刻

```
每个交易日结束:
  → 框架提示 Agent:
    "交易日结束，请用 memory.log 记录今日复盘。
     如果有新的经验教训，用 memory.note 更新 playbook。"

持仓变动 (订单成交):
  → 框架提示 Agent:
    "AAPL 买入 100 股已成交 @172.5。
     请用 memory.note 记录持仓信息。"

持仓清零 (全部平仓):
  → 框架提示 Agent:
    "AAPL 持仓已全部平仓。
     请用 memory.note 更新持仓笔记，记录最终结果和经验。"

周期性节点 (周末/月末):
  → 框架提示 Agent:
    "本周/本月结束，请撰写阶段总结。"
```

## 记忆的时间衰减（自然遗忘）

```
最近 5 天:   journal 完整加载到 recall 候选集
最近 1 月:   只加载周总结 (reviews/week_*.md)
更早:        只加载月总结 (reviews/month_*.md)
全程:        playbook.md 持续累积精华

Agent 写总结时自然地浓缩旧信息
→ 细节遗忘，经验留下
→ 这就是人类记忆巩固的模拟
```

## 后续演进路线

```
MVP:
  - 文件读写
  - recall 用关键词匹配 + 时间衰减

V2:
  - recall 升级为 hybrid search (BM25 + vector)
  - SQLite 索引作为派生物（文件仍是 canonical source）

V3:
  - 跨 run 的记忆迁移（将一次回测的 playbook 带入下一次）
  - 记忆蒸馏（自动从多次 run 中提炼共同经验）
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
