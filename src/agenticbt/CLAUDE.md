# agenticbt/
> L2 | 父级: /CLAUDE.md

## 成员清单
`__init__.py`: 公共 API 入口，暴露 run/BacktestConfig/BacktestResult/LLMAgent/load_csv/make_sample_data
`models.py`: 所有 dataclass 数据结构，无业务逻辑，全模块共享基础层；含 ContextConfig/Context 上下文类型
`engine.py`: 确定性市场模拟，多资产 dict 数据/limit+stop 订单/bracket OCO/做空/风控4检查/百分比滑点/部分成交；recent_bars()/market_history()
`indicators.py`: IndicatorEngine，pandas-ta 防前瞻包装，calc/list_indicators
`memory.py`: 文件式记忆系统，Workspace 隔离 + Memory(log/note/recall)
`tools.py`: ToolKit，OpenAI function calling schema（含用途+返回值说明） + 工具分发 + 调用追踪；含 market_history + compute 沙箱计算工具
`sandbox.py`: exec_compute 沙箱执行器，eval-first 策略/黑名单 builtins（~55 标准条目）/_safe_import 白名单模块/Trading Coreutils（含 bbands/macd 高级 helper）/print→_stdout 捕获/SIGALRM 超时/traceback 增强/_serialize 自动降维（含 tuple 递归序列化）
`context.py`: ContextManager，五层认知上下文组装与 XML 结构化格式化；assemble() → Context（含持仓盈亏注入），_format_text() → XML 标签分隔的 formatted_text
`agent.py`: LLMAgent，ReAct loop（OpenAI SDK 兼容），AgentProtocol 接口；三层 System Prompt 架构（框架模板+策略）；支持自定义 system_prompt 覆盖；TraceWriter 注入追踪 llm_call/tool_call
`runner.py`: Runner 回测主循环；集成 ContextManager + TraceWriter，追踪 agent_step/context/decision；decision_to_dict 完整持久化
`tracer.py`: TraceWriter 本地 JSONL 追踪写入器 + decision_to_dict 序列化；对齐 OTel GenAI Semantic Conventions
`eval.py`: Evaluator，绩效指标(trade_log 真实盈亏) + 遵循度报告计算
`data.py`: load_csv 标准化加载 + make_sample_data 模拟数据生成（regime 参数：random/trending/mean_reverting/volatile/bull_bear）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
