Feature: 回测评估
  评估系统计算绩效指标和遵循度报告。

  Scenario: 盈利回测的绩效指标
    Given 权益曲线 [100000, 102000, 101000, 105000]
    And 交易记录 [{"pnl": 2000}, {"pnl": -1000}, {"pnl": 4000}]
    When 计算绩效指标
    Then total_return 应为 0.05
    And max_drawdown 应大于 0
    And sharpe_ratio 应大于 0
    And win_rate 应为 0.667
    And profit_factor 应为 6.0

  Scenario: 无交易的绩效
    Given 权益曲线 [100000, 100000, 100000]
    And 空交易记录
    When 计算绩效指标
    Then total_return 应为 0.0
    And total_trades 应为 0

  Scenario: 遵循度报告统计
    Given 决策记录包含买入卖出和持仓
    When 计算遵循度
    Then action_distribution.buy 应为 1
    And action_distribution.sell 应为 1
    And action_distribution.hold 应为 2
    And decisions_with_indicators 应为 3
