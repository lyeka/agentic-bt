Feature: TushareAdapter — A 股 OHLCV 数据适配器
  通过 tushare Pro API 获取 A 股日线、分钟线和最新可用 bar，满足 MarketAdapter Protocol。
  所有测试 mock tushare API，不依赖真实 token。

  Background:
    Given 一个 mock tushare 环境

  Scenario: 日线 history 返回标准列
    Given tushare 返回原始日线数据
    When 调用 tushare fetch history "000001.SZ" interval "1d"
    Then 返回 DataFrame 包含标准列 "date,open,high,low,close,volume"

  Scenario: 分钟 history 使用 stk_mins
    Given tushare 返回原始分钟数据
    When 调用 tushare fetch history "000001.SZ" interval "1m"
    Then date 列类型为 datetime
    And tushare stk_mins 收到 freq "1min"

  Scenario: 最新 bar 使用 rt_min_daily 且只返回一行
    Given tushare 返回原始实时分钟数据
    When 调用 tushare fetch latest "000001.SZ" interval "1m"
    Then tushare rt_min_daily 收到 freq "1MIN"
    And 返回 1 行数据

  Scenario: 数据按 date 升序排列
    Given tushare 返回倒序分钟数据
    When 调用 tushare fetch history "000001.SZ" interval "1m"
    Then 数据按 date 升序排列

  Scenario: 分钟接口权限不足时返回清晰错误
    Given tushare 分钟接口无权限
    When 调用 tushare fetch history "000001.SZ" interval "1m"
    Then 返回错误包含 "tushare 分钟或最新 bar 接口未开通权限"

  Scenario: 上交所 .SS 会归一化为 .SH
    Given tushare 返回原始日线数据
    When 调用 tushare fetch history "600519.SS" interval "1d"
    Then tushare daily 收到 ts_code "600519.SH"
