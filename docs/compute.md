# Compute — 沙箱化 Python 计算工具

> Trading Agent 的 Bash。
> 一个工具打开无限可能，让 Agent 从"点菜"变成"做菜"。

## 设计动机

### 问题：工具系统是菜单，不是工坊

当前 10 个硬编码工具是一份**菜单**——Agent 只能从预定义选项中选择。

```
indicator_calc(name="RSI", period=14)  ✓ 菜单上有
indicator_calc(name="自定义动量因子")   ✗ 菜单上没有
```

Agent 想计算"20日均线偏离度"？不行。想算"成交量加权RSI"？不行。
想做"多资产相关性矩阵"？不行。每个新指标都需要改源码。

这就像给 Coding Agent 一个 `create_react_component` 工具，
而不是给它 `Write + Bash`。

### 类比：PI 框架的启示

Coding Agent 的质变不是因为有了 100 个专用工具，
而是因为有了 4 个**通用原语**（Read/Write/Edit/Bash）。

```
Coding Agent 原语        Trading Agent 原语
─────────────────        ─────────────────
Read   → 读任何文件       query()   → 查任何数据
Write  → 写任何文件       order()   → 表达任何交易意图
Edit   → 改任何文件       state()   → 管理任何状态
Bash   → 执行任何计算     compute() → 执行任何分析  ← 本文档
```

## 为什么不直接给 Bash？

Bash 操作**真实世界**（文件系统/网络/进程）。
回测 Agent 活在**模拟世界**。直接给 bash = 穿透模拟边界：

```
bash 能做的                    后果
──────────────────────        ──────────────────
cat data.csv                  读到未来数据，前瞻偏差
curl api.com                  非确定性，回测不可重复
echo > /tmp/state             跨 bar 持久化，破坏隔离
python -c "engine._bar=999"   直接作弊
```

compute() 不是"阉割版 bash"，是**模拟世界的 bash**——
同样的开放哲学，但边界是模拟的物理定律。

> 未来做 Live Trading 时，bash 才是正确的工具
> （获取实时新闻、调用 ML 模型、发送告警）。

## 工具接口

### Schema（OpenAI function calling 格式）

```json
{
  "type": "function",
  "function": {
    "name": "compute",
    "description": "在沙箱中执行 Python 代码分析市场数据。...(见下方 man page)",
    "parameters": {
      "type": "object",
      "properties": {
        "code": {
          "type": "string",
          "description": "要执行的 Python 代码"
        },
        "symbol": {
          "type": "string",
          "description": "股票代码（默认主资产）"
        }
      },
      "required": ["code"]
    }
  }
}
```

### Tool Description（LLM 的 man page）

这段文字会作为 tool schema 的 `description` 字段，直接发送给 LLM。
它是 Agent 理解 compute 工具的唯一入口——必须精准、完整、有示例。

```
在沙箱中执行 Python 代码分析市场数据。数据已截断到当前 bar，无法访问未来数据。
这是通用分析终端（Trading Agent 的 Bash），不是“指标菜单”。
你可以用 Python/Series 运算自由创造新指标；下方 helpers 只是快捷方式，不构成能力上限。

可用变量：
  df         — DataFrame（由 symbol 选择，默认主资产），列: date/open/high/low/close/volume，RangeIndex
  open/high/low/close/volume/date — 对应 df 列的 Series 别名（TradingView 风格）
  account    — dict: {cash, equity, positions: {symbol: {size, avg_price}}}
  cash       — 当前现金（等价于 account['cash']）
  equity     — 当前净值（等价于 account['equity']）
  positions  — 当前持仓（等价于 account['positions']）
  pd/np/ta/math — pandas, numpy, pandas_ta, math

预置函数：
  latest(series)          — 取 Series 最新值
  prev(series, n=1)       — 取 Series 前 N 个值
  crossover(fast, slow)   — 金叉判断（fast 上穿 slow）
  crossunder(fast, slow)  — 死叉判断（fast 下穿 slow）
  above(series, val)      — 最新值是否大于阈值
  below(series, val)      — 最新值是否小于阈值
  bbands(close, length, std) → (upper, mid, lower)
  macd(close) → (macd, signal, hist)
  tail(x, n=20)           — 取尾部 N 个元素（返回 list，用于调试）
  nz(x, default=0.0)      — None/NaN/inf → default

返回规则：
  单表达式 → 自动返回计算结果
  多行代码 → 如果最后一行是表达式，会自动返回；也可以显式赋值给 result

序列化（输出治理）：
  Series → 自动取最新值
  DataFrame/长数组 → 自动摘要（不会爆 token）

示例：
  # 自定义因子（不是内置指标名，也能算）
  factor = close.pct_change(10) / (close.pct_change().rolling(20).std() + 1e-9)
  {'rsi': ta.rsi(close, 14), 'factor': factor, 'signal': latest(factor) > 0}

  # 仓位计算
  int(equity * 0.02 / nz(ta.atr(high, low, close, 14), 1.0))
```

## 沙箱设计

### 威胁模型

代码由 LLM 生成（非用户直接输入）。主要防御：

```
必须防御                    不需要防御
──────────────────        ──────────────────
前瞻偏差（访问未来数据）     恶意攻击（代码注入）
无限循环（死循环/递归）      权限提升
数据篡改（修改原始 df）      网络攻击
```

### 方案：exec + 白名单 globals

```python
SAFE_GLOBALS = {
    'pd': pd, 'np': np, 'ta': ta, 'math': math,
    '__builtins__': {},   # 禁用所有内置函数（含 __import__）
}
```

`__builtins__={}` 禁用了 `__import__`、`open`、`exec`、`eval`、`print` 等所有内置函数。
LLM 生成的代码只能使用白名单中的 `pd/np/ta/math` 和预注入的变量。

### 执行策略：eval-first + REPL（最后表达式返回）

```python
def exec_compute(code, df, account, timeout_ms=500):
    # 1) 单表达式 → eval 直接返回值
    # 2) 多行/语句 → exec；若最后一行是表达式，则再 eval 返回（类似 Jupyter）
    # 3) 若显式设置 result，则 result 优先
    ...
```

为什么需要 eval-first + REPL？

`exec()` 会执行但不会自动返回最后表达式的值。
REPL 语义让 Agent 写多行代码时不必总是记得 `result = ...`，
而 eval-first 保证最常见的单表达式用法最简洁。

### 数据注入

```python
symbol = args.get("symbol", engine._symbol)
df = engine._data_by_symbol[symbol].iloc[:bar_index+1].copy()
local_ns = {
    # 主数据源（截断到 bar_index，防前瞻）
    'df': df,
    # TradingView 风格别名（对 df 列的 Series 引用）
    'open': df.open, 'high': df.high, 'low': df.low, 'close': df.close,
    'volume': df.volume, 'date': df.date,

    # 账户状态（dict + 展开的顶层变量）
    'account': {'cash': 85000, 'equity': 102300, 'positions': {...}},
    'cash': 85000,
    'equity': 102300,
    'positions': {...},

    # Trading Coreutils
    'latest': lambda s: ...,
    'prev': lambda s, n=1: ...,
    'crossover': lambda f, s: ...,
    'tail': lambda x, n=20: ...,
    'nz': lambda x, default=0.0: ...,
    ...
}
```

关键约束：
- `df.copy()` — 每次调用都是副本，Agent 无法篡改原始数据
- `.iloc[:bar_index+1]` — 截断在 ToolKit._compute() 中完成，sandbox 不感知 bar_index

### df 的列结构

Engine 在 `__init__` 中做了 `data.reset_index()`：

```
原始数据（DatetimeIndex）:
            open    high    low     close   volume
2024-01-02  172.5   174.2   171.8   173.9   45200000

reset_index() 后（RangeIndex）:
   date        open    high    low     close   volume
0  2024-01-02  172.5   174.2   171.8   173.9   45200000
1  2024-01-03  ...
```

Tool schema 必须写清楚：`df 列: date/open/high/low/close/volume，RangeIndex`。
Agent 用 `df.close` 而非 `df['Close']`。

### 超时保护

```python
signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000)  # 500ms
```

使用 SIGALRM（仅 Unix/macOS）。超时后抛出 TimeoutError，
返回友好错误：`{"error": "计算超时（500ms），请简化代码或减少数据量"}`。

### 返回值序列化

```python
def _serialize(value):
    # 标量：numpy → Python，NaN/inf → None
    # Series：自动取最新值（返回标量）
    # DataFrame：返回摘要对象（shape/columns/tail），避免爆 token
    # dict/list/ndarray：深度序列化 + 硬上限截断
    ...
```

为什么 Series 自动取最新值？
- `eval("df.close.rolling(20).mean()")` 返回 252 个浮点数的 Series
- 直接 JSON 序列化会爆 LLM 的 token 预算
- Agent 99% 的场景只需要最新值
- 如果需要历史序列，Agent 应该在 compute 内部处理后返回摘要

## Trading Coreutils

预注入的 helper 函数，就像 bash 有 `grep/awk/sed`：

```python
HELPERS = {
    'latest':     lambda s: float(s.iloc[-1]),
    'prev':       lambda s, n=1: float(s.iloc[-1-n]),
    'crossover':  lambda f, s: bool(f.iloc[-1] > s.iloc[-1] and f.iloc[-2] <= s.iloc[-2]),
    'crossunder': lambda f, s: bool(f.iloc[-1] < s.iloc[-1] and f.iloc[-2] >= s.iloc[-2]),
    'above':      lambda s, t: bool(s.iloc[-1] > t),
    'below':      lambda s, t: bool(s.iloc[-1] < t),
    'bbands':     lambda close, length=20, std=2.0: ...,
    'macd':       lambda close, fast=12, slow=26, signal=9: ...,
    'tail':       lambda x, n=20: ...,
    'nz':         lambda x, default=0.0: ...,
}
```

效果：
```python
# 没有 helper
close.rolling(20).mean().iloc[-1] > close.rolling(50).mean().iloc[-1]

# 有 helper
above(close.rolling(20).mean(), latest(close.rolling(50).mean()))

# 更简洁
crossover(close.rolling(20).mean(), close.rolling(50).mean())
```

## 可行性审查

### 典型示例（无需发明 DSL，直接用 Python 创造指标）

**示例 1: 自定义因子（多行 + 最后一行表达式自动返回）**
```python
compute("""
mom = close.pct_change(10)
vol = close.pct_change().rolling(20).std()
factor = mom / (vol + 1e-9)
{'factor': factor, 'signal': latest(factor) > 0}
""")
```

**示例 2: 仓位计算（ATR + 空值平滑）**
```python
compute("int(equity * 0.02 / nz(ta.atr(high, low, close, 14), 1.0))")
```

**示例 3: 市场状态识别（REPL 语义）**
```python
compute("""
vol = close.pct_change().rolling(20).std()
trend = close.iloc[-1] / close.iloc[-min(20, len(df))] - 1
'trending' if abs(trend) > 0.05 and nz(vol, 0.0) < 0.02 else 'ranging'
""")
```

### 问题总结

```
问题                              解法                                   影响
──────────────────────            ──────────────────────────────         ──────
多行最后表达式“没有返回值”        REPL 语义：最后表达式自动返回             易用性
Series/DataFrame/长数组爆 token   深度序列化 + 摘要 + 硬上限截断            稳健性
嵌套 numpy/pandas 变字符串         深度序列化，返回 JSON-safe 结构          可解释性
df 列名容易写错                    注入 close/open/high/low/volume/date     易用性
compute 被误解为“指标菜单”         tool description + remediation 强声明     心智模型
```

## 错误处理

```python
# 错误类型 → 友好提示
SyntaxError    → {"error": "SyntaxError: ...", "remediation": "检查 Python 语法"}
NameError      → {"error": "NameError: ...", "remediation": "可用变量: df, open/high/low/close/volume/date, account/cash/equity/positions, pd, np, ta, math；compute 不是指标菜单，可用代码自定义指标"}
TimeoutError   → {"error": "计算超时（500ms）", "remediation": "简化代码或减少数据量"}
IndexError     → {"error": "IndexError: ...", "remediation": "检查数据长度: len(df)"}
ZeroDivision   → {"error": "ZeroDivisionError: ...", "remediation": "检查除数是否为零"}
其他 Exception → {"error": "{Type}: {msg}", "remediation": "检查变量名和数据访问是否正确"}
```

## 与现有工具的关系

```
compute() 是增量，不是替换。现有 10 个工具不变。

indicator_calc  → 简单场景仍然好用（"给我 RSI"）
compute         → 复杂场景的逃生舱（"给我自定义动量因子"）

Agent 自主选择用哪个。简单的用 indicator_calc，复杂的用 compute。
就像 Coding Agent 简单读文件用 Read，复杂操作用 Bash。
```

## 实施路径

### Phase 1: compute() 原语（最小可行奇点）

BDD 先行：Feature → RED → GREEN → Refactor

```
Step 1  tests/features/compute.feature    Gherkin 行为规格
Step 2  src/agenticbt/sandbox.py          沙箱执行器（~80 行）
Step 3  src/agenticbt/tools.py            新增 compute 工具（schema + handler）
Step 4  tests/test_compute.py             step definitions（fixture: cptx）
Step 5  回归验证                           全量测试用例全绿
```

### Phase 2+（未来）

```
query()   — 统一数据查询（合并 market_observe/history/account_status/order_query）
order()   — 表达式化下单（条件订单、算法执行）
state()   — 结构化状态管理（typed、versioned、queryable）
```

## BDD 测试规格

```gherkin
Feature: compute — 沙箱化 Python 计算工具
  Agent 通过 compute 工具在沙箱中执行任意 Python 代码分析市场数据。
  沙箱保证：防前瞻、防篡改、防超时、防越权。

  Background:
    Given 初始资金 100000
    And 加载 50 根模拟 K 线数据
    And 推进到第 30 根 bar

  # ── 基础计算 ──

	  Scenario: 单表达式计算（eval 模式）
	    When Agent 调用 compute "df.close.iloc[-1]"
	    Then 返回当前收盘价标量

	  Scenario: close 别名可用
	    When Agent 调用 compute "close.iloc[-1]"
	    Then 返回当前收盘价标量

	  Scenario: 多行代码计算（exec 模式）
	    When Agent 调用 compute:
	      """
	      sma = df.close.rolling(20).mean().iloc[-1]
	      result = {'sma': sma, 'above': df.close.iloc[-1] > sma}
	      """
	    Then 返回包含 sma 和 above 的 dict

	  Scenario: 多行最后表达式自动返回
	    When Agent 调用 compute:
	      """
	      x = np.mean(close)
	      x
	      """
	    Then 返回浮点数值

  Scenario: 使用预置 helper 函数
    When Agent 调用 compute "latest(ta.rsi(df.close, 14))"
    Then 返回 RSI 浮点数值

  Scenario: crossover 金叉判断
    When Agent 调用 compute "crossover(df.close.rolling(5).mean(), df.close.rolling(20).mean())"
    Then 返回布尔值

  # ── 数据访问 ──

  Scenario: 账户数据通过顶层变量访问
    When Agent 调用 compute "result = equity"
    Then 返回值等于当前账户净值

  Scenario: 账户数据通过 dict 访问
    When Agent 调用 compute "result = account['cash']"
    Then 返回值等于当前现金余额

	  # ── 安全边界 ──

  Scenario: 防前瞻 — 数据截断到当前 bar
    When Agent 调用 compute "len(df)"
    Then 返回值等于 31

  Scenario: 防篡改 — df.copy() 隔离
    When Agent 调用 compute "df['close'] = 0"
    And Agent 再次调用 compute "df.close.iloc[-1]"
    Then 第二次返回原始收盘价

  Scenario: 禁止导入模块
    When Agent 调用 compute "__import__('os')"
    Then 返回 NameError 错误信息

  Scenario: 超时保护
    When Agent 调用 compute "while True: pass"
    Then 返回超时错误信息

  # ── 错误处理 ──

  Scenario: 语法错误友好提示
    When Agent 调用 compute "def foo(:"
    Then 返回包含 SyntaxError 的错误信息

  Scenario: 运行时错误友好提示
    When Agent 调用 compute "result = 1 / 0"
    Then 返回包含 ZeroDivisionError 的错误信息

  Scenario: 越界访问友好提示
    When Agent 调用 compute "result = df.close.iloc[-999]"
    Then 返回包含 IndexError 的错误信息

  # ── 返回值序列化 ──

  Scenario: Series 自动取最新值
    When Agent 调用 compute "df.close.rolling(20).mean()"
    Then 返回最新一个浮点数值

	  Scenario: numpy 类型自动转 float
	    When Agent 调用 compute "np.mean(df.close)"
	    Then 返回 Python float 类型

	  Scenario: dict 深度序列化（Series/numpy 标量）
	    When Agent 调用 compute "result = {'rsi': ta.rsi(close,14), 'mean': np.mean(close)}"
	    Then 返回包含 rsi mean 的 dict 且都是 float

	  Scenario: DataFrame 返回摘要
	    When Agent 调用 compute "df.tail(3)"
	    Then 返回 DataFrame 摘要

	  Scenario: 长数组自动摘要
	    When Agent 调用 compute "list(range(1000))"
	    Then 返回 array 摘要
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
