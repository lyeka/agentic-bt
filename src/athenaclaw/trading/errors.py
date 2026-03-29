"""
[INPUT]: enum, typing
[OUTPUT]: TradeErrorCode, TradeError, error_payload
[POS]: 交易域统一错误语义
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class TradeErrorCode(str, Enum):
    BROKER_NOT_CONFIGURED = "broker_not_configured"
    BROKER_DISCONNECTED = "broker_disconnected"
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_MARKET_UNSUPPORTED = "account_market_unsupported"
    ACCOUNT_INACTIVE = "account_inactive"
    MISSING_ACCOUNT_REF = "missing_account_ref"
    MISSING_ORDER_REF = "missing_order_ref"
    ORDER_NOT_FOUND = "order_not_found"
    ORDER_NOT_CANCELLABLE = "order_not_cancellable"
    PLAN_NOT_FOUND = "plan_not_found"
    PLAN_EXPIRED = "plan_expired"
    PLAN_ALREADY_APPLIED = "plan_already_applied"
    INVALID_ACCOUNT_REF = "invalid_account_ref"
    INVALID_ORDER_REF = "invalid_order_ref"
    INVALID_SIDE = "invalid_side"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_PRICE = "invalid_price"
    UNSUPPORTED_ORDER_TYPE = "unsupported_order_type"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    TRADE_LOCKED = "trade_locked"
    PERMISSION_DENIED = "permission_denied"
    PREVIEW_REJECTED = "preview_rejected"
    PROVIDER_ERROR = "provider_error"


class TradeError(Exception):
    def __init__(
        self,
        code: TradeErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def error_payload(exc: TradeError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": exc.message,
        "error_code": exc.code.value,
    }
    if exc.details:
        payload["details"] = exc.details
    return payload
