# tests/
> L2 | 父级: /CLAUDE.md

## 成员清单
`conftest.py`: 共享 fixtures（当前空，按需扩展）
`features/engine.feature`: Engine 市场模拟行为规格（含 recent_bars scenario）
`features/indicators.feature`: 技术指标计算行为规格
`features/memory.feature`: 记忆系统行为规格
`features/tools.feature`: 工具桥接层行为规格（含 market_history scenarios）
`features/agent.feature`: Agent ReAct 决策行为规格
`features/runner.feature`: 回测编排行为规格
`features/eval.feature`: 评估计算行为规格
`features/context.feature`: 上下文工程行为规格（11 scenarios）
`test_engine.py`: engine.feature step definitions（含 recent_bars steps）
`test_indicators.py`: indicators.feature step definitions
`test_memory.py`: memory.feature step definitions
`test_tools.py`: tools.feature step definitions（含 market_history steps）
`test_agent.py`: agent.feature step definitions（mock LLM，context: Context 类型）
`test_runner.py`: runner.feature step definitions（mock Agent，context: Context 类型）
`test_eval.py`: eval.feature step definitions
`test_context.py`: context.feature step definitions（fixture: cctx）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
