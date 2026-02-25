Feature: 文件式记忆系统
  记忆系统使用文件存储，工具是接口。
  每次回测拥有独立工作空间。

  Scenario: 工作空间隔离
    When 创建两个工作空间
    Then 两个工作空间路径不同
    And 各自包含独立的目录结构

  Scenario: Playbook 初始化
    Given 一个新工作空间
    When 用策略描述 "RSI < 30 时买入" 初始化 playbook
    Then playbook.md 应包含 "RSI < 30 时买入"

  Scenario: 日志追加
    Given 一个新工作空间
    When 记录日志 "观察到放量下跌" 日期 "2024-03-15"
    And 记录日志 "RSI 逼近 30" 日期 "2024-03-15"
    Then journal/2024-03-15.md 应包含两条记录

  Scenario: 笔记创建和覆盖
    Given 一个新工作空间
    When 创建笔记 key="position_AAPL" content="持仓 100 股"
    Then notes/position_AAPL.md 内容为 "持仓 100 股"
    When 更新笔记 key="position_AAPL" content="已平仓"
    Then notes/position_AAPL.md 内容为 "已平仓"

  Scenario: 持仓笔记条件读取
    Given 一个新工作空间
    And 笔记 "position_AAPL" 内容 "100 股"
    And 笔记 "position_GOOGL" 内容 "50 股"
    When 读取持仓笔记 持仓列表 ["AAPL"]
    Then 应返回 AAPL 的笔记
    And 不应返回 GOOGL 的笔记

  Scenario: 关键词召回
    Given 一个新工作空间
    And 日志 "2024-01-10" 内容 "AAPL RSI 超卖买入"
    And 日志 "2024-01-11" 内容 "大盘下跌观望"
    And 笔记 "market" 内容 "震荡市"
    When 召回 "RSI 超卖"
    Then 应返回包含 "AAPL RSI 超卖买入" 的结果
