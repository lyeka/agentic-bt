"""
[INPUT]: agenticbt.engine, agenticbt.memory, agenticbt.models (ContextConfig, Context, EngineEvent)
[OUTPUT]: ContextManager — 组装并格式化 Agent 决策所需的完整上下文（XML 结构化输出 + 持仓盈亏注入）
[POS]: Runner 和 Agent 的桥接层；assemble() 生产 Context 对象，_format_text() 输出 XML 结构化文本
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Context, ContextConfig

if TYPE_CHECKING:
    from .engine import Engine
    from .memory import Memory


# ─────────────────────────────────────────────────────────────────────────────
# ContextManager
# ─────────────────────────────────────────────────────────────────────────────

class ContextManager:
    """
    组装 Agent 决策所需的五层认知上下文，并格式化为 LLM 友好文本。

    静态注入：情境感知（当前 bar）+ 短期记忆（近 N bar + 近期决策）+ 工作记忆（挂单）
    动态获取：长期记忆（由 Agent 调 memory_recall）
    """

    def __init__(self, config: ContextConfig | None = None) -> None:
        self._cfg = config or ContextConfig()

    def assemble(
        self,
        engine: Engine,
        memory: Memory,
        bar_index: int,
        events: list[dict[str, Any]],
        decisions: list[Any] | None = None,
    ) -> Context:
        """组装完整 Context 并填充 formatted_text"""
        snap = engine.market_snapshot()
        acc = engine.account_snapshot()
        playbook = memory.read_playbook()
        position_notes = memory.read_position_notes(list(acc.positions.keys()))

        recent_bars = engine.recent_bars(self._cfg.recent_bars_window)
        pending_orders = engine.pending_orders()

        # 近期决策摘要（最近 N 条）
        all_decisions = decisions or []
        recent_decisions = [
            self._summarize_decision(d)
            for d in all_decisions[-self._cfg.recent_decisions_window:]
        ]

        risk = engine.risk_summary()

        ctx = Context(
            playbook=playbook,
            position_notes=position_notes,
            datetime=snap.datetime,
            bar_index=bar_index,
            decision_count=len(all_decisions),
            market={
                "symbol": snap.symbol,
                "open": snap.open,
                "high": snap.high,
                "low": snap.low,
                "close": snap.close,
                "volume": snap.volume,
            },
            account={
                "cash": acc.cash,
                "equity": acc.equity,
                "positions": {
                    sym: {
                        "size": p.size,
                        "avg_price": p.avg_price,
                        "unrealized_pnl": (engine.current_price(sym) - p.avg_price) * p.size,
                    }
                    for sym, p in acc.positions.items()
                },
            },
            risk_summary=risk,
            pending_orders=pending_orders,
            recent_bars=recent_bars,
            events=events,
            recent_decisions=recent_decisions,
        )
        ctx.formatted_text = self._format_text(ctx)
        return ctx

    # ── 格式化 ────────────────────────────────────────────────────────────────

    def _format_text(self, ctx: Context) -> str:
        """XML 结构化输出 — 数据在前，指令在后"""
        m = ctx.market
        a = ctx.account
        positions = ", ".join(
            f"{sym} {p['size']}股@{p['avg_price']:.2f} | 未实现{p['unrealized_pnl']:+.0f}"
            for sym, p in a["positions"].items()
        ) or "空仓"

        parts = [
            f'<market datetime="{ctx.datetime}" bar="{ctx.bar_index}" symbol="{m["symbol"]}">',
            f'开={m["open"]}  高={m["high"]}  低={m["low"]}  收={m["close"]}  量={m["volume"]:.0f}',
            '</market>',
            '',
            f'<account cash="{a["cash"]:.0f}" equity="{a["equity"]:.0f}">',
            f'{positions}',
            '</account>',
        ]

        # 风控约束（条件注入：空仓且有买入空间时渲染）
        rs = ctx.risk_summary
        if rs and rs.get("max_buy_qty", 0) > 0 and not a["positions"]:
            pct = rs["max_position_pct"]
            parts += [
                '',
                f'<risk max_position_pct="{pct:.0%}" max_buy_qty="{rs["max_buy_qty"]}" '
                f'positions="{rs["open_positions"]}/{rs["max_open_positions"]}">',
                f'{m["symbol"]} 可买≈{rs["max_buy_qty"]}股',
                '</risk>',
            ]

        # 近期 K 线走势（完整 OHLCV 表格）
        if ctx.recent_bars:
            parts += [
                '',
                f'<recent_bars count="{len(ctx.recent_bars)}">',
                '  bar  开盘    最高    最低    收盘    成交量',
            ]
            for b in ctx.recent_bars:
                parts.append(
                    f"  {b['bar_index']:>3}  {b['open']:.2f}  {b['high']:.2f}  "
                    f"{b['low']:.2f}  {b['close']:.2f}  {b['volume']:.0f}"
                )
            parts.append('</recent_bars>')

        # 本轮事件（条件注入）
        if ctx.events:
            parts.append('')
            parts.append('<events>')
            for e in ctx.events:
                parts.append(self._format_event(e))
            parts.append('</events>')

        # 挂单（条件注入：无挂单则不渲染）
        if ctx.pending_orders:
            parts.append('')
            parts.append('<pending_orders>')
            for o in ctx.pending_orders:
                price_info = ""
                if o.get("limit_price") is not None:
                    price_info = f" limit={o['limit_price']}"
                elif o.get("stop_price") is not None:
                    price_info = f" stop={o['stop_price']}"
                parts.append(
                    f"[{o['order_id']}] {o['order_type']} {o['side']} "
                    f"{o['symbol']} {o['quantity']}股{price_info}"
                )
            parts.append('</pending_orders>')

        # 持仓备注（按 symbol 逐行）
        if ctx.position_notes:
            parts.append('')
            parts.append('<position_notes>')
            for sym, note in ctx.position_notes.items():
                parts.append(f"{sym}: {note}")
            parts.append('</position_notes>')

        # 近期决策（条件注入：无历史则不渲染）
        if ctx.recent_decisions:
            parts.append('')
            parts.append('<recent_decisions>')
            for d in ctx.recent_decisions:
                parts.append(f"[{d['bar_index']}] {d['action']}: {d['reasoning']}")
            parts.append('</recent_decisions>')

        # 任务指令（始终在最后）
        parts += [
            '',
            '<task>',
            '分析当前市场状态，根据你的策略做出交易决策。',
            f'compute 工具中 df 已包含 {ctx.bar_index + 1} 行完整 OHLCV 数据。',
            '</task>',
        ]

        return "\n".join(parts)

    def _format_event(self, e: dict[str, Any]) -> str:
        """按事件类型格式化，防止 fill/expired/cancelled 字段缺失报错"""
        etype = e.get("type", "unknown")
        if etype == "fill":
            return (
                f"成交: {e.get('side', '?')} {e.get('symbol', '?')} "
                f"{e.get('quantity', '?')}股 @ {e.get('price', 0):.2f}"
            )
        if etype == "expired":
            return f"过期: 订单 {e.get('order_id', '?')} ({e.get('symbol', '?')}) 已过期"
        if etype == "cancelled":
            return f"取消: 订单 {e.get('order_id', '?')} ({e.get('symbol', '?')}) 已取消"
        return f"{etype}: {e.get('order_id', '?')}"

    def _summarize_decision(self, decision: Any) -> dict[str, Any]:
        """提取决策摘要，reasoning 截断到 max_chars"""
        reasoning = getattr(decision, "reasoning", "") or ""
        if len(reasoning) > self._cfg.reasoning_max_chars:
            reasoning = reasoning[: self._cfg.reasoning_max_chars] + "…"
        return {
            "bar_index": getattr(decision, "bar_index", 0),
            "action": getattr(decision, "action", "hold"),
            "reasoning": reasoning,
        }
