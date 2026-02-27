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
    EngineEvent,
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
        data: pd.DataFrame | dict[str, pd.DataFrame],
        symbol: str = "",
        initial_cash: float = 100_000.0,
        risk: RiskConfig | None = None,
        commission: CommissionConfig | None = None,
        slippage: SlippageConfig | None = None,
    ) -> None:
        # 多资产支持：dict → 各 symbol 独立 DataFrame
        if isinstance(data, dict):
            self._data_by_symbol: dict[str, pd.DataFrame] = {
                sym: df.reset_index() for sym, df in data.items()
            }
            self._symbol = symbol or next(iter(data.keys()))
            self._data = self._data_by_symbol[self._symbol]
        else:
            self._data = data.reset_index()
            self._symbol = symbol
            self._data_by_symbol = {symbol: self._data}
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
        self._trade_log: list[dict] = []   # 每笔平仓的真实盈亏记录

        # 事件队列：Engine 产生，Runner 每 bar drain 后注入 Agent context
        self._event_queue: list[EngineEvent] = []

        # 权益曲线：每次 advance() 后追加
        self._equity_curve: list[float] = []

        # 风控追踪：峰值权益（回撤）+ 日起始权益（日损）
        self._peak_equity: float = initial_cash
        self._day_start_equity: float = initial_cash
        self._current_date: str = ""

        # Bracket 状态：dormant 子单注册表 {parent_id: (stop_id, tp_id)}
        self._bracket_map: dict[str, tuple[str, str]] = {}
        self._dormant_orders: list[Order] = []
        self._sibling_map: dict[str, str] = {}          # {child_id: sibling_id}
        self._bracket_cancelled: set[str] = set()       # 本轮 OCO 取消集合

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def has_next(self) -> bool:
        return self._bar_index + 1 < len(self._data)

    def advance(self) -> Bar:
        """推进到下一根 bar，更新权益快照、峰值权益、日起始权益。"""
        self._bar_index += 1
        bar = self._current_bar()
        self._update_unrealized()
        equity = self._equity()
        self._equity_curve.append(equity)

        # 更新峰值（用于回撤计算）
        if equity > self._peak_equity:
            self._peak_equity = equity

        # 换日检测（用于单日亏损计算）
        date_str = bar.datetime.strftime("%Y-%m-%d")
        if date_str != self._current_date:
            self._current_date = date_str
            self._day_start_equity = equity

        return bar

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    def market_snapshot(self, symbol: str | None = None) -> MarketSnapshot:
        bar = self._current_bar(symbol)
        sym = symbol or self._symbol
        return MarketSnapshot(
            datetime=bar.datetime,
            bar_index=self._bar_index,
            symbol=sym,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

    def account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            cash=self._cash,
            equity=self._equity(),
            positions=dict(self._positions),
        )

    def equity_curve(self) -> list[float]:
        return list(self._equity_curve)

    def fills(self) -> list[Fill]:
        return list(self._fills)

    def trade_log(self) -> list[dict]:
        """每笔已平仓交易的真实盈亏记录，供 Evaluator 消费"""
        return list(self._trade_log)

    def drain_events(self) -> list[EngineEvent]:
        """排空并返回所有待处理事件（Runner 每 bar 调用一次）"""
        events = list(self._event_queue)
        self._event_queue.clear()
        return events

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """取消指定挂单；返回 {status, order_id} 或 {status, reason}"""
        for i, order in enumerate(self._pending_orders):
            if order.order_id == order_id:
                self._pending_orders.pop(i)
                bar = self._current_bar()
                self._emit("cancelled", order, bar)
                return {"status": "cancelled", "order_id": order_id}
        return {"status": "error", "reason": f"未找到订单: {order_id}"}

    def pending_orders(self) -> list[dict[str, Any]]:
        """返回所有待执行挂单的摘要"""
        return [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side,
                "quantity": o.quantity,
                "order_type": o.order_type,
                "limit_price": o.limit_price,
                "stop_price": o.stop_price,
                "bar_index": o.bar_index,
            }
            for o in self._pending_orders
        ]

    def recent_bars(self, n: int = 5, symbol: str | None = None) -> list[dict[str, Any]]:
        """最近 N 根 K 线完整 OHLCV（含当前 bar），供 Context 静态注入"""
        sym = symbol or self._symbol
        data = self._data_by_symbol.get(sym, self._data)
        start = max(0, self._bar_index - n + 1)
        return [
            {
                "bar_index": i,
                "open": float(data.iloc[i]["open"]),
                "high": float(data.iloc[i]["high"]),
                "low": float(data.iloc[i]["low"]),
                "close": float(data.iloc[i]["close"]),
                "volume": float(data.iloc[i]["volume"]),
            }
            for i in range(start, self._bar_index + 1)
        ]

    def market_history(self, n: int, symbol: str | None = None) -> list[dict[str, Any]]:
        """返回最近 N 根 K 线的完整 OHLCV，供 Agent 动态查询"""
        sym = symbol or self._symbol
        data = self._data_by_symbol.get(sym, self._data)
        start = max(0, self._bar_index - n + 1)
        result = []
        for i in range(start, self._bar_index + 1):
            row = data.iloc[i]
            dt = row.get("date") or row.get("Date") or row.get("datetime") or row.get("index")
            if dt is None:
                dt = data.index[i]
            result.append({
                "bar_index": i,
                "datetime": str(dt),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
        return result

    # ── 订单提交 ──────────────────────────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_price: float | None = None,
        valid_bars: int | None = None,
    ) -> dict[str, Any]:
        """通用订单提交入口（供 Tools 层调用）"""
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
            valid_bars=valid_bars,
        )
        return self._submit(order)

    def submit_buy(self, symbol: str, quantity: int) -> dict[str, Any]:
        """提交市价买单；返回 {status, order_id} 或 {status, reason}"""
        return self.submit_order(symbol, "buy", quantity)

    def submit_bracket(
        self,
        symbol: str,
        side: str,
        quantity: int,
        stop_loss: float,
        take_profit: float,
    ) -> dict[str, Any]:
        """
        提交 Bracket 订单：主单（市价）+ 止损子单 + 止盈子单。
        主单成交后子单自动激活；子单任一成交则 OCO 取消另一个。
        """
        # 主单先过风控
        parent = Order(
            symbol=symbol, side=side, quantity=quantity,
            order_type="market",
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
        )
        rejection = self._risk_check(parent)
        if rejection:
            self._rejected.append(RejectedOrder(order=parent, reason=rejection))
            return {"status": "rejected", "reason": rejection}

        # 子单方向与主单相反（主买→子卖，主卖→子买）
        child_side = "sell" if side == "buy" else "buy"
        stop_order = Order(
            symbol=symbol, side=child_side, quantity=quantity,
            order_type="stop", stop_price=stop_loss,
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
        )
        tp_order = Order(
            symbol=symbol, side=child_side, quantity=quantity,
            order_type="limit", limit_price=take_profit,
            order_id=str(uuid.uuid4())[:8],
            bar_index=self._bar_index,
        )

        self._pending_orders.append(parent)
        self._dormant_orders.extend([stop_order, tp_order])
        self._bracket_map[parent.order_id] = (stop_order.order_id, tp_order.order_id)
        return {"status": "submitted", "order_id": parent.order_id}

    def submit_sell(self, symbol: str, quantity: int) -> dict[str, Any]:
        """提交市价卖单"""
        return self.submit_order(symbol, "sell", quantity)

    def submit_close(self, symbol: str) -> dict[str, Any]:
        """平仓：自动计算持仓方向和数量"""
        pos = self._positions.get(symbol)
        if not pos or pos.size == 0:
            return {"status": "rejected", "reason": "无持仓可平"}
        # 多头 → 卖出平仓；空头 → 买入平仓
        if pos.size > 0:
            return self.submit_sell(symbol, pos.size)
        else:
            return self.submit_buy(symbol, abs(pos.size))

    def _submit(self, order: Order) -> dict[str, Any]:
        rejection = self._risk_check(order)
        if rejection:
            self._rejected.append(RejectedOrder(order=order, reason=rejection))
            result: dict[str, Any] = {"status": "rejected", "reason": rejection}
            # 仓位超限时，计算允许的最大数量，帮助 Agent 一次修正
            if rejection == "仓位超限":
                equity = self._equity()
                est_price = self._current_bar(order.symbol).close
                pos = self._positions.get(order.symbol)
                current_value = pos.size * est_price if pos else 0
                max_value = equity * self._risk.max_position_pct - current_value
                result["max_allowed_qty"] = max(0, int(max_value / est_price))
            return result
        self._pending_orders.append(order)
        return {"status": "submitted", "order_id": order.order_id}

    # ── 订单撮合 ──────────────────────────────────────────────────────────────

    def match_orders(self, bar: Bar) -> list[Fill]:
        """用给定 bar 撮合所有待执行订单（通常用下一根 bar）。"""
        fills = []
        remaining = []
        snapshot = list(self._pending_orders)
        self._pending_orders = []  # 清空，让 bracket 激活可直接追加

        for order in snapshot:
            # 多资产：每个订单用自身 symbol 的 bar 撮合；bar_index 统一不受影响
            order_bar = self._current_bar(order.symbol)
            # 过期检查：bar 差值超过 valid_bars 则过期
            if order.valid_bars is not None and (bar.index - order.bar_index) > order.valid_bars:
                self._emit("expired", order, bar)
                continue
            fill = self._match_one(order, order_bar)
            if fill:
                fills.append(fill)
                self._apply_fill(fill)
                self._emit("fill", order, bar,
                           price=fill.price, quantity=fill.quantity, side=fill.side)
                # 部分成交：剩余数量重新入队（保留原始订单属性）
                remaining_qty = order.quantity - fill.quantity
                if remaining_qty > 0:
                    self._pending_orders.append(Order(
                        symbol=order.symbol, side=order.side, quantity=remaining_qty,
                        order_type=order.order_type, limit_price=order.limit_price,
                        stop_price=order.stop_price, order_id=order.order_id,
                        bar_index=order.bar_index, valid_bars=order.valid_bars,
                    ))
            else:
                remaining.append(order)

        # 过滤掉本轮被 OCO 取消的订单，再合并新激活的子单
        remaining = [o for o in remaining if o.order_id not in self._bracket_cancelled]
        self._bracket_cancelled.clear()
        self._pending_orders = remaining + self._pending_orders
        self._fills.extend(fills)
        return fills

    def _match_one(self, order: Order, bar: Bar) -> Fill | None:
        """按订单类型路由到对应撮合逻辑，并应用成交量约束"""
        if order.order_type == "market":
            fill = self._match_market(order, bar)
        elif order.order_type == "limit":
            fill = self._match_limit(order, bar)
        elif order.order_type == "stop":
            fill = self._match_stop(order, bar)
        else:
            return None
        if fill is None:
            return None
        # 成交量约束：按比例限制单 bar 最大成交量
        max_qty = int(bar.volume * self._slippage.max_volume_pct)
        if max_qty > 0 and fill.quantity > max_qty:
            fill = self._create_fill(order, bar, fill.price, quantity=max_qty)
        return fill

    def _match_market(self, order: Order, bar: Bar) -> Fill:
        """市价单：bar.open + 滑点（固定或百分比）"""
        base = bar.open
        slip = base * self._slippage.pct if self._slippage.mode == "pct" else self._slippage.value
        price = base + (slip if order.side == "buy" else -slip)
        return self._create_fill(order, bar, round(price, 4))

    def _match_limit(self, order: Order, bar: Bar) -> Fill | None:
        """限价单：买入 bar.low ≤ limit / 卖出 bar.high ≥ limit"""
        limit = order.limit_price
        if order.side == "buy" and bar.low <= limit:
            return self._create_fill(order, bar, limit)
        if order.side == "sell" and bar.high >= limit:
            return self._create_fill(order, bar, limit)
        return None

    def _match_stop(self, order: Order, bar: Bar) -> Fill | None:
        """止损单：卖出 bar.low ≤ stop / 买入 bar.high ≥ stop"""
        stop = order.stop_price
        if order.side == "sell" and bar.low <= stop:
            return self._create_fill(order, bar, stop)
        if order.side == "buy" and bar.high >= stop:
            return self._create_fill(order, bar, stop)
        return None

    def _create_fill(self, order: Order, bar: Bar, price: float, quantity: int | None = None) -> Fill:
        """统一 Fill 构造，消除三路分支的重复；quantity 为 None 时使用订单全量"""
        qty = quantity if quantity is not None else order.quantity
        commission = round(price * qty * self._commission.rate, 4)
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            commission=commission,
            bar_index=bar.index,
            datetime=bar.datetime,
        )

    def _apply_fill(self, fill: Fill) -> None:
        """更新持仓和现金，统一处理多空方向；并处理 Bracket 联动"""
        delta = fill.quantity if fill.side == "buy" else -fill.quantity
        pos = self._positions.get(fill.symbol)
        current_size = pos.size if pos else 0
        new_size = current_size + delta

        if current_size == 0 or (current_size > 0) == (delta > 0):
            # 同方向加仓 or 新开仓：加权均价
            if pos is None:
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol, size=new_size, avg_price=fill.price,
                )
            else:
                total_cost = pos.avg_price * abs(current_size) + fill.price * fill.quantity
                pos.size = new_size
                pos.avg_price = total_cost / abs(new_size)
            # 现金：多头开仓支出，空头开仓收入保证金收款
            if fill.side == "buy":
                self._cash -= fill.price * fill.quantity + fill.commission
            else:
                self._cash += fill.price * fill.quantity - fill.commission
        else:
            # 反向减仓 or 平仓：计算已实现盈亏
            assert pos is not None
            if pos.size > 0:
                # 多头 sell → realized = (sell - buy_avg) * qty
                realized = (fill.price - pos.avg_price) * fill.quantity - fill.commission
                self._cash += fill.price * fill.quantity - fill.commission
            else:
                # 空头 buy back → realized = (open_avg - buy_back) * qty
                realized = (pos.avg_price - fill.price) * fill.quantity - fill.commission
                self._cash -= fill.price * fill.quantity + fill.commission

            pos.realized_pnl += realized
            pos.size = new_size
            self._trade_log.append({
                "symbol": fill.symbol,
                "quantity": fill.quantity,
                "buy_price": round(pos.avg_price, 4),
                "sell_price": fill.price,
                "pnl": round(realized, 4),
                "commission": fill.commission,
                "datetime": fill.datetime,
                "bar_index": fill.bar_index,
            })
            if pos.size == 0:
                del self._positions[fill.symbol]

        self._handle_bracket_fill(fill)

    def _handle_bracket_fill(self, fill: Fill) -> None:
        """Bracket 联动：主单成交→激活子单；子单成交→OCO 标记取消同级"""
        # 主单成交 → 将 dormant 子单移入 pending，注册同级映射
        if fill.order_id in self._bracket_map:
            stop_id, tp_id = self._bracket_map.pop(fill.order_id)
            activated = [o for o in self._dormant_orders if o.order_id in (stop_id, tp_id)]
            self._dormant_orders = [o for o in self._dormant_orders
                                    if o.order_id not in (stop_id, tp_id)]
            self._pending_orders.extend(activated)
            self._sibling_map[stop_id] = tp_id
            self._sibling_map[tp_id] = stop_id
            return

        # 子单成交 → 标记同级为 OCO 取消（在 match_orders 末尾过滤）
        if fill.order_id in self._sibling_map:
            sibling_id = self._sibling_map.pop(fill.order_id)
            self._sibling_map.pop(sibling_id, None)
            self._bracket_cancelled.add(sibling_id)

    # ── 风控 ──────────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, order: Order, bar: Bar, **detail: Any) -> None:
        """发射引擎事件到队列"""
        self._event_queue.append(EngineEvent(
            type=event_type,
            bar_index=bar.index,
            datetime=bar.datetime,
            order_id=order.order_id,
            symbol=order.symbol,
            detail=dict(detail),
        ))

    def _risk_check(self, order: Order) -> str | None:
        """返回拒绝原因字符串，或 None 表示通过；只拦截 buy（开仓）方向"""
        if order.side != "buy":
            return None
        equity = self._equity()

        # 检查1: 单票仓位上限（用订单 symbol 的当前价格估算）
        est_price = self._current_bar(order.symbol).close
        pos = self._positions.get(order.symbol)
        current_value = pos.size * est_price if pos else 0
        if (current_value + est_price * order.quantity) / equity > self._risk.max_position_pct:
            return "仓位超限"

        # 检查2: 最大持仓品种数（新开仓才检查）
        if order.symbol not in self._positions and len(self._positions) >= self._risk.max_open_positions:
            return "持仓数量超限"

        # 检查3: 组合最大回撤
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity
            if drawdown > self._risk.max_portfolio_drawdown:
                return "组合回撤超限"

        # 检查4: 单日最大亏损
        if self._day_start_equity > 0:
            daily_loss = (self._day_start_equity - equity) / self._day_start_equity
            if daily_loss > self._risk.max_daily_loss_pct:
                return "单日亏损超限"

        return None

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _current_bar(self, symbol: str | None = None) -> Bar:
        sym = symbol or self._symbol
        data = self._data_by_symbol.get(sym, self._data)
        row = data.iloc[self._bar_index]
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

    def _equity(self) -> float:
        pos_value = sum(
            pos.size * self._current_bar(sym).close
            for sym, pos in self._positions.items()
        )
        return self._cash + pos_value

    def _update_unrealized(self) -> None:
        for sym, pos in self._positions.items():
            pos.update_unrealized(self._current_bar(sym).close)
