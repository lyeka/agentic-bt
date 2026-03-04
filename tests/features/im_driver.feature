Feature: IM Driver — 渠道无关交互层
  IM Driver 负责把 Kernel 能力适配到不同 IM 平台（Telegram/Discord 等），
  并提供统一的鉴权、并发控制、进度展示、确认交互与 Session 持久化。

  Background:
    Given 一个 Fake IM backend
    And 一个 IM driver（allowlist 含 "u1"）

  Scenario: 未授权用户被拒绝
    When 用户 "u2" 在会话 "c1" 发送 "hello"
    Then backend 发送拒绝消息
    And kernel 未被调用

  Scenario: 正常对话返回回复并持久化
    When 用户 "u1" 在会话 "c1" 发送 "hi"
    Then backend 发送状态消息
    And backend 发送最终回复 "reply:hi"
    And session 被持久化

  Scenario: 工具进度会更新状态消息
    When 用户 "u1" 在会话 "c2" 发送 "run"
    Then backend 编辑状态消息包含 "tool echo ok"

  Scenario: 确认交互委托给 backend
    Given backend 确认答案为 approve
    When 用户 "u1" 在会话 "c3" 发送 "confirm"
    Then backend 收到确认请求
    And backend 发送最终回复 "confirmed"

  Scenario: 默认不展示过程消息
    Given 一个默认 IM driver（allowlist 含 "u1"）
    When 用户 "u1" 在会话 "c4" 发送 "hi"
    Then backend 不发送状态消息
    And backend 不编辑状态消息
    And backend 发送最终回复 "reply:hi"
