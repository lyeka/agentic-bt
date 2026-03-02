Feature: Kernel 工具与工作区 — Phase 1b/1c 完整验证
  6 个工具（market_ohlcv/compute/read/write/edit/bash）+ 权限 + Session 持久化 + 自举。

  # ── Phase 1b: 能看能算 ──

  Scenario: market_ohlcv 获取行情
    Given 一个带市场工具的 Kernel
    When 调用 market_ohlcv symbol "TEST"
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
    Then 结果内容包含 "test content"

  Scenario: edit 修改文件
    Given 一个带文件工具的 Kernel
    And 工作区已有文件 "notebook/draft.md" 内容 "旧内容"
    When 调用 edit path "notebook/draft.md" old "旧内容" new "新内容"
    Then 工作区文件 "notebook/draft.md" 内容为 "新内容"

  Scenario: 受保护路径无确认回调时放行
    Given 一个带文件工具的 Kernel
    And 路径 "soul.md" 权限为 USER_CONFIRM
    When 调用 write path "soul.md" content "新灵魂"
    Then 工作区文件 "soul.md" 内容为 "新灵魂"

  Scenario: 受保护路径确认拒绝时被拒
    Given 一个带文件工具的 Kernel
    And 路径 "soul.md" 权限为 USER_CONFIRM
    And 注册了拒绝确认的回调
    When 调用 write path "soul.md" content "hack"
    Then 结果包含 error

  Scenario: Session 保存与恢复
    Given 一个有 4 条消息的 Session
    When 保存并重新加载 Session
    Then 恢复后历史有 4 条消息

  Scenario: 空工作区触发自举
    Given 一个空工作区
    When Kernel 启动
    Then system_prompt 包含自举种子
    And system_prompt 包含 "<workspace>"

  Scenario: soul.md 存在时注入灵魂
    Given 一个含 soul.md 的工作区 内容为 "我是价值投资者"
    When Kernel 启动
    Then system_prompt 包含 "我是价值投资者"
