Feature: CompositeMarketAdapter — 多数据源路由
  聚合多个 MarketAdapter，按 matcher 函数自动路由 symbol 到正确数据源。
  对外满足 MarketAdapter Protocol，market.py 零感知。

  Scenario: 有匹配路由时走对应 adapter
    Given 注册 "tushare" adapter 匹配 A 股 symbol
    And 注册 "yfinance" adapter 作为 fallback
    When composite fetch history "000001.SZ" interval "1d"
    Then 实际调用的 adapter 是 "tushare"

  Scenario: 无匹配路由走 fallback
    Given 注册 "tushare" adapter 匹配 A 股 symbol
    And 注册 "yfinance" adapter 作为 fallback
    When composite fetch history "AAPL" interval "1d"
    Then 实际调用的 adapter 是 "yfinance"

  Scenario: 港股路由可独立命中 HK adapter
    Given 注册 "tushare" adapter 匹配 A 股 symbol
    And 注册 "futu" adapter 匹配港股 symbol
    And 注册 "yfinance" adapter 作为 fallback
    When composite fetch history "00700.HK" interval "1d"
    Then 实际调用的 adapter 是 "futu"

  Scenario: 多条路由按注册顺序 first-match-wins
    Given 注册 "first" adapter 匹配所有 symbol
    And 注册 "second" adapter 匹配所有 symbol
    When composite fetch history "ANY" interval "1d"
    Then 实际调用的 adapter 是 "first"

  Scenario: 无匹配且无 fallback 抛异常
    Given 注册 "tushare" adapter 匹配 A 股 symbol
    When composite fetch history "AAPL" interval "1d" 无 fallback
    Then 抛出 ValueError

  Scenario: 仅 fallback 处理所有 symbol
    Given 注册 "yfinance" adapter 作为 fallback
    When composite fetch history "000001.SZ" interval "1d"
    Then 实际调用的 adapter 是 "yfinance"
