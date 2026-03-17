Feature: Skill 生命周期管理

  验证 reload_skills 热重载机制：安装/删除 skill 后通过 reload 即时生效。

  Background:
    Given 一个临时 skill 工作区

  Scenario: reload_skills 工具重新扫描并更新 system prompt
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    And 技能根目录新增 skill "beta"
    When 调用 reload_skills 工具
    Then system prompt 包含 "beta"
    And reload 结果包含新增 "beta"

  Scenario: 删除 skill 文件后 reload 移除
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    And 技能根目录删除 skill "alpha"
    When 调用 reload_skills 工具
    Then system prompt 不包含 "alpha"
    And reload 结果包含移除 "alpha"

  Scenario: reload 后新 skill 降级检查仍然生效
    Given 技能根目录存在 skill "alpha"
    And Kernel 使用该 skill 根目录启动
    And 技能根目录新增需要工具 "nonexistent" 的 skill "broken"
    When 调用 reload_skills 工具
    Then system prompt 不包含 "broken"
    And system prompt 包含 "alpha"
