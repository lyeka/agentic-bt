# Agent Tools — 当前工具协议

> 本文档描述 `src/agent/tools/` 中真实存在、会直接暴露给 LLM 的工具语义。
> 重点是让读者和 Agent 都能正确理解 `market_ohlcv` 与 `compute` 的配合方式。

## 工具总览

当前 Kernel 内置这些工具：

| 工具 | 作用 |
|------|------|
| `market_ohlcv` | 获取 OHLCV，写入 DataStore，供 `compute` 消费 |
| `portfolio` | 维护结构化当前持仓快照 `portfolio.json` |
| `compute` | 在沙箱中对已加载 OHLCV 做 Python 分析 |
| `read` | 读工作区文件 |
| `write` | 写工作区文件 |
| `edit` | 精确文本替换 |
| `bash` | 执行 shell 命令（按权限控制） |
| `web_search` / `web_fetch` | 可选 Web 搜索与抓取 |

其中最容易用错的是 `portfolio`、`market_ohlcv` 和 `compute`。

## portfolio

### 核心语义

`portfolio` 维护的是**当前持仓快照**，不是交易流水，不是券商账本。

适合的输入：

- 用户发完整持仓截图
- 用户直接给出某账户当前持仓
- 用户明确说某笔已执行交易后，当前仓位已经变了

不适合的输入：

- 计划、假设、watchlist
- 不完整截图
- 账户或 symbol 识别不清的内容

### action

- `get`: 读取全部账户或某个账户的当前快照
- `upsert`: 更新账户快照
- `delete_account`: 删除误建账户

`upsert` 的关键参数是 `positions_mode`：

- `replace`: 本次给出的 `positions` 就是账户最新完整持仓
- `merge`: 只更新提到的 symbol，未提到的不动；`quantity=0` 表示删除该持仓

### 为什么不用 memory.md

`memory.md` 适合长期偏好、风险边界、关注方向。
详细持仓需要结构化读取和 UI 展示，因此单独维护在 `portfolio.json`。

## market_ohlcv

### 请求协议

```json
{
  "symbol": "600519.SH",
  "interval": "1m",
  "mode": "history",
  "start": "2026-03-12 09:30:00",
  "end": "2026-03-12 10:30:00",
  "include_data_in_result": false
}
```

字段语义：

- `symbol`: 标的代码。A 股内部统一归一化为 `.SH/.SZ/.BJ`，`yfinance` 出站时会把 `.SH` 转成 `.SS`
- `interval`: bar 粒度，只能是 `1d | 1m | 5m | 15m | 30m | 60m`
- `mode`:
  - `history`: 返回一段 OHLCV
  - `latest`: 返回最新可用的一根分钟 bar
- `start/end`: 仅 `history` 支持
- `include_data_in_result`:
  - `true`: 返回完整 `data`
  - `false`: 只把数据注入 DataStore，返回 `data=[]`

### 默认行为

- `interval="1d", mode="history"` 且不传 `start/end`：最近 1 年日线
- 分钟 `history` 且不传 `start/end`：当日盘中；休市时返回最近一个交易日
- `latest` 必须显式指定分钟 `interval`

### 关键规则

- `mode="latest"` 不是“交易所实时流”，而是“数据源当前最新可用的一根 bar”
- `mode="latest"` 禁止传 `start/end`
- `interval="1d"` 禁止配 `mode="latest"`
- 日线 `start/end` 用 `YYYY-MM-DD`
- 分钟 `start/end` 用 `YYYY-MM-DD HH:MM:SS`
- `include_data_in_result` 只控制返回 JSON 是否带 `data`，不影响 fetch、DataStore 注入和后续 `compute`

### 返回结构

```json
{
  "symbol": "600519.SH",
  "normalized_symbol": "600519.SH",
  "source": "yfinance",
  "interval": "1m",
  "mode": "latest",
  "timezone": "Asia/Shanghai",
  "as_of": "2026-03-12 10:13:00",
  "effective_start": "2026-03-12 10:13:00",
  "effective_end": "2026-03-12 10:13:00",
  "warning": "Yahoo Finance intraday data may be delayed for this market.",
  "total_rows": 1,
  "data_in_result": false,
  "data": []
}
```

当 `include_data_in_result=true` 时，`data` 会恢复为完整 OHLCV 列表：

```json
{
  "total_rows": 1,
  "data_in_result": true,
  "data": [
    {
      "date": "2026-03-12 10:13:00",
      "open": 65.12,
      "high": 65.18,
      "low": 65.08,
      "close": 65.10,
      "volume": 6041339
    }
  ]
}
```

注意：`data=[]` 且 `total_rows>0` 表示“数据已抓取并写入 DataStore，但当前轮没有回显 OHLCV 明细”，不是“没有抓到数据”。

### DataStore 语义

每次调用 `market_ohlcv` 都会把 DataFrame 写入多个 key：

- 精确窗口 key：`ohlcv:{symbol}:{interval}:{mode}:{start_token}:{end_token}`
- 选择器 key：`ohlcv:{symbol}:{interval}:{mode}`
- symbol 别名：`ohlcv:{symbol}`
- 全局别名：`_default_ohlcv`

这让同一 symbol 的日线、分钟线、latest 可以并存，不会互相覆盖。
即使 `include_data_in_result=false`，这些 key 也会照常写入。

## compute

### 核心语义

`compute` 不会自己拉行情。它只消费已经由 `market_ohlcv` 注入 DataStore 的 DataFrame。

可用变量：

- `df`
- `open/high/low/close/volume/date`
- `account/cash/equity/positions`
- `pd/np/ta/math`
- `latest/prev/crossover/crossunder/above/below/bbands/macd/tail/nz`

### 选择器协议

`compute` 支持和 `market_ohlcv` 相同的 selector：

```json
{
  "code": "latest(close)",
  "symbol": "600519.SH",
  "interval": "1m",
  "mode": "latest"
}
```

查找优先级：

1. 如果传了 `symbol + interval + mode + start/end`：`symbol` 精确窗口 key → `symbol + interval + mode` → `symbol`
2. 如果传了 `symbol + interval + mode`：`symbol + interval + mode` → `symbol`
3. 如果只传了 `symbol`：`symbol`
4. 如果没有 `symbol`，只传了 `interval/mode`：`_default_ohlcv:{interval}:{mode}` → `_default_ohlcv`
5. 如果什么都没传：`_default_ohlcv`

### 重要约束

- `market_ohlcv` 返回 JSON 里的 `data` 不会自动注入 `compute`
- 即使 `market_ohlcv(..., include_data_in_result=false)`，`compute` 仍然可以直接使用对应 `df`
- 如果你加载了多个数据集，后续 `compute` 必须复用同一组 selector
- 一旦显式提供 `symbol`，`compute` 不会跨 symbol 回退
- 分钟数据的 `date` 带时分秒
- 要最新值请用 `latest(close)` 或 `close.iloc[-1]`，不要写 `close[-1]`

### 正确用法

```text
1. market_ohlcv(symbol="600519.SH", interval="1d", mode="history",
                include_data_in_result=false)
2. compute(code="latest(ta.rsi(close, 14))", symbol="600519.SH", interval="1d", mode="history")
```

```text
1. market_ohlcv(symbol="600519.SH", interval="1m", mode="latest",
                include_data_in_result=true)
2. compute(code="{'last_close': latest(close), 'last_time': str(latest(date))}",
           symbol="600519.SH", interval="1m", mode="latest")
```

### 常见误区

- 把 `latest` 理解成“绝对实时”
- 把 `include_data_in_result=false` 理解成“不会进 compute”
- 先拉了 `1d/history`，再拉 `1m/latest`，随后 `compute` 只传 `symbol`，结果拿错数据帧
- 试图在 `compute` 里直接使用 `market_ohlcv` 的 JSON 结果

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
