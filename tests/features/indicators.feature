Feature: 技术指标计算
  指标引擎包裹 pandas-ta，提供统一接口。
  必须防止前瞻——只能使用 bar_index 及之前的数据。

  Background:
    Given 50 根 bar 的历史数据

  Scenario Outline: 计算标准指标
    When 在 bar 49 计算 "<indicator>" 指标
    Then 应返回包含 "value" 的结果
    And 值应为有效数字

    Examples:
      | indicator |
      | RSI       |
      | SMA       |
      | EMA       |
      | ATR       |

  Scenario: MACD 返回多值
    When 在 bar 49 计算 "MACD" 指标
    Then 结果应包含 "macd" "signal" "histogram" 三个值

  Scenario: 防前瞻验证
    When 在 bar 20 计算 "SMA" period=10
    Then 计算只使用 bar 0 到 bar 20 的数据
    And 结果等于手动计算 bar 11-20 收盘价的均值

  Scenario: NaN 安全处理
    When 在 bar 3 计算 "SMA" period=20
    Then 数据不足时应返回 value 为 null

  Scenario: 列出可用指标
    When 查询可用指标列表
    Then 应至少包含 RSI SMA EMA MACD BBANDS ATR
