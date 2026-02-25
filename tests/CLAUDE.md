# tests/
> L2 | 父级: /CLAUDE.md

## 成员清单
`conftest.py`: 共享 fixtures（当前空，按需扩展）
`features/engine.feature`: Engine 市场模拟行为规格
`features/indicators.feature`: 技术指标计算行为规格
`features/memory.feature`: 记忆系统行为规格
`features/tools.feature`: 工具桥接层行为规格
`features/agent.feature`: Agent ReAct 决策行为规格
`features/runner.feature`: 回测编排行为规格
`features/eval.feature`: 评估计算行为规格
`test_engine.py`: engine.feature step definitions
`test_indicators.py`: indicators.feature step definitions
`test_memory.py`: memory.feature step definitions
`test_tools.py`: tools.feature step definitions
`test_agent.py`: agent.feature step definitions（mock LLM）
`test_runner.py`: runner.feature step definitions（mock Agent）
`test_eval.py`: eval.feature step definitions

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
