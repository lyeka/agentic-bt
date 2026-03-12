# Compute — 沙箱化分析终端

> `compute` 是 Agent 的分析终端，不是指标菜单。
> 它消费已经由 `market_ohlcv` 注入的数据帧，在沙箱里执行 Python。

## Schema

```json
{
  "code": "latest(close)",
  "symbol": "600519.SH",
  "interval": "1m",
  "mode": "latest",
  "start": "2026-03-12 09:30:00",
  "end": "2026-03-12 10:30:00"
}
```

字段说明：

- `code`: 必填 Python 代码
- `symbol/interval/mode/start/end`: 可选 selector，用来选择 DataStore 中哪一份 OHLCV

`compute` 不会请求行情。没有匹配数据时会返回错误，提示先用相同 selector 调 `market_ohlcv`。

## 执行环境

预加载变量：

- `df`: OHLCV DataFrame
- `open/high/low/close/volume/date`: 对应列的 Series
- `account/cash/equity/positions`
- `pd/np/ta/math`

预置 helper：

- `latest(series)`
- `prev(series, n=1)`
- `crossover(fast, slow)`
- `crossunder(fast, slow)`
- `above(series, value)`
- `below(series, value)`
- `bbands(close, length, std)`
- `macd(close)`
- `tail(x, n=20)`
- `nz(x, default=0.0)`

返回规则：

- 单表达式直接返回
- 多行代码默认返回最后表达式
- 显式写 `result = ...` 也可以

## Selector 规则

### 为什么必须带 selector

现在同一 symbol 的这些数据可以同时存在：

- `600519.SH` 的 `1d/history`
- `600519.SH` 的 `1m/history`
- `600519.SH` 的 `1m/latest`

因此：

- 如果会话里只抓过一份 OHLCV，`compute(code="...")` 通常够用
- 如果会话里抓过多份数据，`compute` 必须复用同一组 selector，否则可能拿到错误的数据帧
- 一旦显式给了 `symbol`，`compute` 不会回退到别的 symbol

### 查找优先级

1. 如果传了 `symbol + interval + mode + start + end`：`symbol` 精确窗口 key → `symbol + interval + mode` → `symbol`
2. 如果传了 `symbol + interval + mode`：`symbol + interval + mode` → `symbol`
3. 如果只传了 `symbol`：`symbol`
4. 如果没有 `symbol`，只传了 `interval/mode`：`_default_ohlcv:{interval}:{mode}` → `_default_ohlcv`
5. 如果什么都没传：`_default_ohlcv`

### 推荐模式

日线分析：

```text
market_ohlcv(symbol="AAPL", interval="1d", mode="history")
compute(code="latest(ta.rsi(close, 14))", symbol="AAPL", interval="1d", mode="history")
```

盘中最新 bar：

```text
market_ohlcv(symbol="600519.SH", interval="1m", mode="latest")
compute(code="{'close': latest(close), 'time': str(latest(date))}",
        symbol="600519.SH", interval="1m", mode="latest")
```

指定分钟窗口：

```text
market_ohlcv(symbol="600519.SH", interval="1m", mode="history",
             start="2026-03-12 09:30:00", end="2026-03-12 10:30:00")
compute(code="len(df)", symbol="600519.SH", interval="1m", mode="history",
        start="2026-03-12 09:30:00", end="2026-03-12 10:30:00")
```

## Agent 常见错误

### 错误 1：把 `market_ohlcv` 的 JSON 当成 `compute` 输入

错误心智：

```text
先拿到 market_ohlcv 的 data 数组，再在 compute 里访问 data
```

正确心智：

```text
market_ohlcv 只是把 DataFrame 注入后台
compute 直接使用 df/open/high/low/close/volume/date
```

### 错误 2：拉了多份数据却不带 selector

错误：

```text
1. market_ohlcv(... interval="1d", mode="history")
2. market_ohlcv(... interval="1m", mode="latest")
3. compute(code="latest(close)", symbol="600519.SH")
```

这一步很可能拿到最新抓取的 `1m/latest`，而不是日线。

正确：

```text
compute(code="latest(close)", symbol="600519.SH", interval="1d", mode="history")
```

### 错误 3：分钟数据把 `date` 当成纯日期

分钟和 latest 数据的 `date` 带时分秒。要做盘中判断时，直接用：

```python
str(latest(date))
```

## 安全边界

- 无网络
- 无文件 I/O
- 不允许 `import`
- 每次调用独立命名空间
- DataFrame 是副本，不会回写原始市场数据
- 超时和序列化由沙箱统一兜底

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
