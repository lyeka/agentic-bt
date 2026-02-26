"""
[INPUT]: dataclasses, datetime, typing, pandas
[OUTPUT]: Bar, Order, Fill, Position, AccountSnapshot, MarketSnapshot,
          EngineEvent, BacktestConfig, Decision, ToolCall, BacktestResult,
          RiskConfig, CommissionConfig, SlippageConfig,
          ContextConfig, Context
[POS]: 所有模块的数据结构基础层，无业务逻辑，仅数据定义
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# 市场数据层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Bar:
    """单根 K 线"""
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    index: int = 0  # 在数据集中的位置


@dataclass
class MarketSnapshot:
    """当前行情快照"""
    datetime: datetime
    bar_index: int
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# ─────────────────────────────────────────────────────────────────────────────
# 订单与成交层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Order:
    """待执行订单"""
    symbol: str
    side: str           # "buy" | "sell"
    quantity: int
    order_type: str = "market"   # "market" | "limit" | "stop"
    limit_price: float | None = None
    stop_price: float | None = None
    order_id: str = ""
    bar_index: int = 0  # 提交时的 bar index
    valid_bars: int | None = None  # None=永久有效, N=N 根 bar 后过期


@dataclass
class Fill:
    """成交记录"""
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float        # 成交价（含滑点）
    commission: float
    bar_index: int
    datetime: datetime


@dataclass
class RejectedOrder:
    """被风控拒绝的订单"""
    order: Order
    reason: str


@dataclass
class EngineEvent:
    """Engine 状态变化产生的结构化事件（单向流：Engine → Runner → Agent Context）"""
    type: str           # "fill" | "expired" | "cancelled"
    bar_index: int
    datetime: datetime
    order_id: str
    symbol: str
    detail: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 持仓与账户层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """单资产持仓"""
    symbol: str
    size: int           # 正数=多, 0=空仓
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    def market_value(self, current_price: float) -> float:
        return self.size * current_price

    def update_unrealized(self, current_price: float) -> None:
        self.unrealized_pnl = (current_price - self.avg_price) * self.size


@dataclass
class AccountSnapshot:
    """账户状态快照"""
    cash: float
    equity: float
    positions: dict[str, Position]
    total_pnl: float = 0.0
    today_pnl: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 配置层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RiskConfig:
    """风控配置"""
    max_position_pct: float = 0.20      # 单票最大仓位比例
    max_portfolio_drawdown: float = 0.15
    max_open_positions: int = 10
    max_daily_loss_pct: float = 0.03


@dataclass
class CommissionConfig:
    """手续费配置"""
    rate: float = 0.0       # 默认无手续费，由场景显式配置


@dataclass
class SlippageConfig:
    """滑点配置"""
    value: float = 0.0          # 固定滑点（价格单位，向后兼容）
    pct: float = 0.0            # 百分比滑点（0.01 = 1%）
    mode: str = "fixed"         # "fixed" | "pct"
    max_volume_pct: float = 1.0 # 单 bar 最大成交量占比（1.0 = 无约束）


@dataclass
class BacktestConfig:
    """回测配置"""
    data: "pd.DataFrame"            # OHLCV DataFrame，date 列或 DatetimeIndex
    symbol: str
    strategy_prompt: str
    model: str = "claude-sonnet-4-20250514"
    base_url: str | None = None     # None = OpenAI 默认端点
    api_key: str | None = None      # None = 读 env OPENAI_API_KEY
    initial_cash: float = 100_000.0
    risk: RiskConfig = field(default_factory=RiskConfig)
    commission: CommissionConfig = field(default_factory=CommissionConfig)
    slippage: SlippageConfig = field(default_factory=SlippageConfig)
    max_agent_rounds: int = 5       # ReAct loop 最大轮次
    decision_start_bar: int = 0     # 从该 bar index 开始触发 agent 决策
    context_config: "ContextConfig" = field(default_factory=lambda: ContextConfig())


# ─────────────────────────────────────────────────────────────────────────────
# 上下文层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContextConfig:
    """上下文组装配置 — 窗口大小和截断阈值"""
    recent_bars_window: int = 20        # 静态注入的 K 线窗口
    recent_decisions_window: int = 3
    reasoning_max_chars: int = 80


@dataclass
class Context:
    """Agent 决策的完整上下文 — 五层认知注入的结构化承载"""
    # 身份层
    playbook: str
    # 工作记忆层
    position_notes: dict[str, str]
    # 情境感知层
    datetime: datetime
    bar_index: int
    decision_count: int
    market: dict[str, Any]
    account: dict[str, Any]
    pending_orders: list[dict[str, Any]]
    # 短期记忆层
    recent_bars: list[dict[str, Any]]
    events: list[dict[str, Any]]
    recent_decisions: list[dict[str, Any]]
    # 格式化产物（由 ContextManager 填充）
    formatted_text: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Agent 决策层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """单次工具调用记录"""
    tool: str
    input: dict[str, Any]
    output: dict[str, Any]


@dataclass
class Decision:
    """Agent 单次决策完整记录"""
    # 时间标识
    datetime: datetime
    bar_index: int

    # Agent 输出
    action: str                     # "buy" | "sell" | "close" | "hold"
    symbol: str | None
    quantity: int | None
    reasoning: str

    # 决策时快照
    market_snapshot: dict[str, Any]
    account_snapshot: dict[str, Any]
    indicators_used: dict[str, Any]

    # 工具调用链
    tool_calls: list[ToolCall]

    # 执行结果（由 Engine 回填）
    order_result: dict[str, Any] | None = None

    # LLM 元信息
    model: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 评估层
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    equity_curve: list[float]


@dataclass
class ComplianceReport:
    """策略遵循度报告"""
    action_distribution: dict[str, int]     # {"buy": N, "sell": N, "hold": N}
    decisions_with_indicators: int
    total_decisions: int


@dataclass
class BacktestResult:
    """完整回测结果"""
    performance: PerformanceMetrics
    compliance: ComplianceReport
    decisions: list[Decision]
    workspace_path: str
    config: BacktestConfig | None = None
    duration: float = 0.0
    total_llm_calls: int = 0
    total_tokens: int = 0
