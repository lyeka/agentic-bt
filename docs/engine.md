# Engine — 确定性市场模拟引擎

> Engine 是不可侵犯的确定性层。它模拟市场，不做任何决策。
> 像 CPU 执行指令——精确、可重复、不理解意图。

## 职责边界

```
Engine 的职责:
  ├── 数据回放    按时间序列推进 bar
  ├── 指标计算    内置标准指标库，按需计算
  ├── 订单撮合    确定性价格匹配
  ├── 仓位核算    持仓、均价、盈亏、保证金
  ├── 权益跟踪    现金、净值、权益曲线
  └── 风控拦截    硬约束检查（Agent 不可绕过）

Engine 不做的事:
  ✗ 不做交易决策（交给 Agent）
  ✗ 不分析结果（交给 Eval）
  ✗ 不管理记忆（交给 Memory）
  ✗ 不组装上下文（交给 Context Manager）
```

## 数据回放

### 数据模型

采用列式存储，每个资产一张表：

```
columns: datetime | open | high | low | close | volume
```

MVP 阶段使用 Pandas DataFrame，后续可升级为 Polars。

### 时间推进

```python
class Engine:
    def load(self, data_config: DataConfig) -> None:
        """加载市场数据"""

    def has_next(self) -> bool:
        """是否还有下一根 bar"""

    def advance(self) -> Bar:
        """推进到下一根 bar，返回当前 bar 数据"""

    def current_datetime(self) -> datetime:
        """当前模拟时间"""
```

### 多资产支持

多个资产共享同一时间轴。Engine 按 datetime 对齐所有资产数据。
某资产在某个 bar 无数据时，该资产状态保持不变（不前瞻）。

## 指标计算

### 设计原则

- 框架核心能力，不是扩展
- Agent 通过 `indicator` 工具调用，不直接操作计算逻辑
- MVP 阶段每次调用实时计算，不做缓存优化

### 内置标准指标库

```
趋势类:    SMA, EMA, WMA, DEMA, TEMA
动量类:    RSI, MACD, Stochastic, ROC, CCI, Williams%R
波动类:    BollingerBands, ATR, StdDev, KeltnerChannel
成交量类:  OBV, VWAP, MFI, CMF
综合类:    ADX, Ichimoku, ParabolicSAR, Pivot
```

### 指标接口

```python
class IndicatorEngine:
    def calc(self, name: str, symbol: str, **params) -> IndicatorResult:
        """计算指定指标，返回当前值及必要的历史值"""

    def list(self) -> list[IndicatorInfo]:
        """列出所有可用指标"""

    def describe(self, name: str) -> IndicatorSchema:
        """返回指标的参数说明"""
```

### 自定义指标注册

```python
@indicator_registry.register("MyFactor")
def my_factor(close: Series, volume: Series, period: int = 20) -> Series:
    return close.rolling(period).mean() / volume.rolling(period).mean()
```

## 订单撮合

### 订单类型

MVP 支持：

| 类型 | 语义 |
|------|------|
| market | 下一根 bar 开盘价成交 |
| limit | 价格触及限价时成交 |
| stop | 价格触及止损价后变为 market 单 |

### 撮合规则

```
Market 订单:
  成交价 = 下一根 bar 的 open + 滑点
  滑点 = 可配置 (固定值 / 百分比)

Limit 订单:
  if 买入 limit: 当 bar.low <= limit_price → 成交价 = limit_price
  if 卖出 limit: 当 bar.high >= limit_price → 成交价 = limit_price

Stop 订单:
  if 买入 stop: 当 bar.high >= stop_price → 转为 market 单
  if 卖出 stop: 当 bar.low <= stop_price → 转为 market 单
```

### 手续费模型

```python
commission_config = {
    "type": "percentage",  # percentage | fixed | tiered
    "rate": 0.001,         # 0.1%
}
```

### 滑点模型

```python
slippage_config = {
    "type": "fixed",       # fixed | percentage
    "value": 0.01,         # 固定滑点
}
```

## 仓位管理

### Position 数据结构

```python
@dataclass
class Position:
    symbol: str
    size: int              # 正数=多头, 负数=空头, 0=无持仓
    avg_price: float       # 持仓均价
    unrealized_pnl: float  # 浮动盈亏
    realized_pnl: float    # 已实现盈亏
```

### Portfolio 数据结构

```python
@dataclass
class Portfolio:
    cash: float                        # 可用现金
    positions: dict[str, Position]     # 各资产持仓
    equity: float                      # 总权益 = cash + 所有持仓市值
    total_pnl: float                   # 总盈亏
```

## 风控拦截器 (Risk Guard)

### 设计原则

- 风控是**事中拦截**，不是事后统计
- Agent 的每个交易动作在执行前都通过 Risk Guard 检查
- 拒绝时返回结构化原因，Agent 可据此调整

### 声明式配置

```python
risk_config = {
    "max_position_pct": 0.20,       # 单票不超过总资金 20%
    "max_portfolio_drawdown": 0.15, # 组合回撤超 15% 暂停交易
    "max_open_positions": 10,       # 最多同时持有 10 只
    "max_daily_loss_pct": 0.03,     # 单日亏损不超过 3%
}
```

### 检查流程

```
Agent trade.execute(buy AAPL 200 shares)
    │
    ▼
Risk Guard:
    ├── 仓位检查: 200 shares * price / equity > 20%? → REJECT
    ├── 持仓数检查: open_positions >= 10? → REJECT
    ├── 回撤检查: current_drawdown > 15%? → REJECT
    ├── 日损检查: today_loss > 3%? → REJECT
    └── 全部通过 → ACCEPT
    │
    ▼
REJECT → 返回 { passed: false, reason: "仓位超限: 23% > 20% 上限" }
         Agent 收到拒绝信息，可以调整数量后重试
ACCEPT → Engine 提交订单
```

## Engine 对外接口

```python
class Engine:
    # --- 生命周期 ---
    def load(self, data_config: DataConfig) -> None
    def has_next(self) -> bool
    def advance(self) -> Bar

    # --- 状态查询 (供 Tools 使用) ---
    def market_state(self) -> MarketState
    def account_state(self) -> AccountState

    # --- 指标计算 (供 indicator tool 使用) ---
    def calc_indicator(self, name: str, symbol: str, **params) -> IndicatorResult
    def list_indicators(self) -> list[IndicatorInfo]

    # --- 订单管理 ---
    def submit(self, order: Order) -> OrderResult
    def cancel(self, order_id: str) -> bool
    def match_orders(self, bar: Bar) -> list[FillEvent]

    # --- 风控 ---
    def risk_check(self, action: TradeAction) -> RiskCheckResult

    # --- 分析数据 ---
    def equity_curve(self) -> Series
    def trade_log(self) -> list[Trade]
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
