Feature: 回测编排
  Runner 驱动完整回测循环：初始化→主循环→收尾。

  Scenario: 完整回测生命周期
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 始终 hold
    When 执行回测
    Then 应产生 BacktestResult
    And result.decisions 应有 3 条
    And result.workspace_path 应指向有效目录

  Scenario: 订单在下一 bar 成交后作为事件传入
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 在 bar 0 买入 在 bar 1 卖出
    When 执行回测
    Then bar 1 的 context.events 应包含买入成交事件
    And bar 2 的 context.events 应包含卖出成交事件

  Scenario: Context 包含 playbook
    Given 3 根 bar 的测试数据
    And 策略描述 "均值回归策略"
    And 一个记录 context 的 mock Agent
    When 执行回测
    Then 每次 context 应包含 "均值回归策略"

  Scenario: 工作空间保存完整
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 始终 hold
    When 执行回测
    Then workspace 应包含 playbook.md
    And workspace 应包含 decisions.jsonl
    And workspace 应包含 result.json

  Scenario: 成交事件触发 memory.log 写入
    Given 3 根 bar 的测试数据
    And 一个 mock Agent 在 bar 0 买入 在 bar 1 卖出
    When 执行回测
    Then memory 日志应包含成交记录
