"""
[INPUT]: agenticbt.engine, agenticbt.memory, agenticbt.models (ContextConfig, Context, EngineEvent)
[OUTPUT]: ContextManager — 组装并格式化 Agent 决策所需的完整上下文
[POS]: Runner 和 Agent 的桥接层；assemble() 生产 Context 对象，格式化文本由此产出
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
                    sym: {"size": p.size, "avg_price": p.avg_price}
                    for sym, p in acc.positions.items()
                },
            },
            pending_orders=pending_orders,
            recent_bars=recent_bars,
            events=events,
            recent_decisions=recent_decisions,
        )
        ctx.formatted_text = self._format_text(ctx)
        return ctx

    # ── 格式化 ────────────────────────────────────────────────────────────────

    def _format_text(self, ctx: Context) -> str:
        m = ctx.market
        a = ctx.account
        positions = ", ".join(
            f"{sym} {p['size']}股@{p['avg_price']:.2f}"
            for sym, p in a["positions"].items()
        ) or "空仓"

        lines = [
            f"## 当前行情  [{ctx.datetime}  bar={ctx.bar_index}]",
            f"  {m['symbol']}  开={m['open']}  高={m['high']}  低={m['low']}"
            f"  收={m['close']}  量={m['volume']:.0f}",
            f"## 账户",
            f"  现金={a['cash']:.0f}  净值={a['equity']:.0f}  持仓: {positions}",
        ]

        # 近期 K 线走势（条件注入）
        if ctx.recent_bars:
            closes = "  ".join(f"{b['close']:.2f}" for b in ctx.recent_bars)
            lines.append(f"## 近期走势（最近 {len(ctx.recent_bars)} 根收盘价）")
            lines.append(f"  {closes}")

        # 挂单（条件注入：无挂单则不渲染）
        if ctx.pending_orders:
            lines.append("## 挂单")
            for o in ctx.pending_orders:
                price_info = ""
                if o.get("limit_price") is not None:
                    price_info = f" limit={o['limit_price']}"
                elif o.get("stop_price") is not None:
                    price_info = f" stop={o['stop_price']}"
                lines.append(
                    f"  [{o['order_id']}] {o['order_type']} {o['side']} "
                    f"{o['symbol']} {o['quantity']}股{price_info}"
                )

        # 本轮事件（条件注入）
        if ctx.events:
            lines.append("## 本轮事件")
            for e in ctx.events:
                lines.append(f"  {self._format_event(e)}")

        # 持仓备注（按 symbol 逐行）
        if ctx.position_notes:
            lines.append("## 持仓备注")
            for sym, note in ctx.position_notes.items():
                lines.append(f"  {sym}: {note}")

        # 近期决策（条件注入：无历史则不渲染）
        if ctx.recent_decisions:
            lines.append("## 近期决策")
            for d in ctx.recent_decisions:
                lines.append(f"  [{d['bar_index']}] {d['action']}: {d['reasoning']}")

        lines.append(
            f"\n以上行情与账户数据已是最新快照，无需重复获取。\n"
            f"compute 工具中 df 已包含 {ctx.bar_index + 1} 行完整 OHLCV 数据，可直接用 df.close 等访问分析。\n"
            f"请使用可用工具分析后给出交易决策。"
        )
        return "\n".join(lines)

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
