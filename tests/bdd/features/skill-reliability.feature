Feature: Skill 可靠性保障

  确保 skill 的 requires 合约被正确执行，降级 skill 有可见反馈，
  引用文件缺失产出诊断。

  Background:
    Given 一个临时 skill 工作区

  Scenario: 缺少 required-tools 的 skill 被标记 degraded
    Given 技能根目录存在需要工具 "nonexistent" 的 skill "broken"
    When Kernel 使用该 skill 根目录启动
    Then system prompt 不包含 "broken"
    And 诊断包含 "missing_required_deps"

  Scenario: 缺少 required-bins 的 skill 被标记 degraded
    Given 技能根目录存在需要可执行文件 "no_such_binary_xyz" 的 skill "needs-bin"
    When Kernel 使用该 skill 根目录启动
    Then system prompt 不包含 "needs-bin"
    And 诊断包含 "missing_required_deps"

  Scenario: 必需依赖齐全的 skill 正常可用
    Given 技能根目录存在需要工具 "skill_invoke" 的 skill "valid"
    When Kernel 使用该 skill 根目录启动
    Then system prompt 包含 "valid"

  Scenario: degraded skill 被 skill_invoke 调用时返回清晰错误
    Given 技能根目录存在需要工具 "nonexistent" 的 skill "broken"
    And Kernel 使用该 skill 根目录启动
    When 调用 skill_invoke 名称 "broken"
    Then skill_invoke 结果包含 "降级"

  Scenario: degraded skill 仍可通过显式命令调用
    Given 技能根目录存在需要工具 "nonexistent" 的 skill "broken"
    And Kernel 使用该 skill 根目录启动
    And LLM 返回 stop 内容 "已执行"
    When 用户发送 "/skill:broken test"
    Then 历史用户消息包含 "<skill"

  Scenario: boot 时 skills.loaded 事件包含降级信息
    Given 技能根目录存在需要工具 "nonexistent" 的 skill "broken"
    When Kernel 使用该 skill 根目录启动
    Then 事件 "skills.degraded" 已发射
    And 降级事件包含 skill "broken"

  Scenario: 引用文件不存在时产生 reference_missing 诊断
    Given 技能根目录存在引用 "references/missing.md" 的 skill "ref-test"
    When Kernel 使用该 skill 根目录启动
    Then 诊断包含 "reference_missing"

  Scenario: 引用文件存在时无 reference_missing 诊断
    Given 技能根目录存在引用 "references/exists.md" 的 skill "ref-ok"
    And 引用文件 "references/exists.md" 实际存在于 "ref-ok"
    When Kernel 使用该 skill 根目录启动
    Then 诊断不包含 "reference_missing"
