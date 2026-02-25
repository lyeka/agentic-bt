# agenticbt/
> L2 | 父级: /CLAUDE.md

## 成员清单
`__init__.py`: 公共 API 入口，暴露 run/BacktestConfig/BacktestResult/LLMAgent
`models.py`: 所有 dataclass 数据结构，无业务逻辑，全模块共享基础层
`engine.py`: 确定性市场模拟，数据回放/订单撮合/仓位核算/风控拦截
`indicators.py`: IndicatorEngine，pandas-ta 防前瞻包装，calc/list_indicators
`memory.py`: 文件式记忆系统，Workspace 隔离 + Memory(log/note/recall)
`tools.py`: ToolKit，OpenAI function calling schema + 工具分发 + 调用追踪
`agent.py`: LLMAgent，ReAct loop（OpenAI SDK 兼容），AgentProtocol 接口
`runner.py`: Runner 回测主循环 + ContextManager 六层上下文组装
`eval.py`: Evaluator，绩效指标 + 遵循度报告计算

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
