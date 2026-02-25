Feature: 工具桥接层
  ToolKit 将 Engine 和 Memory 能力包装为 Agent 可用的工具。
  每次 decide() 创建新的 ToolKit 实例，追踪所有调用。

  Background:
    Given 一个已初始化的引擎和记忆系统

  Scenario: 工具 schema 符合 OpenAI 格式
    When 获取工具 schema 列表
    Then 每个 schema 应有 type 为 "function"
    And 每个 schema 应有 function.name 和 function.parameters

  Scenario: 分发 market_observe
    When 调用工具 "market_observe" 参数 {}
    Then 应返回包含 open high low close volume 的 dict

  Scenario: 分发 indicator_calc
    When 调用工具 "indicator_calc" 参数 {"name": "RSI"}
    Then 应返回包含 value 的指标结果
    And indicator_queries 应记录此次查询

  Scenario: 分发 trade_execute
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 100}
    Then 应返回包含 status 的结果
    And trade_actions 应记录此次交易

  Scenario: 无交易 = hold
    When 只调用 market_observe 和 indicator_calc
    Then trade_actions 应为空列表

  Scenario: 完整调用记录
    When 依次调用 market_observe 和 indicator_calc RSI 和 trade_execute buy
    Then call_log 应有 3 条记录
    And 每条记录包含 tool input output

  Scenario: 分发 order_cancel
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 100}
    And 调用 order_cancel 取消刚提交的订单
    Then order_cancel 应返回 status 为 "cancelled"

  Scenario: 分发 order_query
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 100}
    And 调用工具 "order_query" 参数 {}
    Then 应返回包含 pending_orders 的列表

  Scenario: trade_execute 提交限价买入
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 100, "order_type": "limit", "price": 102.5}
    Then 应返回包含 status 的结果

  Scenario: trade_execute 提交 Bracket 买入
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 10, "stop_loss": 100.0, "take_profit": 115.0}
    Then 应返回包含 status 的结果

  Scenario: Bracket 止损价为 0.0 时正确传入引擎
    When 调用工具 "trade_execute" 参数 {"action": "buy", "symbol": "AAPL", "quantity": 10, "stop_loss": 0.0, "take_profit": 115.0}
    Then 应返回包含 status 的结果
    And 不因 stop_loss 为 0.0 而报错

  Scenario: 工具内部异常时返回错误字典而不崩溃
    When ToolKit 执行一个会抛出异常的工具调用
    Then 应返回包含 error 字段的字典
    And call_log 记录本次失败调用

  Scenario: 多资产引擎中指标计算正确绑定 symbol
    Given 多资产引擎和记忆系统
    When 调用工具 "indicator_calc" 参数 {"name": "RSI", "symbol": "MSFT"}
    Then 应返回包含 value 的指标结果
    And 不因 symbol 错误而报错
