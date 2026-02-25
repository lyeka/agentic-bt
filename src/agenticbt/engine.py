"""
[INPUT]: pandas.DataFrame (OHLCV), agenticbt.models (所有数据结构)
[OUTPUT]: Engine — 确定性市场模拟引擎
[POS]: 框架核心，提供数据回放/订单撮合/仓位核算/风控拦截，被 runner 驱动
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pandas as pd

from .models import (
    AccountSnapshot,
    Bar,
    CommissionConfig,
    Fill,
    MarketSnapshot,
    Order,
    Position,
    RejectedOrder,
    RiskConfig,
    SlippageConfig,
)


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

class Engine:
    """
    确定性市场模拟引擎。

    职责边界：只做数据事实，不做任何决策判断。
    订单生命周期：submit() → match_orders(next_bar) → Fill / RejectedOrder
    """

    def __init__(
        self,
        data: pd.DataFrame,
        symbol: str,
        initial_cash: float = 100_000.0,
        risk: RiskConfig | None = None,
        commission: CommissionConfig | None = None,
        slippage: SlippageConfig | None = None,
    ) -> None:
        self._data = data.reset_index()     # 保留 datetime 列
        self._symbol = symbol
        self._bar_index = -1                # advance() 后才有效

        # 账户
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._positions: dict[str, Position] = {}

        # 配置
        self._risk = risk or RiskConfig()
        self._commission = commission or CommissionConfig()
        self._slippage = slippage or SlippageConfig()

        # 订单队列与历史
        self._pending_orders: list[Order] = []
        self._fills: list[Fill] = []
        self._rejected: list[RejectedOrder] = []

        # 权益曲线：每次 advance() 后追加
        self._equity_curve: list[float] = []

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def has_next(self) -> bool:
        return self._bar_index + 1 < len(self._data)

    def advance(self) -> Bar:
        """推进到下一根 bar，返回当前 bar，并记录权益快照。"""
        self._bar_index += 1
        bar = self._current_bar()
        self._update_unrealized(bar.close)
        self._equity_curve.append(self._equity(bar.close))
        return bar

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    def market_snapshot(self) -> MarketSnapshot:
        bar = self._current_bar()
        return MarketSnapshot(
            datetime=bar.datetime,
            bar_index=self._bar_index,
            symbol=self._symbol,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

    def account_snapshot(self) -> AccountSnapshot:
        bar = self._current_bar()
        return AccountSnapshot(
            cash=self._cash,
            equity=self._equity(bar.close),
            positions=dict(self._positions),
        )

    def equity_curve(self) -> list[float]:
        return list(self._equity_curve)

    def fills(self) -> list[Fill]:
        return list(self._fills)

    # ── 订单提交 ──────────────────────────────────────────────────────────────

    def submit_buy(self, symbol: str, quantity: int) -> dict[str, Any]:
        """提交市价买单；返回 {status, order_id} 或 {status, reason}"""
        order = Order(
            symbol=symbol,
            side="buy",
            quantity=quantity,
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
        )
        return self._submit(order)

    def submit_sell(self, symbol: str, quantity: int) -> dict[str, Any]:
        """提交市价卖单"""
        order = Order(
            symbol=symbol,
            side="sell",
            quantity=quantity,
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
        )
        return self._submit(order)

    def submit_close(self, symbol: str) -> dict[str, Any]:
        """平仓：自动计算持仓数量"""
        pos = self._positions.get(symbol)
        if not pos or pos.size == 0:
            return {"status": "rejected", "reason": "无持仓可平"}
        return self.submit_sell(symbol, pos.size)

    def _submit(self, order: Order) -> dict[str, Any]:
        rejection = self._risk_check(order)
        if rejection:
            self._rejected.append(RejectedOrder(order=order, reason=rejection))
            return {"status": "rejected", "reason": rejection}
        self._pending_orders.append(order)
        return {"status": "submitted", "order_id": order.order_id}

    # ── 订单撮合 ──────────────────────────────────────────────────────────────

    def match_orders(self, bar: Bar) -> list[Fill]:
        """用给定 bar 撮合所有待执行订单（通常用下一根 bar）。"""
        fills = []
        remaining = []
        for order in self._pending_orders:
            fill = self._match_one(order, bar)
            if fill:
                fills.append(fill)
                self._apply_fill(fill)
            else:
                remaining.append(order)
        self._pending_orders = remaining
        self._fills.extend(fills)
        return fills

    def _match_one(self, order: Order, bar: Bar) -> Fill | None:
        """市价单：用 bar.open + 滑点成交"""
        price = bar.open + (self._slippage.value if order.side == "buy" else -self._slippage.value)
        price = round(price, 4)
        commission = round(price * order.quantity * self._commission.rate, 4)
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            commission=commission,
            bar_index=bar.index,
            datetime=bar.datetime,
        )

    def _apply_fill(self, fill: Fill) -> None:
        """更新持仓和现金"""
        cost = fill.price * fill.quantity + fill.commission
        if fill.side == "buy":
            self._cash -= cost
            pos = self._positions.get(fill.symbol)
            if pos and pos.size > 0:
                # 均价加权
                total_cost = pos.avg_price * pos.size + fill.price * fill.quantity
                pos.size += fill.quantity
                pos.avg_price = total_cost / pos.size
            else:
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    size=fill.quantity,
                    avg_price=fill.price,
                )
        else:  # sell
            pos = self._positions.get(fill.symbol)
            if pos:
                realized = (fill.price - pos.avg_price) * fill.quantity - fill.commission
                pos.realized_pnl += realized
                pos.size -= fill.quantity
                self._cash += fill.price * fill.quantity - fill.commission
                if pos.size == 0:
                    del self._positions[fill.symbol]

    # ── 风控 ──────────────────────────────────────────────────────────────────

    def _risk_check(self, order: Order) -> str | None:
        """返回拒绝原因字符串，或 None 表示通过"""
        if order.side != "buy":
            return None
        bar = self._current_bar()
        est_price = bar.close  # 用收盘价估算
        est_cost = est_price * order.quantity
        equity = self._equity(bar.close)
        pos = self._positions.get(order.symbol)
        current_value = pos.size * est_price if pos else 0
        new_pct = (current_value + est_cost) / equity
        if new_pct > self._risk.max_position_pct:
            return "仓位超限"
        return None

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _current_bar(self) -> Bar:
        row = self._data.iloc[self._bar_index]
        # 兼容 index 列名可能是 'date'、'Date'、'datetime' 或 DatetimeIndex
        dt = row.get("date") or row.get("Date") or row.get("datetime") or row.get("index")
        if dt is None:
            dt = self._data.index[self._bar_index]
        if isinstance(dt, str):
            dt = pd.Timestamp(dt).to_pydatetime()
        elif isinstance(dt, pd.Timestamp):
            dt = dt.to_pydatetime()
        return Bar(
            datetime=dt,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            index=self._bar_index,
        )

    def _equity(self, ref_price: float) -> float:
        pos_value = sum(p.size * ref_price for p in self._positions.values())
        return self._cash + pos_value

    def _update_unrealized(self, price: float) -> None:
        for pos in self._positions.values():
            pos.update_unrealized(price)
