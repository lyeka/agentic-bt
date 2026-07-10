# kernel/
> L2 | 父级: ../CLAUDE.md

系统唯一协调中心：ReAct loop + 声明式 wire/emit + DataStore + 权限 + Skill/SubAgent 集成。

## 成员清单

service.py: 核心实现（~1200行）— Kernel（turn/_do_llm_call/_stream_complete/_call_tool/tool policy/skill 合约验证/降级事件）、Session（含 summary 摘要）、DataStore、Permission、MemoryCompressor 接口、SEED/AUTOMATION/TRADE/WORKSPACE guide 常量、skill_invoke
models.py: 薄包装，re-export DataStore/ExecutionContext/MemoryCompressor/Permission/Session/ToolAccessPolicy 等
prompts.py: 薄包装，re-export AUTOMATION_GUIDE/SEED_PROMPT/TRADE_GUIDE/WORKSPACE_GUIDE
seed.py: SEED_PROMPT 定义——首次启动自举种子 system prompt

## LLM 调用容错

`_do_llm_call` 非 stream 分支委托 `athenaclaw.llm.retry.call_with_retry`（指数退避 + temperature 不兼容降级），exhausted 时 reraise。`llm_max_attempts`/`llm_base_delay`/`llm_timeout_sec` 由 `Kernel.__init__` 接收，来源 `runtime/bundle.py::AgentConfig`。

## 新增事件（M1 可靠性加固）

- `tool.args.invalid`：工具参数非合法 JSON 时发出，同时向模型回一条 `role:tool` 错误消息（不再静默吞异常并回 `{}`）
- `tool.error`：`_call_tool` 捕获 handler 异常时发出，含 error_type/error/traceback；仍向模型返回 `{"error": ...}` 摘要
- `turn.exhausted`：max_rounds 耗尽时发出，回复由裸占位串改为可读提示 + 最后一次 assistant 内容（若有）
- `compaction.degraded`：`compact_history` 因 LLM 压缩失败降级为确定性截断时发出（trigger: auto/overflow）

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
