# agenticbt/
> L2 | 父级: /CLAUDE.md

## 成员清单
`__init__.py`: 公共 API 入口，暴露 run/BacktestConfig/BacktestResult/LLMAgent/load_csv/make_sample_data
`models.py`: 所有 dataclass 数据结构，无业务逻辑，全模块共享基础层；含 ContextConfig/Context 上下文类型（Context 含 risk_summary 字段）；PerformanceMetrics 含 15 个指标字段
`engine.py`: 确定性市场模拟，多资产 dict 数据/limit+stop 订单/bracket OCO/做空/风控4检查/百分比滑点/部分成交；recent_bars() 完整 OHLCV/market_history()/risk_summary() 风控约束摘要；trade_log 含 commission 字段
`indicators.py`: re-export core/indicators（IndicatorEngine, AVAILABLE_INDICATORS）
`memory.py`: 文件式记忆系统，Workspace 隔离 + Memory(log/note/recall)
`tools.py`: ToolKit，OpenAI function calling schema（含完整 API 文档：compute 预加载变量/helpers/注意事项，trade_execute 风控重试提示） + 工具分发 + 调用追踪；含 market_history + compute 沙箱计算工具
`sandbox.py`: re-export core/sandbox（exec_compute, HELPERS）
`context.py`: ContextManager，五层认知上下文组装与 XML 结构化格式化；assemble() → Context（含持仓盈亏注入 + 风控约束注入），_format_text() → XML 标签分隔 + 完整 OHLCV 表格渲染 + 条件 `<risk>` 块
`agent.py`: LLMAgent，ReAct loop（OpenAI SDK 兼容），AgentProtocol 接口；三层 System Prompt 架构（框架模板+策略）；支持自定义 system_prompt 覆盖；TraceWriter 注入追踪 llm_call/tool_call
`runner.py`: Runner 回测主循环；集成 ContextManager + TraceWriter，追踪 agent_step/context/decision；decision_to_dict 完整持久化
`tracer.py`: re-export core/tracer（TraceWriter） + decision_to_dict 序列化（依赖 models.Decision）
`eval.py`: Evaluator，绩效指标(trade_log 盈亏 + sortino/calmar/volatility/cagr/max_dd_duration/avg_trade/best_worst) + 遵循度报告计算
`data.py`: load_csv 标准化加载 + make_sample_data 模拟数据生成（regime 参数：random/trending/mean_reverting/volatile/bull_bear）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
