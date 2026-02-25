Feature: LLM Agent 交易决策
  Agent 通过 ReAct loop 使用工具做出交易决策。
  决策记录捕获完整的推理链和工具调用。

  Scenario: Agent 调用工具后做出买入决策
    Given 一个 mock Agent 按顺序响应工具调用后买入
    When Agent 做出决策
    Then decision.action 应为 "buy"
    And decision.symbol 应为 "AAPL"
    And decision.reasoning 应包含 "RSI"
    And decision.tool_calls 应有 2 条记录

  Scenario: Agent 不交易则为 hold
    Given 一个 mock Agent 只查询指标后观望
    When Agent 做出决策
    Then decision.action 应为 "hold"
    And decision.tool_calls 应有 1 条记录

  Scenario: ReAct loop 在 max_rounds 后终止
    Given 一个 mock Agent 永远返回工具调用
    And max_rounds 设为 3
    When Agent 做出决策
    Then 应在 3 轮后返回 decision
    And decision.action 应为 "hold"

  Scenario: Decision 记录完整审计信息
    Given 一个 mock Agent 按顺序响应工具调用后买入
    When Agent 做出决策
    Then decision 应包含 market_snapshot
    And decision 应包含 account_snapshot
    And decision 应包含 tokens_used
    And decision 应包含 latency_ms

  Scenario: LLM API 异常时重试后返回 hold
    Given 一个持续抛出异常的 mock LLM 客户端
    When Agent 做出决策
    Then decision.action 应为 "hold"
    And 不抛出异常
