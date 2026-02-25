Feature: 确定性市场模拟引擎
  引擎负责数据回放、订单撮合、仓位核算和风控拦截。
  引擎是不可侵犯的确定性层，不做任何交易决策。

  Background:
    Given 初始资金 100000
    And 市场数据:
      | date       | open  | high  | low   | close | volume  |
      | 2024-01-01 | 100.0 | 105.0 | 99.0  | 103.0 | 1000000 |
      | 2024-01-02 | 103.5 | 108.0 | 102.0 | 107.0 | 1200000 |
      | 2024-01-03 | 107.0 | 110.0 | 106.0 | 109.0 | 900000  |

  Scenario: 逐 bar 推进时间
    When 引擎推进到 bar 0
    Then 当前日期应为 "2024-01-01"
    And 当前收盘价应为 103.0
    When 引擎推进到 bar 1
    Then 当前日期应为 "2024-01-02"

  Scenario: bar 0 提交的买单在 bar 1 开盘价成交
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 103.5 成交
    And 持仓 "AAPL" 应为 100 股 均价 103.5
    And 现金应为 89650.0

  Scenario: 平仓自动计算数量
    Given 引擎在 bar 0
    And 持有 "AAPL" 100 股 均价 100.0
    When 提交平仓 "AAPL"
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "AAPL" 应为 0 股
    And 已实现盈亏应为正数

  Scenario: 风控拒绝超限仓位
    Given 风控配置 max_position_pct 为 0.10
    And 引擎在 bar 0
    When 提交买入 "AAPL" 200 股
    Then 订单应被拒绝
    And 拒绝原因应包含 "仓位超限"

  Scenario: 滑点影响成交价
    Given 滑点配置为 0.01
    And 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 成交价应为 103.51

  Scenario: 手续费扣减现金
    Given 手续费率为 0.001
    And 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 手续费应为 10.35

  Scenario: 权益曲线正确跟踪
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    And 引擎推进到 bar 2
    Then 权益曲线应有 3 个数据点
    And 最终权益应反映持仓市值变化

  Scenario: 有效期为 0 的订单在下一根 bar 过期
    Given 引擎在 bar 0
    When 提交有效期 0 的买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 应无成交记录
    And 应产生 "expired" 类型的引擎事件
    And 挂单列表应为空

  Scenario: 取消挂单
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 取消该订单
    Then 取消结果应为 "cancelled"
    And 挂单列表应为空

  Scenario: 查询挂单列表
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    Then 挂单列表应有 1 条记录
    And 挂单应包含 symbol 为 "AAPL"

  Scenario: 成交后产生 fill 事件
    Given 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 应产生 "fill" 类型的引擎事件

  Scenario: 限价买入 — 价格触及限价时成交
    Given 引擎在 bar 0
    When 提交限价买入 "AAPL" 100 股 限价 102.5
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 102.5 成交
    And 持仓 "AAPL" 应为 100 股 均价 102.5

  Scenario: 限价买入 — 价格未触及时不成交
    Given 引擎在 bar 0
    When 提交限价买入 "AAPL" 100 股 限价 101.0
    And 引擎推进到 bar 1 并撮合订单
    Then 应无成交记录
    And 挂单列表应有 1 条记录

  Scenario: 限价卖出 — 价格触及限价时成交
    Given 引擎在 bar 0
    And 持有 "AAPL" 100 股 均价 100.0
    When 提交限价卖出 "AAPL" 100 股 限价 107.5
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 107.5 成交
    And 持仓 "AAPL" 应为 0 股

  Scenario: 止损卖出 — 价格击穿止损价
    Given 引擎在 bar 0
    And 持有 "AAPL" 100 股 均价 110.0
    When 提交止损卖出 "AAPL" 100 股 止损价 102.5
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 102.5 成交
    And 持仓 "AAPL" 应为 0 股

  Scenario: 止损买入 — 突破价格触发
    Given 引擎在 bar 0
    When 提交止损买入 "AAPL" 100 股 止损价 107.5
    And 引擎推进到 bar 1 并撮合订单
    Then 订单应以 107.5 成交
    And 持仓 "AAPL" 应为 100 股 均价 107.5

  Scenario: 限价单有效期到期未成交自动过期
    Given 引擎在 bar 0
    When 提交有效期 0 的限价买入 "AAPL" 100 股 限价 101.0
    And 引擎推进到 bar 1 并撮合订单
    Then 应无成交记录
    And 应产生 "expired" 类型的引擎事件

  Scenario: 最大持仓数限制
    Given 风控配置 max_open_positions 为 1
    And 引擎在 bar 0
    And 持有 "MSFT" 1 股 均价 100.0
    When 提交买入 "AAPL" 10 股
    Then 订单应被拒绝
    And 拒绝原因应包含 "持仓数量超限"

  Scenario: 组合回撤超限禁止开仓
    Given 风控配置 max_portfolio_drawdown 为 0.05
    And 引擎在 bar 0
    When 模拟组合回撤 10%
    And 提交买入 "AAPL" 10 股
    Then 订单应被拒绝
    And 拒绝原因应包含 "组合回撤超限"

  Scenario: 单日亏损超限禁止开仓
    Given 风控配置 max_daily_loss_pct 为 0.02
    And 引擎在 bar 0
    When 模拟当日亏损 5%
    And 提交买入 "AAPL" 10 股
    Then 订单应被拒绝
    And 拒绝原因应包含 "单日亏损超限"

  Scenario: Bracket 买入 — 主单成交后止损止盈子单激活
    Given 引擎在 bar 0
    When 提交 Bracket 买入 "AAPL" 10 股 止损 100.0 止盈 115.0
    And 引擎推进到 bar 1 并撮合订单
    Then 应产生 "fill" 类型的引擎事件
    And 挂单列表应有 2 条记录

  Scenario: Bracket 止盈触发后止损单自动取消
    Given 引擎在 bar 0
    When 提交 Bracket 买入 "AAPL" 10 股 止损 100.0 止盈 107.5
    And 引擎推进到 bar 1 并撮合订单
    And 引擎推进到 bar 2 并撮合订单
    Then 持仓 "AAPL" 应为 0 股
    And 挂单列表应为空

  Scenario: Bracket 主单被风控拒绝时子单不创建
    Given 风控配置 max_position_pct 为 0.001
    And 引擎在 bar 0
    When 提交 Bracket 买入 "AAPL" 100 股 止损 100.0 止盈 115.0
    Then 订单应被拒绝
    And 挂单列表应为空

  Scenario: 卖空开仓
    Given 引擎在 bar 0
    When 提交卖空 "AAPL" 50 股
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "AAPL" 空头应为 50 股

  Scenario: 空头平仓盈利
    Given 引擎在 bar 0
    And 空头持有 "AAPL" 50 股 均价 110.0
    When 提交平仓 "AAPL"
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "AAPL" 应为 0 股
    And 已实现盈亏应为正数

  Scenario: 空头浮动盈亏方向正确
    Given 引擎在 bar 0
    And 空头持有 "AAPL" 50 股 均价 110.0
    When 引擎推进到 bar 1
    Then 空头浮动盈亏应为正数

  Scenario: 多资产数据加载与快照查询
    Given 多资产引擎包含 "AAPL" 和 "MSFT"
    When 引擎推进到 bar 0
    Then "AAPL" 市场快照收盘价应为 103.0
    And "MSFT" 市场快照收盘价应为 51.0

  Scenario: 跨资产建仓与持仓查询
    Given 多资产引擎包含 "AAPL" 和 "MSFT"
    And 引擎在 bar 0
    When 提交买入 "MSFT" 10 股
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "MSFT" 应为 10 股

  Scenario: 多资产权益合并计算
    Given 多资产引擎包含 "AAPL" 和 "MSFT"
    And 引擎在 bar 0
    And 持有 "AAPL" 10 股 均价 100.0
    And 持有 "MSFT" 10 股 均价 50.0
    When 引擎推进到 bar 1
    Then 权益曲线应有 2 个数据点

  Scenario: 百分比滑点计算正确
    Given 百分比滑点配置为 0.01
    And 引擎在 bar 0
    When 提交买入 "AAPL" 100 股
    And 引擎推进到 bar 1 并撮合订单
    Then 成交价应为 104.535

  Scenario: 成交量约束导致部分成交
    Given 初始资金 1000000
    And 风控配置 max_position_pct 为 1.0
    And 成交量约束配置 max_volume_pct 为 0.001
    And 引擎在 bar 0
    When 提交买入 "AAPL" 4500 股
    And 引擎推进到 bar 1 并撮合订单
    Then 持仓 "AAPL" 应为 1200 股
    And 挂单列表应有 1 条记录

  Scenario: 部分成交后剩余订单继续撮合
    Given 初始资金 1000000
    And 风控配置 max_position_pct 为 1.0
    And 成交量约束配置 max_volume_pct 为 0.001
    And 引擎在 bar 0
    When 提交买入 "AAPL" 4500 股
    And 引擎推进到 bar 1 并撮合订单
    And 引擎推进到 bar 2 并撮合订单
    Then 持仓 "AAPL" 应为 2100 股

  Scenario: 查询最近 N 根 K 线
    Given 初始资金 100000 和 30 根 bar 数据
    When 推进到第 25 根 bar
    And 查询最近 20 根 bar
    Then 应返回 20 条记录且 bar_index 从 6 到 25
