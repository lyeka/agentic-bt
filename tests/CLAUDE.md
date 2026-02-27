# tests/
> L2 | 父级: /CLAUDE.md

## 成员清单
`conftest.py`: 共享 fixtures + 项目根目录 path 注入（使 examples/ 可导入）
`features/engine.feature`: Engine 市场模拟行为规格（含 recent_bars scenario）
`features/indicators.feature`: 技术指标计算行为规格
`features/memory.feature`: 记忆系统行为规格
`features/tools.feature`: 工具桥接层行为规格（含 market_history scenarios）
`features/agent.feature`: Agent ReAct 决策行为规格
`features/runner.feature`: 回测编排行为规格
`features/eval.feature`: 评估计算行为规格
`features/context.feature`: 上下文工程行为规格（11 scenarios）
`features/data.feature`: 数据生成行为规格（7 scenarios，regime 多行情模式）
`features/tracer.feature`: 可观测性追踪行为规格（7 scenarios）
`features/compute.feature`: 沙箱计算工具行为规格（19 scenarios：基础计算/数据访问/安全边界/错误处理/序列化/标准Python能力）
`test_engine.py`: engine.feature step definitions（含 recent_bars steps）
`test_indicators.py`: indicators.feature step definitions
`test_memory.py`: memory.feature step definitions
`test_tools.py`: tools.feature step definitions（含 market_history steps）
`test_agent.py`: agent.feature step definitions（mock LLM，context: Context 类型）
`test_runner.py`: runner.feature step definitions（mock Agent，context: Context 类型）
`test_eval.py`: eval.feature step definitions
`test_context.py`: context.feature step definitions（fixture: cctx）
`test_data.py`: data.feature step definitions（fixture: dctx）
`test_tracer.py`: tracer.feature step definitions（fixture: trcx）
`test_compute.py`: compute.feature step definitions（fixture: cptx）
`test_e2e_strategies.py`: E2E 策略自动化测试（参数化 5 mock + 2 LLM-only 验证）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
