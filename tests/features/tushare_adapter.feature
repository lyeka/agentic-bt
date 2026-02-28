Feature: TushareAdapter — A 股日线 OHLCV 数据适配器
  通过 tushare Pro API 获取 A 股日线数据，满足 MarketAdapter Protocol。
  所有测试 mock tushare API，不依赖真实 token。

  Background:
    Given 一个 mock tushare 环境

  Scenario: 列名标准化
    Given tushare 返回原始日线数据
    When 调用 fetch "000001.SZ"
    Then 返回 DataFrame 包含标准列 "date,open,high,low,close,volume"

  Scenario: date 列为 datetime 类型
    Given tushare 返回原始日线数据
    When 调用 fetch "000001.SZ"
    Then date 列类型为 datetime

  Scenario: 数据按日期升序排列
    Given tushare 返回倒序日线数据
    When 调用 fetch "000001.SZ"
    Then 数据按 date 升序排列

  Scenario: 指定日期范围透传
    When 调用 fetch "000001.SZ" 从 "20240101" 到 "20240601"
    Then tushare 收到 start_date "20240101" 和 end_date "20240601"

  Scenario: 默认拉取最近一年
    When 调用 fetch "000001.SZ" 不指定日期
    Then tushare 收到的 start_date 距今约 365 天
