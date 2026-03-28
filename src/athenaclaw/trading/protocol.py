"""
[INPUT]: typing.Protocol, athenaclaw.trading.types
[OUTPUT]: TradeBrokerAdapter
[POS]: 交易 broker 抽象协议
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Protocol

from athenaclaw.trading.types import (
    SubmitLimitOrderIntent,
    TradeAccountDescriptor,
    TradeAccountSummary,
    TradeCapabilities,
    TradeOpenOrder,
    TradeOrderSnapshot,
    TradePosition,
    TradePreview,
    TradeReceipt,
)


class TradeBrokerAdapter(Protocol):
    name: str

    def capabilities(self) -> TradeCapabilities: ...

    def list_accounts(self) -> list[TradeAccountDescriptor]: ...

    def get_positions(self, account_ref: str) -> list[TradePosition]: ...

    def get_open_orders(self, account_ref: str) -> list[TradeOpenOrder]: ...

    def get_order_status(self, order_ref: str) -> TradeOrderSnapshot: ...

    def submit_limit_order(self, intent: SubmitLimitOrderIntent) -> TradeReceipt: ...

    def cancel_order(self, order_ref: str) -> TradeReceipt: ...

    def get_account_summary(self, account_ref: str) -> TradeAccountSummary | None: ...

    def preview_limit_order(self, intent: SubmitLimitOrderIntent) -> TradePreview | None: ...
