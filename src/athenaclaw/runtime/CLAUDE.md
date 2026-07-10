# runtime/
> L2 | 父级: ../CLAUDE.md

入口无关的 Kernel 组装层：统一 tools/permission/wire/trace/session_store/subagent 路径约定。

## 成员清单

bundle.py: AgentConfig（含 `llm_max_attempts`/`llm_base_delay`/`llm_timeout_sec`/`provider`，`from_env()` 读取 `ATHENACLAW_LLM_MAX_ATTEMPTS`/`ATHENACLAW_LLM_BASE_DELAY`/`ATHENACLAW_LLM_TIMEOUT_SEC`/`ATHENACLAW_PROVIDER`）、KernelBundle、build_kernel_bundle、`_build_provider`（M2：按 `AgentConfig.provider` 选择 `AnthropicProvider` / 默认 `OpenAIChatProvider`）—— 组装 Kernel 并注入重试/超时/provider 配置
config.py: 薄包装，re-export AgentConfig
factories.py: 薄包装，re-export `_build_automation_delivery_channels`/`_build_market_adapter`/`_make_adapter`
session_store.py: SessionStore、JsonSessionStore —— 会话持久化基础设施，原子写入 + 兼容旧格式
wiring.py: 薄包装，re-export LLMCompressor/`_on_memory_write`/`_wire_trace`

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
