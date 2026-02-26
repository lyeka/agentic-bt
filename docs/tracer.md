# Tracer — Agent 可观测性

> 你无法优化你看不见的东西。
> 回测不只是跑出一个收益率，更要看清 Agent 为什么做出每一个决策。

## 设计哲学

### 黑箱问题

Agent 回测的核心困境：LLM 收到什么 prompt、返回什么推理、调用了哪些工具、
工具返回什么结果——全部在内存中一闪而过。唯一的输出是一行：

```
bar   0 2024-01-01 ...  hold   tokens=120
```

Decision 有 15 个字段，`decisions.jsonl` 只持久化 7 个，剩下 8 个直接丢弃。
这不是 bug，是架构层面的信息熵损失。

### 三个原则

1. **记录和展示分离**（Unix 哲学）
   先忠实记录到文件，展示方式可以多种：jq、Python 脚本、Web UI。
   一个程序做一件事，做好它。

2. **本地文件优先**（对齐 Memory 的"文件即真理"）
   不依赖外部服务。文件永远可访问，Git diff 友好，人类可直接阅读。

3. **结构化 JSON，不是文本日志**
   可查询、可过滤、可聚合。`jq` 是你的朋友。

## 业界对标

### 三层 Trace 模型（业界共识）

所有主流 Agent 可观测性平台都收敛到同一个层次模型：

```
Trace/Session（一次回测）
  └── Agent Step（一次 ReAct 迭代）
        ├── LLM Call（一次 LLM 请求/响应）
        └── Tool Call（一次工具调用）
```

| 层级 | OTel GenAI | Langfuse | LangSmith | AgentOps |
|------|-----------|----------|-----------|----------|
| 顶层 | `invoke_agent` span | Trace | Root Run | Session |
| 步骤 | 子 span | Span | Run(chain) | — |
| LLM | `gen_ai.chat` span | Generation | Run(llm) | LLMEvent |
| 工具 | `execute_tool` span | Span | Run(tool) | ToolEvent |

参考：
- [OTel GenAI Agent Spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [OTel GenAI Client Spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [Langfuse Data Model](https://langfuse.com/docs/observability/data-model)
- [LangSmith Run Data Format](https://docs.langchain.com/langsmith/run-data-format)
- [AgentOps Core Concepts](https://docs.agentops.ai/v2/concepts/core-concepts)

### OTel GenAI Semantic Conventions 核心字段

LLM Call 必须记录：

| 字段 | OTel 属性 | 说明 |
|------|----------|------|
| model | `gen_ai.request.model` | 模型名 |
| input_tokens | `gen_ai.usage.input_tokens` | 输入 token 数 |
| output_tokens | `gen_ai.usage.output_tokens` | 输出 token 数 |
| finish_reason | `gen_ai.response.finish_reasons` | stop / tool_calls |
| input_messages | `gen_ai.*.message` events | 完整 prompt |
| output | `gen_ai.choice` event | 完整响应 |
| duration_ms | span duration | 调用耗时 |

Tool Call 必须记录：

| 字段 | OTel 属性 | 说明 |
|------|----------|------|
| tool | `gen_ai.tool.name` | 工具名 |
| input | tool arguments | 调用参数 |
| output | tool result | 返回结果 |
| duration_ms | span duration | 执行耗时 |

### 我们的选择

本地 JSONL 文件，字段对齐 OTel 语义。
不引入外部依赖，不需要服务端。
未来接入 Langfuse/LangSmith 只需写 adapter 读 trace.jsonl 推送。

## trace.jsonl 格式

### 5 种事件类型

#### agent_step — bar 开始标记

```json
{
  "type": "agent_step",
  "bar_index": 0,
  "dt": "2024-01-01",
  "ts": "2026-02-25T10:00:00.123"
}
```

#### context — LLM 收到的完整上下文

```json
{
  "type": "context",
  "bar_index": 0,
  "formatted_text": "## 当前行情\n...",
  "market": {"symbol": "AAPL", "close": 173.9, "...": "..."},
  "account": {"cash": 100000, "equity": 100000, "...": "..."},
  "ts": "..."
}
```

#### llm_call — 一次 LLM 请求/响应

```json
{
  "type": "llm_call",
  "bar_index": 0,
  "round": 1,
  "model": "claude-sonnet-4-20250514",
  "input_messages": [
    {"role": "system", "content": "你是一个量化交易员..."},
    {"role": "user", "content": "## 当前行情\n..."}
  ],
  "output_content": null,
  "output_tool_calls": [
    {"id": "call_1", "name": "indicator_calc", "args": "{\"name\":\"RSI\"}"}
  ],
  "finish_reason": "tool_calls",
  "tokens": {"input": 100, "output": 50, "total": 150},
  "duration_ms": 1200,
  "ts": "..."
}
```

#### tool_call — 一次工具调用

```json
{
  "type": "tool_call",
  "bar_index": 0,
  "round": 1,
  "tool": "indicator_calc",
  "input": {"name": "RSI"},
  "output": {"value": 35.2},
  "duration_ms": 1.2,
  "ts": "..."
}
```

#### decision — 完整决策记录

```json
{
  "type": "decision",
  "bar_index": 0,
  "action": "buy",
  "symbol": "AAPL",
  "quantity": 100,
  "reasoning": "RSI 超卖区域，技术面支撑买入",
  "tool_calls": [{"tool": "indicator_calc", "input": {}, "output": {}}],
  "market_snapshot": {},
  "account_snapshot": {},
  "indicators_used": {"RSI": {"value": 35.2}},
  "order_result": {"status": "submitted", "order_id": "..."},
  "model": "claude-sonnet-4-20250514",
  "tokens_used": 150,
  "latency_ms": 2500,
  "ts": "..."
}
```

### 与业界映射

| trace.jsonl type | OTel GenAI | Langfuse | 记录内容 |
|---|---|---|---|
| agent_step | invoke_agent | Trace | bar 开始标记 |
| context | span attribute | Span input | LLM 收到的完整 prompt |
| llm_call | gen_ai.chat | Generation | 请求+响应+tokens+latency |
| tool_call | execute_tool | Span | 工具名+参数+结果+latency |
| decision | agent output | Trace output | 完整 Decision（15 字段） |

## 观测点

### 注入位置

```
Runner.run() 主循环
  │
  ├── engine.advance()
  ├── engine.match_orders()
  │
  ├── ★ trace: agent_step          ← Runner 写入
  │
  ├── ctx_mgr.assemble()
  ├── ★ trace: context              ← Runner 写入
  │
  └── agent.decide()
      │
      └── ReAct loop (1..N rounds)
          │
          ├── ★ trace: llm_call     ← Agent 写入（请求+响应合一）
          │
          └── for each tool_call:
              └── ★ trace: tool_call ← Agent 写入
      │
      ├── ★ trace: decision          ← Runner 写入
      └── _record_decision()
```

### 层级分工

| 层 | 写入事件 | 职责 |
|----|---------|------|
| Runner | agent_step, context, decision | 编排层可观测性 |
| Agent | llm_call, tool_call | ReAct loop 内部可观测性 |

## 使用方式

### jq 查询

```bash
# 看某根 bar 的完整决策过程
cat trace.jsonl | jq 'select(.bar_index==5)'

# 看所有 LLM 调用的 prompt
cat trace.jsonl | jq 'select(.type=="llm_call") | .input_messages'

# 看所有工具调用
cat trace.jsonl | jq 'select(.type=="tool_call") | {tool, input, output, duration_ms}'

# 看 LLM 收到的完整上下文
cat trace.jsonl | jq 'select(.type=="context") | .formatted_text'

# 统计每根 bar 的 LLM 调用轮次
cat trace.jsonl | jq -s '[.[] | select(.type=="llm_call")] | group_by(.bar_index) | map({bar: .[0].bar_index, rounds: length})'

# 找出耗时最长的 LLM 调用
cat trace.jsonl | jq 'select(.type=="llm_call")' | jq -s 'sort_by(-.duration_ms) | .[0]'

# 找出所有失败的工具调用
cat trace.jsonl | jq 'select(.type=="tool_call" and .output.error != null)'
```

## Workspace 结构

```
.agenticbt/runs/{run_id}/
  ├── playbook.md          策略描述
  ├── decisions.jsonl       决策记录（完整 15 字段）
  ├── trace.jsonl           追踪日志（ReAct loop 全链路）
  ├── result.json           绩效汇总
  └── journal/              记忆日志
```

`trace.jsonl` 是 `decisions.jsonl` 的超集：
- `decisions.jsonl` 每根 bar 一行（决策结果）
- `trace.jsonl` 每根 bar 多行（决策过程）

两者共存，各有用途：
- 快速查看决策序列 → `decisions.jsonl`
- 深入调试某次决策 → `trace.jsonl`

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
