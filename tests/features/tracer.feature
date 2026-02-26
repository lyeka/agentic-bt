Feature: 可观测性追踪 — trace.jsonl
  TraceWriter 为回测过程提供结构化追踪，
  将 ReAct loop 的每一步写入本地 JSONL 文件，
  对齐 OTel GenAI Semantic Conventions。

  # ── TraceWriter 基础 ────────────────────────────────────────

  Scenario: TraceWriter 写入合法 JSONL
    Given 一个指向临时文件的 TraceWriter
    When 写入 3 条不同类型的事件
    Then JSONL 文件应有 3 行
    And 每行应为合法 JSON
    And 每行应包含 "type" 和 "ts" 字段

  Scenario: TraceWriter 自动填充 bar_index
    Given 一个指向临时文件的 TraceWriter
    When 设置 bar_index 为 5
    And 写入一条不含 bar_index 的事件
    Then 该事件的 bar_index 应为 5

  # ── llm_call 事件 ───────────────────────────────────────────

  Scenario: trace.jsonl 记录 LLM 调用
    Given 一个指向临时文件的 TraceWriter
    When 写入一条 llm_call 事件
    Then 该事件应包含 "input_messages" 字段
    And 该事件应包含 "finish_reason" 字段
    And 该事件应包含 "tokens" 字段
    And 该事件应包含 "duration_ms" 字段

  # ── tool_call 事件 ──────────────────────────────────────────

  Scenario: trace.jsonl 记录工具调用
    Given 一个指向临时文件的 TraceWriter
    When 写入一条 tool_call 事件
    Then 该事件应包含 "tool" 字段
    And 该事件应包含 "input" 字段
    And 该事件应包含 "output" 字段
    And 该事件应包含 "duration_ms" 字段

  # ── decision 事件 ───────────────────────────────────────────

  Scenario: decision_to_dict 保留完整 Decision 字段
    Given 一个包含所有字段的 Decision 对象
    When 调用 decision_to_dict
    Then 结果应包含 "market_snapshot" 字段
    And 结果应包含 "tool_calls" 字段
    And 结果应包含 "order_result" 字段
    And 结果应包含 "latency_ms" 字段
    And 结果应包含 "indicators_used" 字段

  # ── Runner 集成 ─────────────────────────────────────────────

  Scenario: Runner 回测产生 trace.jsonl
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 始终 hold
    When 执行回测
    Then workspace 应包含 trace.jsonl
    And trace.jsonl 应包含 "agent_step" 类型事件
    And trace.jsonl 应包含 "context" 类型事件
    And trace.jsonl 应包含 "decision" 类型事件

  Scenario: decisions.jsonl 持久化完整 Decision 字段
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 始终 hold
    When 执行回测
    Then decisions.jsonl 每行应包含 "market_snapshot"
    And decisions.jsonl 每行应包含 "tool_calls"
    And decisions.jsonl 每行应包含 "indicators_used"
    And decisions.jsonl 每行应包含 "latency_ms"
