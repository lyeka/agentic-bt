Feature: Context Ops — 会话上下文管理
  会话上下文管理纯函数层：token 估算、上下文统计、对话历史压缩。
  session.history 是有限资源（受 context window 约束），compact 统一接管裁剪。

  Background:
    Given 一个空上下文环境

  Scenario: 空历史的 token 估算为零
    When 估算空历史的 token
    Then token 估算结果为 0

  Scenario: 有消息历史的 token 估算大于零
    Given 一条 user 消息 "你好"
    When 估算历史的 token
    Then token 估算结果大于 0

  Scenario: 上下文统计包含正确的消息计数和使用率
    Given 一条 user 消息 "你好"
    And 一条 assistant 消息 "你好！"
    When 获取上下文统计（context_window 1000）
    Then 统计消息总数为 2
    And 统计 user 消息数为 1
    And 统计使用率大于 0

  Scenario: 太短的历史不压缩
    Given 一条 user 消息 "你好"
    And 一条 assistant 消息 "你好！"
    When 压缩历史（recent_turns 3）
    Then 压缩的消息数为 0
    And 保留的消息数为 2

  Scenario: 压缩对话历史返回摘要和最近消息
    Given 5 轮完整对话
    When 压缩历史（recent_turns 2）
    Then 压缩的消息数大于 0
    And 保留的消息数大于 0
    And 摘要非空

  Scenario: 压缩后最近消息保持原样
    Given 5 轮完整对话
    When 压缩历史（recent_turns 2）
    Then 最近 2 轮消息内容不变

  Scenario: 摘要包含结构化内容
    Given 5 轮完整对话
    When 压缩历史（recent_turns 2）
    Then 摘要非空
