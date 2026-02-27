Feature: compute — 沙箱化 Python 计算工具
  Agent 通过 compute 工具在沙箱中执行任意 Python 代码分析市场数据。
  沙箱保证：防前瞻、防篡改、防超时、防越权。

  Background:
    Given 初始化 compute 测试引擎（50 根 bar 推进到第 30 根）

  # ── 基础计算 ──

  Scenario: 单表达式计算（eval 模式）
    When 调用 compute "df.close.iloc[-1]"
    Then compute 返回当前收盘价标量

  Scenario: 多行代码计算（exec 模式）
    When 调用 compute 多行代码计算 sma 和 above
    Then compute 返回包含 sma 和 above 的 dict

  Scenario: 使用预置 helper 函数
    When 调用 compute "latest(ta.rsi(df.close, 14))"
    Then compute 返回浮点数值

  Scenario: crossover 金叉判断
    When 调用 compute "crossover(df.close.rolling(5).mean(), df.close.rolling(20).mean())"
    Then compute 返回布尔值

  # ── 数据访问 ──

  Scenario: 账户数据通过顶层变量访问
    When 调用 compute "equity"
    Then compute 返回值等于当前账户净值

  Scenario: 账户数据通过 dict 访问
    When 调用 compute "account['cash']"
    Then compute 返回值等于当前现金余额

  Scenario: 多资产数据注入
    Given 初始化多资产 compute 引擎（AAPL 和 SPY）
    When 调用 compute "result = df_aapl.close.corr(df_spy.close)"
    Then compute 返回浮点数值

  # ── 安全边界 ──

  Scenario: 防前瞻 — 数据截断到当前 bar
    When 调用 compute "len(df)"
    Then compute 返回值等于 31

  Scenario: 防篡改 — df.copy() 隔离
    When 调用 compute "df['close'] = 0"
    And 再次调用 compute "df.close.iloc[-1]"
    Then compute 第二次返回原始收盘价

  Scenario: 白名单 import 正常执行
    When 调用 compute 白名单 import numpy 计算均值
    Then compute 返回浮点数值

  Scenario: 禁止导入非白名单模块
    When 调用 compute "__import__('os')"
    Then compute 返回包含 "禁止导入" 的错误

  Scenario: 超时保护
    When 调用 compute 超时代码
    Then compute 返回超时错误

  # ── 错误处理 ──

  Scenario: 语法错误友好提示
    When 调用 compute "def foo(:"
    Then compute 返回包含 SyntaxError 的错误

  Scenario: 运行时错误友好提示
    When 调用 compute "result = 1 / 0"
    Then compute 返回包含 ZeroDivisionError 的错误

  Scenario: 越界访问友好提示
    When 调用 compute "result = df.close.iloc[-999]"
    Then compute 返回包含 IndexError 的错误

  # ── 返回值序列化 ──

  Scenario: Series 自动取最新值
    When 调用 compute "df.close.rolling(20).mean()"
    Then compute 返回浮点数值

  Scenario: numpy 类型自动转 float
    When 调用 compute "np.mean(df.close)"
    Then compute 返回 Python float 类型

  # ── 标准 Python 能力 ──

  Scenario: print 输出通过 _stdout 返回
    When 调用 compute print 后赋值 result
    Then compute 返回浮点数值
    And compute 返回包含 _stdout 的结果

  Scenario: try-except 正常工作
    When 调用 compute try-except 捕获异常
    Then compute 返回包含 caught 的 dict

  Scenario: 错误时也返回 _meta
    When 调用 compute "result = 1 / 0"
    Then compute 返回包含 _meta 的错误结果

  # ── 高级 helper：bbands / macd ──

  Scenario: bbands helper 返回三元组
    When 调用 compute "result = bbands(df.close, 20, 2)"
    Then compute 返回包含 upper middle lower 的三元组

  Scenario: bbands helper 数据不足返回 None 三元组
    When 调用 compute "result = bbands(df.close, 999, 2)"
    Then compute 返回 None 三元组

  Scenario: macd helper 返回三元组
    When 调用 compute "result = macd(df.close)"
    Then compute 返回包含 macd signal histogram 的三元组

  Scenario: macd helper 数据不足返回 None 三元组
    When 调用 compute "result = macd(df.close, fast=999)"
    Then compute 返回 None 三元组
