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

  Scenario: Sortino 比率计算
    Given 权益曲线 [100000, 102000, 99000, 101000, 105000]
    And 空交易记录
    When 计算绩效指标
    Then sortino_ratio 应大于 0

  Scenario: 最大回撤持续时间
    Given 权益曲线 [100000, 95000, 93000, 96000, 100000, 102000]
    And 空交易记录
    When 计算绩效指标
    Then max_dd_duration 应为 4

  Scenario: 交易统计指标
    Given 权益曲线 [100000, 102000, 101000, 105000]
    And 交易记录 [{"pnl": 2000}, {"pnl": -1000}, {"pnl": 4000}]
    When 计算绩效指标
    Then avg_trade_return 应约为 1666.67
    And best_trade 应为 4000.0
    And worst_trade 应为 -1000.0

  Scenario: 年化波动率
    Given 权益曲线 [100000, 102000, 99000, 101000, 105000]
    And 空交易记录
    When 计算绩效指标
    Then volatility 应大于 0

  Scenario: CAGR 年化收益
    Given 权益曲线 [100000, 102000, 101000, 105000]
    And 空交易记录
    When 计算绩效指标
    Then cagr 应大于 0
