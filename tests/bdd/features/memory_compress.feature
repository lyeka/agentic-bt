Feature: Memory 自动压缩 — 超限触发 LLM 压缩
  memory.md 超过 MEMORY_MAX_CHARS 时自动压缩，未超限时不触发。

  Scenario: 超限内容触发压缩
    Given 一个已挂载压缩的 Kernel
    And memory.md 内容超过上限
    When 触发 memory 写入事件
    Then memory.md 字数在上限内
    And 收到 memory.compressed 事件

  Scenario: 未超限不触发压缩
    Given 一个已挂载压缩的 Kernel
    And memory.md 内容未超过上限
    When 触发 memory 写入事件
    Then memory.md 内容不变
    And 未收到 memory.compressed 事件

  Scenario: 压缩保持 markdown 格式
    Given 一个已挂载压缩的 Kernel
    And memory.md 内容超过上限
    When 触发 memory 写入事件
    Then 压缩结果是 markdown 格式
