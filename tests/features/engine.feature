Feature: 确定性市场模拟引擎
  引擎负责数据回放、订单撮合、仓位核算和风控拦截。
  引擎是不可侵犯的确定性层，不做任何交易决策。

  Background:
    Given 初始资金 100000
    And 市场数据:
      | date       | open  | high  | low   | close | volume  |
      | 2024-01-01 | 100.0 | 105.0 | 99.0  | 103.0 | 1000000 |
      | 2024-01-02 | 103.5 | 108.0 | 102.0 | 107.0 | 1200000 |
      | 2024-01-03 | 107.0 | 110.0 | 106.0 | 109.0 | 900000  |

  Scenario: 逐 bar 推进时间
    When 引擎推进到 bar 0
    Then 当前日期应为 "2024-01-01"
    And 当前收盘价应为 103.0
    When 引擎推进到 bar 1
    Then 当前日期应为 "2024-01-02"

  Scenario: bar 0 提交的买单在 bar 1 开盘价成交
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 103.5 成交
    And 持仓 "AAPL" 应为 100 股 均价 103.5
    And 现金应为 89650.0

  Scenario: 平仓自动计算数量
    Given 引擎在 bar 0
    And 持有 "AAPL" 100 股 均价 100.0
    When 提交平仓 "AAPL"
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "AAPL" 应为 0 股
    And 已实现盈亏应为正数

  Scenario: 风控拒绝超限仓位
    Given 风控配置 max_position_pct 为 0.10
    And 引擎在 bar 0
    When 提交买入 "AAPL" 200 股
    Then 订单应被拒绝
    And 拒绝原因应包含 "仓位超限"

  Scenario: 滑点影响成交价
    Given 滑点配置为 0.01
    And 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 成交价应为 103.51

  Scenario: 手续费扣减现金
    Given 手续费率为 0.001
    And 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 手续费应为 10.35

  Scenario: 权益曲线正确跟踪
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    And 引擎推进到 bar 2
    Then 权益曲线应有 3 个数据点
    And 最终权益应反映持仓市值变化
