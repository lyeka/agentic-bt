# Core Tools — 核心工具设计

> Agent 通过工具与 Framework 交互。
> 5 个核心工具组，每个职责单一，接口简洁。

## 工具总览

```
Core Tools (框架内置，不可替换):

  market       感知行情
  indicator    计算指标
  account      感知持仓
  trade        执行操作
  memory       记录和回忆

Extension Tools (MCP/Skills，可选):
  新闻情感 · 宏观数据 · 另类数据 · 自定义分析 · ...
```

## market — 感知行情

Agent 通过此工具观察市场状态。

### observe

获取当前 bar 的行情快照。

```
输入: 无 (或指定 symbol)
输出:
{
  "datetime": "2024-03-15",
  "bars": {
    "AAPL": {
      "open": 172.5,
      "high": 174.2,
      "low": 171.8,
      "close": 173.9,
      "volume": 45200000
    }
  }
}
```

### history

获取指定资产的历史 K 线。

```
输入: symbol: str, bars: int
输出: 最近 N 根 bar 的 OHLCV 数据列表
```

## indicator — 计算指标

Agent 通过此工具获取技术指标值。指标计算是框架核心能力。

### calc

计算指定技术指标。

```
输入: name: str, symbol: str, **params
输出: 指标当前值及相关数据

示例:
  indicator.calc("RSI", symbol="AAPL", period=14)
  → {"value": 28.5, "prev": 31.2}

  indicator.calc("MACD", symbol="AAPL", fast=12, slow=26, signal=9)
  → {"macd": 0.35, "signal": 0.12, "histogram": 0.23}

  indicator.calc("BollingerBands", symbol="AAPL", period=20, std=2)
  → {"upper": 178.2, "middle": 174.5, "lower": 170.8}
```

### list

列出所有可用的技术指标。

```
输入: 无
输出: 指标名称列表及分类
```

### describe

获取指定指标的参数说明。

```
输入: name: str
输出:
{
  "name": "RSI",
  "description": "Relative Strength Index, 0-100 range",
  "params": {
    "period": {"type": "int", "default": 14, "range": [2, 200]}
  }
}
```

## account — 感知持仓

Agent 通过此工具了解自身的资金和持仓状态。

### status

获取当前账户完整状态。

```
输入: 无
输出:
{
  "cash": 85000,
  "equity": 102300,
  "positions": {
    "AAPL": {
      "size": 100,
      "avg_price": 170.5,
      "current_price": 173.9,
      "unrealized_pnl": 340,
      "weight_pct": 17.0
    },
    "GOOGL": {
      "size": 50,
      "avg_price": 142.0,
      "current_price": 141.4,
      "unrealized_pnl": -120,
      "weight_pct": 6.9
    }
  },
  "pending_orders": [...],
  "today_pnl": 220,
  "total_pnl": 2300,
  "max_drawdown": 0.08
}
```

## trade — 执行操作

Agent 通过此工具提交交易指令。所有指令先经 Risk Guard 检查。

### execute

提交一个交易动作。

```
输入:
  action: "buy" | "sell" | "close"
  symbol: str
  quantity: int       (close 时可省略)
  order_type: "market" | "limit" | "stop"  (默认 "market")
  price: float        (limit/stop 时必填)

示例:
  trade.execute(action="buy", symbol="AAPL", quantity=100)
  trade.execute(action="buy", symbol="AAPL", quantity=100,
                order_type="limit", price=171.0)
  trade.execute(action="sell", symbol="AAPL", quantity=50)
  trade.execute(action="close", symbol="AAPL")

输出:
  成功: {"status": "submitted", "order_id": "..."}
  被风控拒绝: {"status": "rejected", "reason": "仓位超限: 23% > 20%"}
```

## memory — 记录和回忆

Agent 通过此工具管理交易记忆。本质是文件读写，但 Agent 不接触文件路径。

详细设计见 [memory.md](memory.md)。

### log

往当日日志追加一条记录。

```
输入: content: str
效果: 追加到 journal/{current_date}.md

示例:
  memory.log("观察到 AAPL 连续 3 天缩量下跌, RSI 逼近 30")
  memory.log("买入 AAPL 100 股, 理由: RSI 超卖 + 放量企稳")
```

### note

创建或更新一个主题笔记。

```
输入: key: str, content: str
效果: 写入/覆盖 notes/{key}.md

示例:
  memory.note("position_AAPL", "持仓 100 股 @172.5, 止损 168.0")
  memory.note("market_regime", "当前震荡市, ADX=18, 布林带收窄")
```

### recall

搜索相关记忆。

```
输入: query: str
输出: 相关记忆片段列表

示例:
  memory.recall("上次 RSI 超卖时买 AAPL 的结果")
  → [
      { "source": "journal/2024-02-20.md",
        "content": "买入 AAPL 因 RSI=25, 最终止损出局 -1.8%" },
      { "source": "notes/position_AAPL.md",
        "content": "已平仓... RSI 超卖 + 放量组合有效" },
    ]
```

## 扩展工具 (Extension Tools)

框架不内置，通过 MCP Server 或 Skills 机制接入。

```
MCP Server 示例:

  news-sentiment
    ├── get_news(symbol, date)
    └── get_sentiment(symbol, date)

  macro-data
    ├── get_fed_rate()
    └── get_vix()

  alternative-data
    └── get_social_sentiment(symbol)
```

Agent 自主决定调用哪些扩展工具。框架不限制也不干预。

## 工具设计原则

1. **职责单一** — 每个工具组只做一件事
2. **接口简洁** — 参数少，语义明确，LLM 容易正确调用
3. **输出结构化** — JSON 格式，LLM 容易解析和推理
4. **错误信息丰富** — 失败时返回清晰原因，Agent 可据此调整
5. **不越界** — 核心工具不替代 Agent 做决策

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
