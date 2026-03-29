# Agent Tools — 当前工具协议

> 本文档描述 `src/agent/tools/` 中真实存在、会直接暴露给 LLM 的工具语义。
> 重点是让读者和 Agent 都能正确理解 `market_ohlcv` 与 `compute` 的配合方式。

## 工具总览

当前 Kernel 内置这些工具：

| 工具 | 作用 |
|------|------|
| `market_ohlcv` | 获取 OHLCV，写入 DataStore，供 `compute` 消费 |
| `portfolio` | 维护结构化当前持仓快照 `portfolio.json` |
| `watchlist` | 维护结构化自选列表快照 `watchlist.json` |
| `trade_account` | 读取远端 broker 账户、持仓、未完成订单、订单状态 |
| `trade_plan` | 生成交易执行计划，不直接产生外部副作用 |
| `trade_apply` | 执行 `trade_plan` 生成的计划 |
| `compute` | 在沙箱中对已加载 OHLCV 做 Python 分析 |
| `read` | 读工作区文件 |
| `write` | 写工作区文件 |
| `edit` | 精确文本替换 |
| `bash` | 执行 shell 命令（按权限控制） |
| `web_search` / `web_fetch` | 可选 Web 搜索与抓取 |

其中最容易用错的是 `portfolio`、`watchlist`、`trade_account`、`trade_plan`、`trade_apply`、`market_ohlcv` 和 `compute`。

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

注意：

- `portfolio` 不是远端 broker 账户
- 使用交易工具执行远端下单/撤单后，不会自动改写 `portfolio.json`
- 如果用户明确要把工作区快照同步到远端 broker 结果，应通过后续专门同步动作完成，而不是在 V1 自动覆盖

## watchlist

### 核心语义

`watchlist` 维护的是**当前有效的自选列表快照**，不是持仓，不是研究日志，也不是价格提醒引擎。

适合的输入：

- 用户说“把某个 symbol 加到自选 / 从自选删除”
- 用户直接给出当前完整自选列表
- 用户希望围绕某个观察理由持续跟踪标的

不适合的输入：

- 当前持仓
- 长篇研究过程
- 止盈止损/价格提醒规则
- symbol 识别不清的内容

### action

- `get`: 读取全部列表或某个列表
- `upsert`: 更新某个列表
- `remove_items`: 从列表中删除若干 symbol
- `delete_list`: 删除整个列表

`upsert` 的关键参数是 `items_mode`：

- `replace`: 本次给出的 `items` 就是该列表当前完整快照
- `merge`: 只更新提到的 symbol，未提到的不动

### 条目字段

- `symbol`: 当前观察的标的
- `name`: 可选显示名，便于人和 UI 阅读；不参与身份识别
- `watch_reason`: 当前这轮观察的核心问题；后续分析和自动化巡检会围绕它展开
- `added_at`: 本轮观察开始时间；用于复盘“加入自选后走势”

`name` 和 `watch_reason` 的更新协议：

- 省略：保留旧值
- 传非空字符串：更新
- 传 `null`：清空
- 传空字符串：报错

### 为什么不用 memory.md

`memory.md` 适合记录高层关注方向和长期偏好。
具体自选 symbol 清单、观察理由和加入时间需要结构化读取，因此单独维护在 `watchlist.json`。

## trade_account / trade_plan / trade_apply

### 核心语义

这三者共同组成远端 broker 交易闭环：

- `trade_account`：读取远端账户状态
- `trade_plan`：创建可确认、可审计的执行计划
- `trade_apply`：执行计划

它们不是 `portfolio` 的替代物，也不会自动维护 `portfolio.json`。

### V1 边界

只支持：

- 股票/ETF
- `LIMIT`
- `BUY`
- `SELL`
- `CANCEL`

不支持：

- `MARKET`
- `STOP`
- `AUCTION`
- 条件单
- 期权/期货/融资融券/卖空

### 正确用法

1. 先 `trade_account.list_accounts`
2. 再 `trade_plan.submit_limit` 或 `trade_plan.cancel`
3. 最后 `trade_apply`

不能跳过 `trade_plan` 直接执行。

显式参数规则：

- `trade_account.get_positions/get_summary/get_open_orders` 必须显式传 `account_ref`
- `trade_account.get_order_status` 必须显式传 `order_ref`
- `trade_plan.submit_limit` 必须显式传 `account_ref`
- `trade_plan.cancel` 必须显式传 `order_ref`
- 不会自动承接最近账户、最近订单，也不会返回 suggestion

### 账户发现

`trade_account.list_accounts` 不只返回 `account_ref`。V1 里它还会返回：

- `supported_markets`
- `account_status`
- `account_kind`
- `is_simulated`
- `extra`

其中：

- 公共字段用于跨 broker 选户
- `extra` 用于解释 provider 特有的限制或能力

对 Futu 来说，`extra` 至少会包含类似 `sim_acc_type`、`trdmarket_auth`、`acc_status`、`acc_role` 这类原生账户信息。

当要交易某个 symbol 时，先用这些字段判断账户是否支持目标市场、是否 active、以及是否是合适的账户类型。

### 活动账户快照

`trade_account.get_positions` 成功后，会把该账户快照写入 `Kernel.data["account"]`。  
后续 `compute` 读取到的 `account/cash/equity/positions` 就来自这个当前活动账户快照。

### 计划与执行返回

`trade_plan.submit_limit` 返回的 plan 除了 `plan_id` 外，还会返回：

- `normalized_intent`

其中 `normalized_intent.limit_price` 是后续 `trade_apply` 唯一允许执行的价格。  
如果 provider 对输入价格做了规范化，plan 的 `warnings` 里会明确写出原始价格和规范化后的价格。

`trade_apply` 返回除了 `order_status` 外，还会返回：

- `finalized`
- `warnings`

语义是：

- `status=ok` 只表示工具执行成功
- `finalized=true` 才表示该次交易动作已确认进入终态
- 撤单后如果短时确认不到终态，会返回 `finalized=false`，并在 `warnings` 中给出 `cancel_requested_not_finalized`

### 缺参错误

缺少 ref 时，不再返回 `invalid_*`，而是：

- 缺少 `account_ref`：`missing_account_ref`
- 缺少 `order_ref`：`missing_order_ref`

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

- `symbol`: 标的代码。支持美股、港股和 A 股。A 股内部统一归一化为 `.SH/.SZ/.BJ`，`yfinance` 出站时会把 `.SH` 转成 `.SS`
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
- 当前 provider 可为 `tushare | yfinance | finnhub | futu`
- `futu` 这一版默认使用**不复权**口径，不暴露 `autype/session/extended_time` 公共参数
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
