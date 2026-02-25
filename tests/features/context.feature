Feature: 上下文工程 — Agent 决策所需的信息组装与格式化
  ContextManager 将分散在 Engine 和 Memory 中的信息，
  组装为结构化 Context，格式化为 LLM 友好文本。

  Background:
    Given 初始资金 100000 和 30 根 bar 的引擎

  Scenario: Agent 看到近期价格走势
    When 推进到第 25 根 bar 并组装上下文
    Then 上下文应包含最近 20 根 K 线的收盘价

  Scenario: 回测初期走势不足窗口时展示所有可用的
    When 推进到第 5 根 bar 并组装上下文
    Then 上下文应包含 6 根 K 线的收盘价

  Scenario: Agent 看到自己的挂单
    Given 提交了一个限价买入 AAPL 100 股 @ 95.0
    When 组装上下文
    Then 上下文文本应包含挂单信息
    And 挂单信息应包含 "limit" 和 "AAPL"

  Scenario: 无挂单时不展示挂单区域
    When 组装上下文
    Then 上下文文本不应包含 "挂单"

  Scenario: Agent 看到近期决策历史
    Given 已有 5 条历史决策
    When 组装上下文
    Then 上下文应包含最近 3 条决策摘要

  Scenario: 无历史决策时不展示近期决策区域
    When 组装上下文
    Then 上下文文本不应包含 "近期决策"

  Scenario: 成交事件显示成交详情
    Given 本轮有买入成交事件
    When 组装上下文
    Then 上下文文本应包含 "成交"

  Scenario: 过期事件不因缺少字段而报错
    Given 本轮有订单过期事件
    When 组装上下文
    Then 上下文文本应包含 "过期"

  Scenario: 取消事件正确展示
    Given 本轮有订单取消事件
    When 组装上下文
    Then 上下文文本应包含 "取消"

  Scenario: 持仓备注按 symbol 逐行展示
    Given 持有 AAPL 和 MSFT 各 100 股
    And AAPL 持仓备注为 "RSI 超卖建仓"
    And MSFT 持仓备注为 "跟随大盘趋势"
    When 组装上下文
    Then 上下文文本应包含 "AAPL: RSI 超卖建仓"
    And 上下文文本应包含 "MSFT: 跟随大盘趋势"

  Scenario: Playbook 注入系统提示词
    Given playbook 为 "RSI 策略"
    When 组装上下文
    Then context.playbook 应为 "RSI 策略"
