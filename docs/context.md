# Context Manager — 上下文工程

> 同样的市场数据，不同的上下文组装方式，LLM 决策质量天差地别。
> Context Manager 是 Agent 决策质量的核心决定因素。

## 核心职责

将分散在各模块中的信息组装为结构化上下文，交给 Agent 作为决策输入。

```
输入来源:
  Engine    → 市场状态、账户状态、事件
  Memory    → playbook、持仓笔记
  Config    → 上下文策略偏好

输出:
  Context   → 结构化的 Agent 决策输入
```

## 上下文分层

```
┌──────────────────────────────────────────────┐
│  Layer 1: System Prompt (策略指令·持久)        │
│  Agent 的角色定义和行为约束                     │
│  ≈ 交易员的性格与信仰                          │
├──────────────────────────────────────────────┤
│  Layer 2: Playbook (交易手册·持久·可演化)      │
│  策略规则 + 累积的经验教训                      │
│  始终注入上下文                                │
│  ≈ 交易员多年积累的交易系统                     │
├──────────────────────────────────────────────┤
│  Layer 3: Position Notes (持仓笔记·条件注入)   │
│  当前持有的每个仓位的笔记                       │
│  有持仓时才注入                                │
│  ≈ 交易员桌上贴的持仓便签                      │
├──────────────────────────────────────────────┤
│  Layer 4: Market State (市场快照·每次重建)     │
│  当前日期、行情、账户状态、待执行订单           │
│  ≈ 交易员此刻屏幕上看到的                      │
├──────────────────────────────────────────────┤
│  Layer 5: Events (触发事件·本次决策特有)       │
│  "止损被触发" / "订单已成交" / "新 bar"         │
│  ≈ 让交易员注意力聚焦的那个事件                 │
├──────────────────────────────────────────────┤
│  Layer 6: Available Tools (工具列表)           │
│  Agent 可以使用的所有工具及其描述               │
│  ≈ 交易终端上有哪些按钮可以按                   │
└──────────────────────────────────────────────┘
```

## Context 组装流程

```python
class ContextManager:
    def assemble(self,
                 market_state: MarketState,
                 account_state: AccountState,
                 events: list[Event],
                 playbook: str,
                 position_notes: dict[str, str],
                 ) -> Context:
        """
        组装 Agent 决策所需的完整上下文。

        组装策略:
        1. 始终包含: playbook + 当前持仓笔记
        2. 始终包含: 当前市场快照 + 账户状态
        3. 有事件时: 包含触发事件描述
        4. 工具列表: 始终包含可用工具说明
        """
```

## 市场数据呈现格式

Context Manager 需要将原始数据格式化为 LLM 友好的文本。

### 可配置格式

```python
context_config = {
    "market_format": "tabular",  # tabular | narrative | json
}
```

**tabular（默认，token 效率最高）**:
```
AAPL | 2024-03-15 | O:172.5 H:174.2 L:171.8 C:173.9 V:45.2M
                   | 涨跌: +0.8% | 较昨日放量 30%
```

**narrative（可读性最好）**:
```
AAPL 2024-03-15: 开盘 172.5, 最高 174.2 (+1.0%), 最低 171.8,
收盘 173.9 (+0.8%)。成交量 4520 万股, 较 20 日均量放大 30%。
连续第 3 个交易日收阳。
```

**json（结构化，适合需要精确数值的场景）**:
```json
{"symbol": "AAPL", "date": "2024-03-15",
 "open": 172.5, "high": 174.2, "low": 171.8,
 "close": 173.9, "volume": 45200000}
```

## 上下文预算管理

Context Manager 需要控制总 token 量，避免超出 LLM 上下文窗口。

```python
context_config = {
    "max_context_tokens": 4000,            # 上下文 token 上限
    "playbook_budget": 1000,               # playbook 最大 token
    "position_notes_budget": 500,          # 持仓笔记最大 token
    "market_budget": 500,                  # 市场数据最大 token
    "events_budget": 200,                  # 事件描述最大 token
}
```

### 超出预算时的压缩策略

```
1. playbook 超长 → 警告用户精简 playbook
2. 持仓笔记过多 → 只保留最大持仓的笔记 + 其余摘要
3. 市场数据 → 减少历史窗口大小
```

## Context 数据结构

```python
@dataclass
class Context:
    # 始终存在
    playbook: str                    # 交易手册内容
    market: MarketSnapshot           # 当前行情
    account: AccountSnapshot         # 当前账户
    available_tools: list[ToolDesc]  # 可用工具

    # 条件存在
    position_notes: dict[str, str]   # 当前持仓的笔记 (symbol → note)
    events: list[Event]              # 触发本次决策的事件

    # 元信息
    current_datetime: datetime       # 当前模拟时间
    bar_index: int                   # 第几根 bar
    decision_count: int              # 第几次决策
```

## Context Manager 作为框架核心

Context Manager 是框架核心组件，不是扩展，因为它直接决定 Agent 信息质量。

但 Context Manager 的**实现策略**是可配置的：
- 数据呈现格式可选
- token 预算可调
- 压缩策略可扩展

用户通过配置来定制，不需要替换整个 Context Manager。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
