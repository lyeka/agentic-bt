Feature: Kernel — 持久投资助手核心协调器
  Kernel 是系统唯一协调中心：ReAct loop + 声明式 wire/emit 管道 + DataStore。
  不依赖 agenticbt，import core/ 公共基础。

  Background:
    Given 一个 Mock LLM 客户端

  Scenario: 基础对话
    Given 一个 Kernel
    When 用户说 "你好"
    Then 返回非空回复

  Scenario: 多轮对话历史保持
    Given 一个 Kernel
    When 用户依次说 "第一句" 和 "第二句"
    Then Session 包含 4 条消息

  Scenario: ReAct loop 执行工具
    Given 一个注册了 echo 工具的 Kernel
    And LLM 先调用 echo 工具再结束
    When 用户说 "测试"
    Then echo 工具被调用 1 次

  Scenario: 声明式管道触发
    Given 一个 Kernel
    And 注册了 "turn.done" 管道
    When 用户说 "你好"
    Then 管道被触发 1 次

  Scenario: 最大轮次保护
    Given 一个注册了 echo 工具的 Kernel
    And LLM 永远返回工具调用
    And max_rounds 设为 3
    When 用户说 "测试"
    Then 返回非空回复

  Scenario: boot 注入 beliefs 到 system prompt
    Given 工作区含 soul.md 内容 "我是价值投资者"
    And 工作区含 memory/beliefs.md 内容 "长期持有优质资产"
    When Kernel boot
    Then system prompt 包含 "我是价值投资者"
    And system prompt 包含 "<beliefs>"
    And system prompt 包含 "长期持有优质资产"

  Scenario: boot 注入 memory index 到 system prompt
    Given 工作区含 soul.md 内容 "灵魂"
    And 工作区含 memory/MEMORY.md 内容 "# Index\n- 宁德时代研究\n- 比亚迪分析"
    When Kernel boot
    Then system prompt 包含 "<memory_index>"
    And system prompt 包含 "宁德时代研究"

  Scenario: boot 无 beliefs 和 memory 时只有 soul
    Given 工作区含 soul.md 内容 "纯净灵魂"
    When Kernel boot
    Then system prompt 包含 "纯净灵魂"
    And system prompt 不包含 "<beliefs>"
    And system prompt 不包含 "<memory_index>"
