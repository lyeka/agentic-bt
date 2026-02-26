Feature: 数据生成 — make_sample_data 多行情模式
  make_sample_data 通过 regime 参数控制行情特征，
  为不同策略提供匹配的市场环境。

  Scenario: 默认 regime 与现有行为一致
    Given regime 为 "random"
    When 生成 60 根 bar 的模拟数据
    Then 应返回 60 行 OHLCV DataFrame
    And 所有价格应为正数

  Scenario: trending 行情具有明显上升趋势
    Given regime 为 "trending"
    When 生成 100 根 bar 的模拟数据
    Then 最后 10 根 bar 的均价应高于前 10 根 bar 的均价

  Scenario: mean_reverting 行情零漂移高波动
    Given regime 为 "mean_reverting"
    When 生成 252 根 bar 的模拟数据
    Then 收盘价标准差应大于 trending 行情

  Scenario: volatile 行情极高波动
    Given regime 为 "volatile"
    When 生成 100 根 bar 的模拟数据
    Then 日收益率标准差应大于 0.02

  Scenario: bull_bear 行情前半段涨后半段跌
    Given regime 为 "bull_bear"
    When 生成 100 根 bar 的模拟数据
    Then 前半段均价应低于中间价
    And 后半段均价应低于中间价

  Scenario: 未知 regime 抛出异常
    Given regime 为 "unknown_regime"
    When 尝试生成数据
    Then 应抛出 ValueError

  Scenario: regime 参数不影响 random 的向后兼容
    When 不传 regime 参数生成数据
    And 传 regime="random" 生成数据
    Then 两次结果应完全一致
