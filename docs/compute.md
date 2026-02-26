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
          "description": "指定主数据源的股票代码（默认主资产）"
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

可用变量：
  df         — 主资产 DataFrame，列: date/open/high/low/close/volume，RangeIndex
  df_{sym}   — 多资产场景下各资产数据（如 df_aapl, df_spy）
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

返回规则：
  单表达式 → 自动返回计算结果
  多行代码 → 将结果赋值给 result 变量

示例：
  result = latest(ta.rsi(df.close, 14))
  result = {'rsi': latest(ta.rsi(df.close)), 'sma_cross': crossover(df.close.rolling(20).mean(), df.close.rolling(50).mean())}
  result = int(equity * 0.02 / latest(ta.atr(df.high, df.low, df.close, 14)))
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

### 执行策略：eval-first

```python
def exec_compute(code, df, account, extra_dfs=None, timeout_ms=500):
    try:
        # 单表达式 → eval 直接返回值
        value = eval(code.strip(), SAFE_GLOBALS, local_ns)
        return {"result": _serialize(value)}
    except SyntaxError:
        # 多行/语句 → exec，从 local_ns 提取 result
        exec(code, SAFE_GLOBALS, local_ns)
        return {"result": _serialize(local_ns.get('result'))}
```

为什么 eval-first？

`exec()` 执行表达式但**丢弃返回值**。如果 Agent 写 `df.close.iloc[-1]`，
exec 会计算但结果消失。eval-first 让单表达式自然返回，
多行代码 fallback 到 exec + 显式 `result = ...`。

### 数据注入

```python
local_ns = {
    # 主数据源（截断到 bar_index，防前瞻）
    'df': engine._data_by_symbol[symbol].iloc[:bar_index+1].copy(),

    # 多资产数据（全部截断 + copy）
    'df_aapl': engine._data_by_symbol['AAPL'].iloc[:bar_index+1].copy(),
    'df_spy':  engine._data_by_symbol['SPY'].iloc[:bar_index+1].copy(),

    # 账户状态（dict + 展开的顶层变量）
    'account': {'cash': 85000, 'equity': 102300, 'positions': {...}},
    'cash': 85000,
    'equity': 102300,
    'positions': {...},

    # Trading Coreutils
    'latest': lambda s: ...,
    'prev': lambda s, n=1: ...,
    'crossover': lambda f, s: ...,
    ...
}
```

关键约束：
- `df.copy()` — 每次调用都是副本，Agent 无法篡改原始数据
- `.iloc[:bar_index+1]` — 截断在 ToolKit._compute() 中完成，sandbox 不感知 bar_index
- 多资产变量名：`df_{symbol.lower().replace('.','_').replace('-','_')}`

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
    if isinstance(value, pd.Series):
        return float(value.iloc[-1])    # Series → 最新值
    if isinstance(value, pd.DataFrame):
        return {"error": "DataFrame 太大，请用 .iloc[-1] 或聚合函数"}
    if isinstance(value, (np.integer, np.floating)):
        return float(value)             # numpy → Python float
    if isinstance(value, (bool, np.bool_)):
        return bool(value)              # numpy bool → Python bool
    return value                        # scalar / dict / list / str
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
}
```

效果：
```python
# 没有 helper
df.close.rolling(20).mean().iloc[-1] > df.close.rolling(50).mean().iloc[-1]

# 有 helper
above(df.close.rolling(20).mean(), latest(df.close.rolling(50).mean()))

# 更简洁
crossover(df.close.rolling(20).mean(), df.close.rolling(50).mean())
```

## 可行性审查

### 审查的 4 个示例及其问题

**示例 1: 发明新指标**
```python
# 原始（有 BUG）
compute("(df.close.rolling(20).mean() / df.close.rolling(50).mean() - 1) * 100")
# → exec() 执行了计算但丢弃结果。local_ns 里没有 result。

# 修正：eval-first 策略自动捕获表达式返回值
compute("latest(df.close.rolling(20).mean() / df.close.rolling(50).mean() - 1) * 100")
```

**示例 2: 多资产分析**
```python
# 原始（需要框架支持）
compute("df_aapl.close.pct_change().corr(df_spy.close.pct_change())")
# → 需要框架遍历 engine._data_by_symbol 注入 df_aapl, df_spy

# 修正：框架自动注入，Agent 代码不变
compute("result = df_aapl.close.pct_change().corr(df_spy.close.pct_change())")
```

**示例 3: 仓位计算**
```python
# 原始（有 BUG）
compute("""
atr = df.close.diff().abs().rolling(14).mean().iloc[-1]
risk_per_trade = equity * 0.02    # ← equity 未定义！
position_size = int(risk_per_trade / (atr * 2))
""")
# → NameError: equity 不在命名空间中
# → 且 result 未设置，返回 None

# 修正：equity 作为顶层变量注入 + 显式设置 result
compute("""
result = int(equity * 0.02 / (latest(ta.atr(df.high, df.low, df.close, 14)) * 2))
""")
```

**示例 4: 市场状态识别**
```python
# 原始（有 BUG）
compute("""
returns = df.close.pct_change().dropna()
vol = returns.rolling(20).std().iloc[-1]
trend = (df.close.iloc[-1] / df.close.iloc[-50] - 1)
'trending' if abs(trend) > 0.1 and vol < 0.02 else 'ranging'
""")
# → 最后一行是表达式，exec() 丢弃结果
# → df.close.iloc[-50] 在数据不足 50 行时 IndexError

# 修正：显式 result + 安全索引
compute("""
vol = latest(df.close.pct_change().rolling(20).std())
trend = df.close.iloc[-1] / df.close.iloc[-min(50, len(df))] - 1
result = 'trending' if abs(trend) > 0.1 and vol < 0.02 else 'ranging'
""")
```

### 问题总结

```
问题                          解法                           影响
──────────────────────        ──────────────────────        ──────
exec() 丢弃表达式结果          eval-first 策略                核心架构
多资产变量未注入               遍历 _data_by_symbol 注入      数据层
account 变量不直观             展开为顶层变量                  易用性
Series 返回爆 token           _serialize() 自动降维          序列化
df 列结构不透明                Tool schema 写清楚             文档
```

## 错误处理

```python
# 错误类型 → 友好提示
SyntaxError    → {"error": "SyntaxError: ...", "remediation": "检查 Python 语法"}
NameError      → {"error": "NameError: ...", "remediation": "可用变量: df, account, cash, equity, pd, np, ta, math"}
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
Step 1  tests/features/compute.feature    Gherkin 规格（16 scenarios）
Step 2  src/agenticbt/sandbox.py          沙箱执行器（~80 行）
Step 3  src/agenticbt/tools.py            新增 compute 工具（schema + handler）
Step 4  tests/test_compute.py             step definitions（fixture: cptx）
Step 5  回归验证                           108 现有 + 16 新 scenario 全绿
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

  Scenario: 多行代码计算（exec 模式）
    When Agent 调用 compute:
      """
      sma = df.close.rolling(20).mean().iloc[-1]
      result = {'sma': sma, 'above': df.close.iloc[-1] > sma}
      """
    Then 返回包含 sma 和 above 的 dict

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

  Scenario: 多资产数据注入
    Given 加载多资产数据 "AAPL" 和 "SPY"
    And 推进到第 30 根 bar
    When Agent 调用 compute "result = df_aapl.close.corr(df_spy.close)"
    Then 返回相关系数浮点数

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
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
