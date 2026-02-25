# Runner — 回测编排器

> Runner 是指挥家，不演奏任何乐器。
> 它只做一件事：按正确的顺序调度各模块。

## 职责

```
Runner 的职责:
  ├── 初始化    创建工作空间、初始化各模块
  ├── 主循环    驱动 bar 推进 → 事件处理 → Agent 决策
  ├── 触发策略  决定何时调用 Agent
  ├── 记忆驱动  在关键时刻提示 Agent 记录
  ├── 收尾      生成结果、保存快照
  └── 矩阵实验  支持多维对比回测

Runner 不做的事:
  ✗ 不做市场模拟 (Engine 做)
  ✗ 不组装上下文 (Context Manager 做)
  ✗ 不做交易决策 (Agent 做)
  ✗ 不评估结果 (Eval 做)
```

## 回测主循环

```python
class Runner:
    def run(self, config: BacktestConfig) -> BacktestResult:
        """
        执行一次完整回测。
        """

        # ─── Phase 1: 初始化 ───
        workspace = self._create_workspace()
        engine = Engine()
        engine.load(config.data)
        memory = Memory(workspace)
        memory.init_playbook(config.strategy_prompt)
        memory.load_presets(config.preset_memories)
        agent = config.agent
        context_mgr = ContextManager(config.context_config)
        recorder = Recorder(workspace)

        # ─── Phase 2: 主循环 ───
        while engine.has_next():
            bar = engine.advance()

            # 2a. 处理订单撮合
            fills = engine.match_orders(bar)
            events = self._fills_to_events(fills)

            # 2b. 检查触发条件
            if not self._should_decide(bar, events, config.trigger):
                continue

            # 2c. 组装上下文
            context = context_mgr.assemble(
                market_state=engine.market_state(),
                account_state=engine.account_state(),
                events=events,
                playbook=memory.read_playbook(),
                position_notes=memory.read_position_notes(
                    engine.account_state().positions
                ),
            )

            # 2d. Agent 决策
            tools = self._build_tools(engine, memory)
            decision = agent.decide(context, tools)

            # 2e. 记录决策
            recorder.record(decision)

            # 2f. 框架驱动的记忆时刻
            self._trigger_memory_moments(agent, bar, fills, tools)

        # ─── Phase 3: 收尾 ───
        result = self._build_result(engine, recorder, memory, config)
        result.save(workspace)
        return result
```

## 触发策略 (Trigger Policy)

决定何时调用 Agent 做决策。不同策略适用于不同场景。

### 可选策略

```python
class TriggerPolicy(Protocol):
    def should_decide(self, bar: Bar, events: list[Event]) -> bool: ...
```

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `EVERY_BAR` | 每根 bar 都调用 Agent | 日线策略、简单策略 |
| `ON_EVENT` | 有事件时才调用 | 事件驱动策略 |
| `PERIODIC` | 每 N 根 bar 调用一次 | 周频/月频策略 |
| `COMPOSITE` | 多条件组合 | 复杂触发逻辑 |

### 配置示例

```python
# 每根 bar 都决策 (MVP 默认)
config = BacktestConfig(
    trigger=EveryBar(),
    ...
)

# 每周一决策
config = BacktestConfig(
    trigger=Periodic(interval="weekly", day="monday"),
    ...
)

# 事件驱动: 成交、止损触发、新 bar
config = BacktestConfig(
    trigger=OnEvent(event_types=["fill", "stop_triggered"]),
    ...
)

# 复合: 每天 + 有成交时额外触发
config = BacktestConfig(
    trigger=Composite([EveryBar(), OnEvent(["fill"])]),
    ...
)
```

## 框架驱动的记忆时刻

Runner 在关键时刻自动提示 Agent 进行记忆操作。

```python
def _trigger_memory_moments(self, agent, bar, fills, tools):
    """
    在关键时刻提示 Agent 执行记忆操作。
    通过 agent.prompted_action() 触发，
    Agent 自主决定记录什么内容。
    """

    # 持仓变动 → 提示 Agent 记录持仓笔记
    for fill in fills:
        agent.prompted_action(
            f"{fill.symbol} {fill.side} {fill.quantity}股 "
            f"已成交 @{fill.price}。"
            f"请用 memory.note 记录持仓信息。",
            tools
        )

    # 交易日结束 → 提示 Agent 日终复盘
    if self._is_day_end(bar):
        agent.prompted_action(
            "交易日结束。请用 memory.log 记录今日复盘。"
            "如有新的经验教训，用 memory.note 更新 playbook。",
            tools
        )

    # 周末 → 提示 Agent 周度总结
    if self._is_week_end(bar):
        agent.prompted_action(
            "本周结束。请撰写周度总结，回顾本周交易表现和市场观察。",
            tools
        )

    # 月末 → 提示 Agent 月度总结
    if self._is_month_end(bar):
        agent.prompted_action(
            "本月结束。请撰写月度总结，浓缩本月经验。",
            tools
        )
```

## 工具构建

Runner 负责将 Engine 和 Memory 的能力包装为 Agent 可用的工具。

```python
def _build_tools(self, engine: Engine, memory: Memory) -> list[Tool]:
    """
    构建 Agent 可用的工具列表。
    每个工具是一个可调用对象，附带名称和描述。
    """
    tools = [
        # 核心工具
        Tool("market.observe", engine.market_state, "获取当前行情"),
        Tool("market.history", engine.get_history, "获取历史 K 线"),
        Tool("indicator.calc", engine.calc_indicator, "计算技术指标"),
        Tool("indicator.list", engine.list_indicators, "列出可用指标"),
        Tool("indicator.describe", engine.describe_indicator, "指标参数说明"),
        Tool("account.status", engine.account_state, "获取账户状态"),
        Tool("trade.execute", self._guarded_trade(engine), "执行交易"),
        Tool("memory.log", memory.log, "记录日志"),
        Tool("memory.note", memory.note, "创建/更新笔记"),
        Tool("memory.recall", memory.recall, "搜索记忆"),
    ]

    # 扩展工具 (MCP/Skills)
    tools.extend(self._load_extensions())

    return tools
```

## BacktestConfig 配置

```python
@dataclass
class BacktestConfig:
    # 必填
    agent: AgentProtocol                # Agent 实例
    data: DataConfig                    # 数据配置

    # 策略描述 (初始化 playbook)
    strategy_prompt: str                # 策略的自然语言描述

    # 可选
    trigger: TriggerPolicy = EveryBar() # 触发策略
    risk_config: RiskConfig = default   # 风控配置
    context_config: ContextConfig = default  # 上下文配置
    initial_cash: float = 100_000       # 初始资金
    commission: CommissionConfig = default   # 手续费
    slippage: SlippageConfig = default  # 滑点

    # 预设记忆
    preset_memories: dict[str, str] = field(default_factory=dict)
```

### DataConfig

```python
@dataclass
class DataConfig:
    # 数据源 (MVP: DataFrame)
    source: dict[str, DataFrame]       # {symbol: ohlcv_dataframe}

    # 时间范围 (可选，默认用数据全部范围)
    start: datetime | None = None
    end: datetime | None = None
```

## 矩阵实验

Runner 支持多维对比实验，自动化 A/B 测试。

```python
class Runner:
    def run_matrix(self,
                   agents: list[AgentProtocol],
                   data: DataConfig,
                   repeats: int = 1,
                   ) -> MatrixResult:
        """
        运行多维对比实验。

        agents × repeats 次回测，自动生成对比报告。
        """
        results = []
        for agent in agents:
            for i in range(repeats):
                config = BacktestConfig(agent=agent, data=data, ...)
                result = self.run(config)
                results.append(result)

        return MatrixResult(results)
```

### 实验维度

```
Prompt A/B:
  agents = [
      AgentFactory.create(model="sonnet", strategy_prompt=prompt_v1),
      AgentFactory.create(model="sonnet", strategy_prompt=prompt_v2),
  ]
  → 哪种策略描述让 Agent 表现更好？

Model A/B:
  agents = [
      AgentFactory.create(model="claude-sonnet", strategy_prompt=same),
      AgentFactory.create(model="claude-opus", strategy_prompt=same),
      AgentFactory.create(model="gpt-4o", strategy_prompt=same),
  ]
  → 哪个模型最适合这个策略？

Agent vs Baseline:
  agents = [
      AgentFactory.create(model="sonnet", strategy_prompt=prompt),
      AgentFactory.create_rule_agent(rules=same_logic),
  ]
  → Agent 推理比 if/else 强多少？

一致性测试:
  agents = [same_agent]
  repeats = 10
  → 策略 prompt 够明确吗？还是模型在猜？
```

## Runner 生命周期

```
Runner.run(config) 被调用
    │
    ├── Phase 1: 初始化
    │   ├── 创建 workspace 目录
    │   ├── 初始化 Engine (加载数据)
    │   ├── 初始化 Memory (写入 playbook, 加载预设)
    │   ├── 初始化 Context Manager
    │   └── 初始化 Recorder
    │
    ├── Phase 2: 主循环 (对每根 bar)
    │   ├── engine.advance() → 推进时间
    │   ├── engine.match_orders() → 撮合待执行订单
    │   ├── trigger.should_decide() → 是否需要 Agent 决策？
    │   │   ├── No → continue
    │   │   └── Yes ↓
    │   ├── context_mgr.assemble() → 组装上下文
    │   ├── agent.decide(context, tools) → Agent 决策
    │   ├── recorder.record(decision) → 记录决策
    │   └── _trigger_memory_moments() → 驱动记忆
    │
    └── Phase 3: 收尾
        ├── eval.evaluate() → 计算三维评估
        ├── 保存 BacktestResult
        └── 保存 workspace 快照
```

## Recorder

Recorder 负责忠实记录每条 Decision，为 Eval 提供审计数据。

```python
class Recorder:
    def __init__(self, workspace: Path):
        self.decisions_file = workspace / "decisions.jsonl"

    def record(self, decision: Decision) -> None:
        """
        将 Decision 追加到 decisions.jsonl。
        JSONL 格式，每行一条记录。
        """
        line = json.dumps(asdict(decision), default=str)
        self.decisions_file.open("a").write(line + "\n")

    def all_decisions(self) -> list[Decision]:
        """读取所有决策记录"""
        ...
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
