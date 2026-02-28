Feature: Kernel 工具与工作区 — Phase 1b/1c 完整验证
  6 个工具（market.ohlcv/compute/read/write/edit/recall）+ 权限 + Session 持久化 + 自举。

  # ── Phase 1b: 能看能算 ──

  Scenario: market.ohlcv 获取行情
    Given 一个带市场工具的 Kernel
    When 调用 market.ohlcv symbol "TEST"
    Then 结果包含 rows 和 latest
    And DataStore 中存在 "ohlcv:TEST"

  Scenario: compute 使用行情数据计算
    Given 一个带市场工具的 Kernel
    And 已获取 "TEST" 行情
    When 调用 compute code "len(df)"
    Then 结果 result 为正整数

  # ── Phase 1c: 能读能写能记 ──

  Scenario: write 创建文件
    Given 一个带文件工具的 Kernel
    When 调用 write path "notebook/test.md" content "hello"
    Then 工作区文件 "notebook/test.md" 内容为 "hello"

  Scenario: read 读取文件
    Given 一个带文件工具的 Kernel
    And 工作区已有文件 "memory/note.md" 内容 "test content"
    When 调用 read path "memory/note.md"
    Then 结果内容为 "test content"

  Scenario: edit 修改文件
    Given 一个带文件工具的 Kernel
    And 工作区已有文件 "memory/beliefs.md" 内容 "旧信念"
    When 调用 edit path "memory/beliefs.md" old "旧信念" new "新信念"
    Then 工作区文件 "memory/beliefs.md" 内容为 "新信念"

  Scenario: 受保护路径写入被拒
    Given 一个带文件工具的 Kernel
    And 路径 "soul.md" 权限为 USER_CONFIRM
    When 调用 write path "soul.md" content "hack"
    Then 结果包含 error

  Scenario: recall 搜索工作区
    Given 一个带文件工具的 Kernel
    And 工作区已有文件 "notebook/report.md" 内容 "宁德时代年度分析"
    When 调用 recall query "宁德时代"
    Then 结果中包含路径 "notebook/report.md"

  Scenario: Session 保存与恢复
    Given 一个有 4 条消息的 Session
    When 保存并重新加载 Session
    Then 恢复后历史有 4 条消息

  Scenario: 空工作区触发自举
    Given 一个空工作区
    When Kernel 启动
    Then system_prompt 包含自举种子

  Scenario: soul.md 存在时注入灵魂
    Given 一个含 soul.md 的工作区 内容为 "我是价值投资者"
    When Kernel 启动
    Then system_prompt 包含 "我是价值投资者"
