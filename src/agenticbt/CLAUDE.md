# agenticbt/
> L2 | 父级: /CLAUDE.md

## 成员清单
`__init__.py`: 公共 API 入口，暴露 run/BacktestConfig/BacktestResult/LLMAgent/load_csv/make_sample_data
`models.py`: 所有 dataclass 数据结构，无业务逻辑，全模块共享基础层；含 ContextConfig/Context 上下文类型
`engine.py`: 确定性市场模拟，多资产 dict 数据/limit+stop 订单/bracket OCO/做空/风控4检查/百分比滑点/部分成交；recent_bars()/market_history()
`indicators.py`: IndicatorEngine，pandas-ta 防前瞻包装，calc/list_indicators
`memory.py`: 文件式记忆系统，Workspace 隔离 + Memory(log/note/recall)
`tools.py`: ToolKit，OpenAI function calling schema + 工具分发 + 调用追踪；含 market_history 工具
`context.py`: ContextManager，五层认知上下文组装与格式化；assemble() → Context，_format_text() → formatted_text
`agent.py`: LLMAgent，ReAct loop（OpenAI SDK 兼容），AgentProtocol 接口；context: Context 类型
`runner.py`: Runner 回测主循环；集成 ContextManager，传入决策历史组装近期决策
`eval.py`: Evaluator，绩效指标(trade_log 真实盈亏) + 遵循度报告计算
`data.py`: load_csv 标准化加载 + make_sample_data 模拟数据生成

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
