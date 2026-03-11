# core/
> L2 | 父级: /CLAUDE.md

## 定位

agenticbt 和 agent 的共享基础层。从 agenticbt 提取的完全独立模块（无 Engine/Memory 依赖）。

## 成员清单
`__init__.py`: 包入口
`sandbox.py`: exec_compute 沙箱执行器，eval-first/黑名单 builtins/白名单 import/Trading Coreutils（latest/crossover/bbands/macd 等）/print→_stdout/线程安全超时（主线程 SIGALRM + 非主线程 ThreadPoolExecutor 降级）/_serialize 自动降维
`indicators.py`: IndicatorEngine，pandas-ta 防前瞻包装，calc(name, df, bar_index)/6 指标（RSI/SMA/EMA/ATR/MACD/BBANDS）
`tracer.py`: TraceWriter 本地 JSONL 追踪写入器，对齐 OTel GenAI Semantic Conventions
`subagent.py`: 领域无关的 Sub-Agent 纯函数层：SubAgentDef/SubAgentResult 数据类型 + filter_schemas 工具过滤 + run_subagent 通用 ReAct loop（资源管控: token_budget/timeout/max_rounds + 3 次指数退避）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
