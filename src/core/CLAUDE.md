# core/
> L2 | 父级: /CLAUDE.md

## 定位

agenticbt 和 agent 的共享基础层。从 agenticbt 提取的完全独立模块（无 Engine/Memory 依赖）。

## 成员清单
`__init__.py`: 包入口
`sandbox.py`: exec_compute 沙箱执行器，eval-first/黑名单 builtins/白名单 import/Trading Coreutils（latest/crossover/bbands/macd 等）/print→_stdout/SIGALRM 超时/_serialize 自动降维
`indicators.py`: IndicatorEngine，pandas-ta 防前瞻包装，calc(name, df, bar_index)/6 指标（RSI/SMA/EMA/ATR/MACD/BBANDS）
`tracer.py`: TraceWriter 本地 JSONL 追踪写入器，对齐 OTel GenAI Semantic Conventions

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
