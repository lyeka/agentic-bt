"""
[INPUT]: athenaclaw.trading.types
[OUTPUT]: build_kernel_account
[POS]: 交易账户快照到 compute 账户变量的映射
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Any

from athenaclaw.trading.types import TradeAccountSnapshot


def build_kernel_account(snapshot: TradeAccountSnapshot) -> dict[str, Any]:
    positions: dict[str, Any] = {}
    for item in snapshot.positions:
        positions[item.symbol] = {
            "quantity": item.quantity,
            "avg_cost": item.avg_cost,
            "currency": item.currency,
            "can_sell_qty": item.can_sell_qty,
            "market_value": item.market_value,
        }
    return {
        "account_ref": snapshot.account_ref,
        "broker": snapshot.broker,
        "account_id": snapshot.account_id,
        "env": snapshot.env,
        "cash": snapshot.cash,
        "equity": snapshot.equity,
        "positions": positions,
        "updated_at": snapshot.updated_at,
    }
