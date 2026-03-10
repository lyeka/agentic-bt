Feature: YFinanceAdapter — 美股日线 OHLCV 数据适配器
  通过 yfinance 获取美股日线数据，满足 MarketAdapter Protocol。
  所有测试 mock yfinance API，不依赖真实网络。

  Background:
    Given 一个 mock yfinance 环境

  Scenario: 列名标准化
    Given yfinance 返回原始日线数据
    When 调用 yfinance fetch "AAPL"
    Then yfinance 返回 DataFrame 包含标准列 "date,open,high,low,close,volume"

  Scenario: date 列为 datetime 类型
    Given yfinance 返回原始日线数据
    When 调用 yfinance fetch "AAPL"
    Then yfinance date 列类型为 datetime

  Scenario: 数据按日期升序排列
    Given yfinance 返回倒序日线数据
    When 调用 yfinance fetch "AAPL"
    Then yfinance 数据按 date 升序排列

  Scenario: 指定日期范围透传
    When 调用 yfinance fetch "AAPL" 从 "2024-01-01" 到 "2024-06-01"
    Then yfinance.download 收到 start "2024-01-01" 和 end "2024-06-01"

  Scenario: 默认拉取最近一年
    When 调用 yfinance fetch "AAPL" 不指定日期
    Then yfinance.download 收到的 start 距今约 365 天
