Feature: FinnhubAdapter — 美股日线 OHLCV 数据适配器（后备源）
  通过 Finnhub REST API 获取美股日线数据，满足 MarketAdapter Protocol。
  所有测试 mock finnhub client，不依赖真实 API Key。

  Background:
    Given 一个 mock finnhub 环境

  Scenario: 列名标准化
    Given finnhub 返回原始 candle 数据
    When 调用 finnhub fetch "AAPL"
    Then finnhub 返回 DataFrame 包含标准列 "date,open,high,low,close,volume"

  Scenario: date 列为 datetime 类型
    Given finnhub 返回原始 candle 数据
    When 调用 finnhub fetch "AAPL"
    Then finnhub date 列类型为 datetime

  Scenario: 数据按日期升序排列
    Given finnhub 返回倒序 candle 数据
    When 调用 finnhub fetch "AAPL"
    Then finnhub 数据按 date 升序排列

  Scenario: 指定日期范围透传
    When 调用 finnhub fetch "AAPL" 从 "2024-01-01" 到 "2024-06-01"
    Then finnhub client 收到正确的 UNIX 时间戳范围

  Scenario: 默认拉取最近一年
    When 调用 finnhub fetch "AAPL" 不指定日期
    Then finnhub client 收到的 from_ 距今约 365 天
