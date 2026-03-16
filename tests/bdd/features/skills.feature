Feature: Skill Engine — 发现/注入/显式展开/模型自主调用
  Agent Skills 按需注入 system prompt，支持显式命令和模型自主调用。

  Background:
    Given 一个临时 skill 工作区

  Scenario: boot 注入 available_skills XML
    Given 技能根目录存在 skill "alpha"
    When Kernel 使用该 skill 根目录启动
    Then system prompt 包含 "<available_skills>"
    And system prompt 包含 "<name>alpha</name>"

  Scenario: 未注册 read 也能注入技能摘要
    Given 技能根目录存在 skill "alpha"
    When Kernel 在无 read 工具时启动
    Then system prompt 包含 "<available_skills>"
    And system prompt 包含 "<name>alpha</name>"

  Scenario: 显式命令 /skill:name 会展开正文
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    And LLM 返回 stop 内容 "已执行"
    When 用户发送 "/skill:alpha run check"
    Then 历史用户消息包含 "<skill name=\"alpha\""
    And 历史用户消息包含 "run check"
    And 回复为 "已执行"

  Scenario: 未知 skill 显式命令直接报错且不调用 LLM
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    When 用户发送 "/skill:ghost test"
    Then 回复包含 "未知 skill"
    And LLM 调用次数为 0

  Scenario: disable-model-invocation 仅隐藏自动路由
    Given 技能根目录存在隐藏 skill "hidden"
    And Kernel 使用该 skill 根目录启动
    Then system prompt 不包含 "<name>hidden</name>"
    When 调用 skill_invoke 名称 "hidden"
    Then skill_invoke 结果包含 "禁用"
    When 用户发送 "/skill:hidden run"
    Then 历史用户消息包含 "<skill name=\"hidden\""

  Scenario: 模型可像调用内置工具一样调用 skill_invoke
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    And LLM 先调用 skill_invoke 再 stop
    When 用户发送 "请按 alpha skill 处理"
    Then LLM 调用次数为 2
    And 工具响应包含 "\"name\": \"alpha\""
    And 回复为 "完成 skill"

