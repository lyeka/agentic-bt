# AgenticBT 架构设计

> **"Backtest the Trader, Not Just the Strategy."**
> 回测交易员，而不仅仅是策略。

## 核心认知

传统回测测试的是**策略代码**在历史行情中的表现。
AgenticBT 测试的是**一个带策略指令的 AI 交易员**在历史行情中的行为与表现。

测试对象从代码变成了 **Prompt + Model + Memory** 三位一体的交易员。

## 设计哲学

量化交易涉及两种本质不同的认知：

| 认知类型 | 本质 | 归属 |
|---------|------|------|
| 创造性认知 — 理解市场、生成假设、解释结果 | 开放式、概率性 | Agent (LLM) |
| 精确性认知 — 计算指标、撮合订单、执行风控 | 封闭式、确定性 | Framework |

AgenticBT 的核心原则：**Agent 说意图，Framework 说真相。**

- Agent 像人类交易员一样思考、判断、决策
- Framework 像交易终端一样提供数据、计算、执行
- Agent 做所有交易决策，Framework 不代替 Agent 决策
- Framework 通过风控拦截器保护 Agent 不犯致命错误

## 架构总览

```
╔═══════════════════════════════════════════════════════════════╗
║                    AGENT (外部·可替换)                         ║
║                                                               ║
║   Strategy Prompt + LLM Model + Memory State                  ║
║                                                               ║
║        ▲ context              │ actions          ▲ tools      ║
║        │                      ▼                  │            ║
╠════════╧══════════════════════╤══════════════════╧════════════╣
║                       FRAMEWORK                               ║
║                                                               ║
║  Core Tools:                                                  ║
║  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐       ║
║  │ market   │ │ indicator │ │ account  │ │  trade   │       ║
║  │ 行情感知  │ │ 指标计算   │ │ 持仓感知  │ │ 交易执行  │       ║
║  └──────────┘ └───────────┘ └──────────┘ └──────────┘       ║
║                                                               ║
║  Memory Tools:                                                ║
║  ┌──────────────────────────────────────────────────────┐    ║
║  │ memory.log / memory.note / memory.recall             │    ║
║  │ 本质是文件读写，Agent 通过工具操作，不接触路径         │    ║
║  └──────────────────────────────────────────────────────┘    ║
║                                                               ║
║  Framework Modules:                                           ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  ║
║  │ Engine   │ │ Context  │ │ Recorder │ │     Eval      │  ║
║  │ 市场模拟  │ │ 上下文    │ │ 决策记录  │ │ 绩效+遵循+    │  ║
║  │ 订单撮合  │ │ 组装     │ │ 审计追踪  │ │ 一致性评估    │  ║
║  │ 指标引擎  │ │          │ │          │ │               │  ║
║  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  ║
║                                                               ║
║  ┌──────────────────────────────────────────────────────┐    ║
║  │                    Runner (编排器)                     │    ║
║  └──────────────────────────────────────────────────────┘    ║
║                                                               ║
║  ┌──────────────────────────────────────────────────────┐    ║
║  │           Extension Point (MCP / Skills)              │    ║
║  │    新闻情感 · 宏观数据 · 另类数据 · 自定义分析 · ...    │    ║
║  └──────────────────────────────────────────────────────┘    ║
╚═══════════════════════════════════════════════════════════════╝
```

## 五个核心模块

| 模块 | 职责 | 详细文档 |
|------|------|---------|
| **Engine** | 确定性市场模拟：数据回放、指标计算、订单撮合、仓位核算、风控拦截 | [engine.md](engine.md) |
| **Context Manager** | 上下文工程：组装每次 Agent 决策所需的信息 | [context.md](context.md) |
| **Memory** | 文件式记忆系统：日志、笔记、回忆，工作空间隔离 | [memory.md](memory.md) |
| **Eval** | 三维评估：绩效 × 策略遵循度 × 一致性 | [eval.md](eval.md) |
| **Runner** | 编排器：驱动回测循环，连接所有模块 | [runner.md](runner.md) |

## 五个核心工具

| 工具组 | 作用 | Agent 视角 |
|--------|------|-----------|
| **market** | 感知行情 | "现在价格多少？最近走势如何？" |
| **indicator** | 计算指标 | "RSI 是多少？MACD 金叉了吗？" |
| **account** | 感知持仓 | "我的仓位和资金情况？" |
| **trade** | 执行操作 | "买入 100 股 AAPL" |
| **memory** | 记录和回忆 | "记下这个观察 / 上次类似情况怎么处理的？" |

详细设计见 [tools.md](tools.md)。

## Agent Protocol

框架对 Agent 的唯一要求：实现 `AgentProtocol` 接口。

```python
class AgentProtocol(Protocol):
    def decide(self, context: Context, tools: list[Tool]) -> Decision: ...
    def prompted_action(self, prompt: str, tools: list[Tool]) -> None: ...
```

任何实现此接口的 Agent 都能被框架回测——Claude、GPT、本地 LLM、甚至规则引擎。

详细设计见 [agent-protocol.md](agent-protocol.md)。

## 扩展机制

框架核心保持精简，通过 MCP Server 和 Skills 扩展能力：

- 新闻情感分析
- 宏观经济数据
- 另类数据（卫星、网络流量等）
- 自定义分析工具

Agent 自主决定调用哪些扩展工具，框架不干预。

## 与现有框架的本质差异

| 维度 | Backtrader | VectorBT | QLib | **AgenticBT** |
|------|-----------|----------|------|-------------|
| 策略表达 | Python 类继承 | 信号矩阵 | ML 模型 | **自然语言 (Prompt)** |
| 决策者 | 代码 | 代码 | 模型 | **LLM Agent** |
| 风控 | 事后统计 | 无 | 嵌入决策层 | **事中拦截中间件** |
| 评估维度 | 绩效 | 绩效 | 绩效 | **绩效 × 遵循 × 一致性** |
| 记忆机制 | 无 | 无 | 无 | **文件式交易日志** |
| 目标用户 | Python 程序员 | 量化研究员 | ML 工程师 | **任何人** |

## 相关文档

- [Engine 详细设计](engine.md)
- [Tools 详细设计](tools.md)
- [Memory 详细设计](memory.md)
- [Context 详细设计](context.md)
- [Eval 详细设计](eval.md)
- [Agent Protocol 详细设计](agent-protocol.md)
- [Runner 详细设计](runner.md)
- [Roadmap](roadmap.md)
