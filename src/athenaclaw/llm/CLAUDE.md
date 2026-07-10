# llm/
> L2 | 父级: ../CLAUDE.md

LLM provider 抽象 + 消息模型 + 上下文压缩 + 重试策略，零框架依赖的纯函数/薄封装层。

## 成员清单

providers.py: LLMProvider Protocol（complete + stream，均含 timeout 参数）、LLMResult、OpenAIChatProvider（含 stream，M2 从 Kernel 下沉而来，补 `stream_options={"include_usage":True}` 真实 usage）、AnthropicProvider（官方 anthropic SDK，OpenAI-shape ↔ Anthropic Messages API 双向编解码，内部 wire 格式对 Kernel 透明）—— 统一内部消息与 provider SDK 之间的编解码
messages.py: TurnInput、AttachmentRef、history normalization/render helpers —— 隔离 provider payload
context.py: estimate_tokens、ContextInfo、context_info、CompactResult（含 degraded 标记）、compact_history —— LLM 压缩失败时降级为确定性截断（`_deterministic_summary`）而非静默丢弃历史，由 Kernel 据 `degraded` 标记发 `compaction.degraded` 事件
retry.py: call_with_retry —— 指数退避 + temperature 不兼容自动降级的共享重试策略，供 Kernel（`_do_llm_call`）与 subagents/runner（`_call_llm`）共用，消除此前"subagent 比主循环更健壮"的重复实现

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
