# Agent Protocol — Agent 接口规范

> 框架对 Agent 的唯一要求：实现 `AgentProtocol`。
> 任何能思考、能调用工具的实体，都可以成为交易员。

## 设计原则

```
Agent 是交易员，不是插件。
框架不关心 Agent 内部如何推理，只关心：
  1. 给你上下文和工具，你能做出决策吗？
  2. 给你一个提示，你能执行相应动作吗？

这就是全部接口。
```

## AgentProtocol

```python
from typing import Protocol

class AgentProtocol(Protocol):

    def decide(self, context: Context, tools: list[Tool]) -> Decision:
        """
        核心决策方法。

        框架在每个决策点调用此方法：
        1. 组装好 context (市场状态 + playbook + 持仓笔记 + 事件)
        2. 准备好 tools (market, indicator, account, trade, memory + 扩展)
        3. 调用 agent.decide()
        4. Agent 内部自由推理，通过 tools 获取信息、执行交易、记录记忆
        5. 返回 Decision 记录

        Agent 在 decide() 内部可以：
          - 调用 market.observe() 查看行情
          - 调用 indicator.calc() 计算指标
          - 调用 account.status() 查看持仓
          - 调用 trade.execute() 下单
          - 调用 memory.log() / memory.note() / memory.recall()
          - 调用任何扩展工具 (MCP/Skills)
          - 多次调用工具（多轮推理）
          - 不调用任何工具（纯观望）

        返回:
          Decision 对象，记录本次决策的完整信息
        """
        ...

    def prompted_action(self, prompt: str, tools: list[Tool]) -> None:
        """
        框架驱动的提示动作。

        用于框架在特定时刻引导 Agent 执行非决策性任务：
          - 日终复盘: "交易日结束，请记录今日复盘"
          - 持仓变动: "AAPL 买入已成交，请记录持仓信息"
          - 阶段总结: "本周结束，请撰写周度总结"

        Agent 响应提示，通常通过 memory 工具记录信息。
        此方法不返回 Decision（不是交易决策）。
        """
        ...
```

## Decision 数据结构

每次 `decide()` 调用产生一条 Decision 记录，是合规审计和一致性分析的基础数据。

```python
@dataclass
class Decision:
    # 时间标识
    datetime: datetime           # 决策时的模拟时间
    bar_index: int               # 第几根 bar
    decision_index: int          # 第几次决策

    # Agent 输出
    action: str                  # "buy" | "sell" | "close" | "hold"
    symbol: str | None           # 操作标的 (hold 时可为 None)
    quantity: int | None         # 操作数量
    reasoning: str               # Agent 的推理过程 (完整思考链)

    # 决策时的快照
    market_snapshot: dict        # 决策时的市场数据
    account_snapshot: dict       # 决策时的账户状态
    indicators_used: dict        # Agent 查询过的指标及其值

    # 工具调用记录
    tool_calls: list[ToolCall]   # 本次决策中所有工具调用

    # 执行结果
    order_result: dict | None    # 订单执行结果 (hold 时为 None)

    # LLM 元信息
    model: str                   # 使用的模型
    tokens_used: int             # 本次决策消耗的 token
    latency_ms: float            # 本次决策耗时


@dataclass
class ToolCall:
    tool: str                    # 工具名 (如 "indicator.calc")
    input: dict                  # 调用参数
    output: dict                 # 返回结果
    timestamp: float             # 调用时间
```

## 支持的 Agent 类型

### 1. LLM Agent（主要形态）

```python
class LLMAgent:
    """基于 LLM 的交易员 Agent"""

    def __init__(self, model: str, system_prompt: str):
        self.model = model               # "claude-sonnet-4-20250514" etc.
        self.system_prompt = system_prompt # 角色定义和行为约束

    def decide(self, context: Context, tools: list[Tool]) -> Decision:
        # 1. 构建 LLM messages
        messages = self._build_messages(context)

        # 2. 调用 LLM (支持多轮工具调用)
        response = self._call_llm(messages, tools)

        # 3. 从 LLM 响应中提取 Decision
        return self._parse_decision(response)
```

### 2. 规则引擎 Baseline（对照组）

```python
class RuleAgent:
    """规则引擎 Agent，用于 Agent vs Baseline 对比"""

    def __init__(self, rules: dict):
        self.rules = rules

    def decide(self, context: Context, tools: list[Tool]) -> Decision:
        # 用 if/else 实现同样的策略逻辑
        # 作为 LLM Agent 的对照基准
        ...
```

A/B 对比的核心价值：**同一策略，规则引擎 vs LLM，谁做得更好？** LLM 的推理能力是否真的优于硬编码规则？

### 3. 人类代理（调试工具）

```python
class HumanAgent:
    """人类通过终端交互做决策，用于调试和理解"""

    def decide(self, context: Context, tools: list[Tool]) -> Decision:
        # 打印 context，等待人类输入
        # 人类可以调用工具，最终给出决策
        ...
```

用于：策略调试、理解 Agent 视角、验证框架行为。

## Agent 的自由度与约束

```
Agent 可以自由做的事:
  ✓ 选择查看哪些指标
  ✓ 决定是否交易
  ✓ 决定交易方向和数量
  ✓ 记录任何想法和观察
  ✓ 回忆历史经验
  ✓ 调用扩展工具
  ✓ 在一次 decide() 中多轮推理

Agent 不能做的事:
  ✗ 绕过风控拦截器
  ✗ 操作未来数据 (Engine 保证)
  ✗ 直接修改仓位 (必须通过 trade 工具)
  ✗ 修改引擎内部状态
  ✗ 接触文件路径 (通过 memory 工具间接操作)
```

## Agent 的决策流程

```
框架调用 agent.decide(context, tools)
    │
    ▼
Agent 阅读 context
    ├── playbook: 我的策略是什么？
    ├── market: 当前行情如何？
    ├── positions: 我持有什么？
    ├── events: 发生了什么事？
    └── position_notes: 上次买入的理由？
    │
    ▼
Agent 主动调用工具
    ├── indicator.calc("RSI", ...) → 28.5
    ├── indicator.calc("MACD", ...) → 金叉
    ├── market.history("AAPL", 20) → 近 20 日走势
    ├── memory.recall("上次 RSI 超卖...") → 历史经验
    └── (可多轮，可不调用)
    │
    ▼
Agent 推理决策
    "RSI 超卖 + MACD 金叉 + 历史经验积极
     → 买入信号，但仓位已有 15%，只加 5%"
    │
    ▼
Agent 执行交易
    ├── trade.execute(buy, AAPL, 50)
    │   └── Risk Guard 检查 → 通过/拒绝
    ├── memory.note("position_AAPL", "...")
    └── memory.log("买入 AAPL 50 股, 理由: ...")
    │
    ▼
Agent 返回 Decision
    └── 包含完整推理链 + 工具调用记录
```

## Agent 工厂

框架提供 Agent 工厂，简化 Agent 创建：

```python
# 最简用法
agent = AgentFactory.create(
    model="claude-sonnet-4-20250514",
    strategy_prompt="均值回归策略: RSI < 30 时买入..."
)

# 自定义用法
agent = AgentFactory.create(
    model="claude-sonnet-4-20250514",
    strategy_prompt="...",
    system_prompt="你是一位保守的价值投资者...",
    temperature=0.0,         # 降低随机性
    max_tool_rounds=5,       # 最多 5 轮工具调用
)

# 规则引擎对照
baseline = AgentFactory.create_rule_agent(
    rules={
        "buy": lambda ctx: ctx.indicators["RSI"] < 30,
        "sell": lambda ctx: ctx.indicators["RSI"] > 70,
    }
)
```

## 多 Agent 支持（后续扩展）

```
MVP: 单 Agent 单资产/多资产
后续: 多 Agent 协作
  - 分析师 Agent: 只看不做，提供研究报告
  - 交易员 Agent: 参考分析，执行决策
  - 风控 Agent: 独立风险评估

多 Agent 不改变 Protocol，
每个 Agent 仍实现 AgentProtocol，
Runner 负责编排调用顺序。
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
