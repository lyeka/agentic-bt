# subagents/
> L2 | 父级: ../CLAUDE.md

Sub-Agent 定义、运行与系统集成。类比 skills/：发现/解析/注册/调用/工具生成/团队描述。

## 成员清单

runner.py: SubAgentDef、SubAgentResult、filter_schemas、run_subagent —— 领域无关的 Sub-Agent 纯函数层：数据类型 + 通用 ReAct loop + 资源管控。`_call_llm` 委托 `athenaclaw.llm.retry.call_with_retry`（3 次指数退避，耗尽后返回 None 而非 raise，保持 `run_subagent` 不抛异常的契约）
loader.py: 薄包装，re-export discover_subagent_files 相关（实为 load_subagents/parse_subagent_file）
models.py: 薄包装，re-export SubAgentDef/SubAgentResult
system.py: discover_subagent_files、parse_subagent_file、load_subagents、SubAgentSystem —— 发现/解析/注册/调用/工具生成/团队描述

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
