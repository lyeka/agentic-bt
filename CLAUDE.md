# AgenticBT - Agent 时代的量化回测框架
Python 3.12+ · Pandas · litellm · ta-lib/pandas-ta

> "Backtest the Trader, Not Just the Strategy."
> 回测交易员，而不仅仅是策略。

## 架构哲学

Agent 说意图，Framework 说真相。LLM Agent 像人类交易员一样思考和决策，确定性引擎负责数据、计算和执行。

## 目录结构

```
docs/          - 设计文档 (9 篇，指导全部开发)
src/           - 源代码 (待创建)
tests/         - 测试 (待创建)
```

<directory>
docs/ - 完整设计文档集 (9 文件: architecture, engine, tools, memory, context, eval, agent-protocol, runner, roadmap)
</directory>

## 核心模块 (规划中)

| 模块 | 职责 | 设计文档 |
|------|------|---------|
| Engine | 确定性市场模拟：数据回放、指标计算、订单撮合、仓位核算、风控拦截 | docs/engine.md |
| Context Manager | 上下文工程：分层组装 Agent 决策输入 | docs/context.md |
| Memory | 文件式记忆：log/note/recall 工具，工作空间隔离 | docs/memory.md |
| Eval | 三维评估：绩效 × 遵循度 × 一致性 | docs/eval.md |
| Runner | 编排器：驱动回测循环，连接所有模块 | docs/runner.md |

## 五个核心工具

market (行情) · indicator (指标) · account (持仓) · trade (交易) · memory (记忆)

详见 docs/tools.md

## 开发状态

当前阶段：设计完成，准备 MVP 开发
路线图：docs/roadmap.md
