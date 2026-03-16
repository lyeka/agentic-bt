Feature: YFinanceAdapter — Yahoo Finance OHLCV 数据适配器
  通过 yfinance 获取日线、分钟线和最新可用 bar，满足 MarketAdapter Protocol。
  所有测试 mock yfinance API，不依赖真实网络。

  Background:
    Given 一个 mock yfinance 环境

  Scenario: 日线 history 返回标准列
    Given yfinance 返回原始日线数据
    When 调用 yfinance fetch history "AAPL" interval "1d"
    Then yfinance 返回 DataFrame 包含标准列 "date,open,high,low,close,volume"

  Scenario: 分钟 history 返回 datetime 且按时间升序
    Given yfinance 返回原始分钟数据
    When 调用 yfinance fetch history "AAPL" interval "1m"
    Then yfinance date 列类型为 datetime
    And yfinance 数据按 date 升序排列

  Scenario: latest 模式只返回一行
    Given yfinance 返回原始分钟数据
    When 调用 yfinance fetch latest "AAPL" interval "1m"
    Then yfinance 返回 1 行数据

  Scenario: 上海代码自动转换为 Yahoo 代码
    Given yfinance 返回原始分钟数据
    When 调用 yfinance fetch history "600519.SH" interval "1m"
    Then yfinance Ticker 收到 symbol "600519.SS"

  Scenario: 指定分钟范围透传到 yfinance
    When 调用 yfinance fetch history "AAPL" interval "1m" 从 "2024-01-02 09:30:00" 到 "2024-01-02 10:30:00"
    Then yfinance history 收到 start "2024-01-02 09:30:00" 和 end "2024-01-02 10:31:00"
