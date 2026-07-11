"""
[INPUT]: uuid, datetime, athenaclaw.trading.*
[OUTPUT]: TradeOrchestrator
[POS]: 交易边界层的核心编排对象；负责账户/订单读取与单步下单/撤单执行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from time import sleep
from uuid import uuid4

from athenaclaw.tools.market.schema import normalize_symbol
from athenaclaw.trading.errors import TradeError, TradeErrorCode
from athenaclaw.trading.policy import RiskAction, RiskContext, RiskGuard
from athenaclaw.trading.protocol import TradeBrokerAdapter
from athenaclaw.trading.store import TradeAuditLog
from athenaclaw.trading.types import (
    SubmitLimitOrderIntent,
    TradeAccountSnapshot,
    TradeAccountSummary,
    TradeApplyResult,
    TradeOpenOrder,
    TradeOrderSnapshot,
    TradeReceipt,
    decode_account_ref,
    decode_order_ref,
)


_TERMINAL_STATUSES = {"filled", "cancelled", "rejected", "expired"}


class TradeOrchestrator:
    def __init__(
        self,
        *,
        adapter: TradeBrokerAdapter,
        guard: RiskGuard,
        audit_log: TradeAuditLog,
        cancel_confirm_delays: tuple[float, ...] = (0.2, 0.5, 1.0),
    ) -> None:
        self._adapter = adapter
        self._guard = guard
        self._audit_log = audit_log
        self._cancel_confirm_delays = cancel_confirm_delays

    def list_accounts(self):
        return self._adapter.list_accounts()

    def get_positions(self, account_ref: str) -> TradeAccountSnapshot:
        self._require_account_ref(account_ref)
        positions = tuple(self._adapter.get_positions(account_ref))
        summary = self.get_summary(account_ref)
        parts = self._account_parts(account_ref)
        return TradeAccountSnapshot(
            account_ref=account_ref,
            broker=parts["broker"],
            account_id=parts["account_id"],
            env=parts["env"],
            positions=positions,
            cash=summary.cash if summary else 0.0,
            equity=summary.equity if summary else 0.0,
            updated_at=(summary.updated_at if summary else _utc_now_iso()),
        )

    def get_summary(self, account_ref: str) -> TradeAccountSummary | None:
        self._require_account_ref(account_ref)
        if not self._adapter.capabilities().supports_account_summary:
            return None
        return self._adapter.get_account_summary(account_ref)

    def get_open_orders(self, account_ref: str) -> list[TradeOpenOrder]:
        self._require_account_ref(account_ref)
        return self._adapter.get_open_orders(account_ref)

    def get_order_status(self, order_ref: str) -> TradeOrderSnapshot:
        self._require_order_ref(order_ref)
        return self._adapter.get_order_status(order_ref)

    def execute_limit(
        self,
        *,
        account_ref: str,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: float,
        automation: bool = False,
    ) -> TradeApplyResult:
        """校验 + 预检规整 + 风控裁决 + 下单，一步到底。

        自主操作员不再有「plan 给人看，apply 再执行」的中间站——这里就是
        唯一的执行入口，guard.evaluate 是唯一的安全边界。
        """
        self._require_account_ref(account_ref)
        requested_limit_price = self._validate_price(limit_price)
        intent = SubmitLimitOrderIntent(
            account_ref=account_ref,
            symbol=normalize_symbol(symbol),
            side=self._normalize_side(side),
            quantity=self._validate_quantity(quantity),
            limit_price=requested_limit_price,
        )
        caps = self._adapter.capabilities()
        if "limit" not in caps.supported_order_types:
            raise TradeError(TradeErrorCode.UNSUPPORTED_ORDER_TYPE, "当前 broker 不支持限价单")

        preview = self._adapter.preview_limit_order(intent) if caps.supports_preview_limit_order else None
        normalized_limit_price = preview.normalized_limit_price if preview and preview.normalized_limit_price is not None else intent.limit_price
        normalized_intent = SubmitLimitOrderIntent(
            account_ref=intent.account_ref,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            limit_price=normalized_limit_price,
        )
        warnings = list(preview.warnings if preview else ())
        if abs(normalized_intent.limit_price - intent.limit_price) > 1e-9:
            reason = preview.normalization_reason if preview else None
            suffix = f" ({reason})" if reason else ""
            warnings.insert(
                0,
                f"limit_price normalized from {_format_price(intent.limit_price)} to {_format_price(normalized_intent.limit_price)}{suffix}",
            )

        env = self._account_parts(account_ref)["env"]
        ctx = RiskContext(operation="submit_limit", env=env, automation=automation, intent=normalized_intent.to_dict())
        decision = self._guard.evaluate(ctx)
        self._audit_log.append({"event": "trade.guard.decision", "context": ctx.to_dict(), "decision": decision.to_dict()})
        if decision.action is not RiskAction.ALLOW:
            raise TradeError(TradeErrorCode.PERMISSION_DENIED, decision.reason or "交易未授权")

        receipt = self._adapter.submit_limit_order(normalized_intent)
        order_status = self._adapter.get_order_status(receipt.order_ref)
        account_snapshot = None
        if order_status.status in {"partially_filled", "filled"}:
            account_snapshot = self.get_positions(normalized_intent.account_ref)
        result = TradeApplyResult(
            plan_id=f"exec-{uuid4().hex}",
            operation="submit_limit",
            result_summary=_submit_result_summary(normalized_intent, order_status),
            receipt=receipt,
            order_status=order_status,
            account_snapshot=account_snapshot,
            finalized=order_status.status in _TERMINAL_STATUSES,
            warnings=tuple(warnings),
        )
        self._audit_log.append({"event": "trade.executed", "result": result.to_dict(), "guard": decision.to_dict()})
        return result

    def execute_cancel(self, *, order_ref: str, automation: bool = False) -> TradeApplyResult:
        self._require_order_ref(order_ref)
        order = self.get_order_status(order_ref)
        if order.status in _TERMINAL_STATUSES:
            raise TradeError(
                TradeErrorCode.ORDER_NOT_CANCELLABLE,
                f"订单当前状态不可撤销: {order.status}",
                details={"order_ref": order_ref, "status": order.status},
            )

        env = decode_order_ref(order_ref)["env"]
        ctx = RiskContext(operation="cancel", env=env, automation=automation, intent={"order_ref": order_ref})
        decision = self._guard.evaluate(ctx)
        self._audit_log.append({"event": "trade.guard.decision", "context": ctx.to_dict(), "decision": decision.to_dict()})
        if decision.action is not RiskAction.ALLOW:
            raise TradeError(TradeErrorCode.PERMISSION_DENIED, decision.reason or "交易未授权")

        receipt = self._adapter.cancel_order(order_ref)
        order_status = self._confirm_order_status(order_ref)
        finalized = order_status.status in _TERMINAL_STATUSES
        warnings = ("cancel_requested_not_finalized",) if not finalized else ()
        result = TradeApplyResult(
            plan_id=f"exec-{uuid4().hex}",
            operation="cancel",
            result_summary=_cancel_result_summary(order_status, finalized=finalized),
            receipt=receipt,
            order_status=order_status,
            account_snapshot=None,
            finalized=finalized,
            warnings=warnings,
        )
        self._audit_log.append({"event": "trade.executed", "result": result.to_dict(), "guard": decision.to_dict()})
        return result

    def _adapter_capabilities(self):
        return self._adapter.capabilities()

    @staticmethod
    def _normalize_side(side: str) -> str:
        value = str(side or "").strip().lower()
        if value not in {"buy", "sell"}:
            raise TradeError(TradeErrorCode.INVALID_SIDE, f"side 必须是 buy 或 sell，收到: {side!r}")
        return value

    @staticmethod
    def _validate_quantity(quantity: float) -> float:
        value = float(quantity)
        if value <= 0:
            raise TradeError(TradeErrorCode.INVALID_QUANTITY, "quantity 必须大于 0")
        return value

    @staticmethod
    def _validate_price(price: float) -> float:
        try:
            value = Decimal(str(price))
        except (InvalidOperation, ValueError) as exc:
            raise TradeError(TradeErrorCode.INVALID_PRICE, "limit_price 必须是合法数字") from exc
        if value <= 0:
            raise TradeError(TradeErrorCode.INVALID_PRICE, "limit_price 必须大于 0")
        return float(value)

    def _confirm_order_status(self, order_ref: str) -> TradeOrderSnapshot:
        latest = self._adapter.get_order_status(order_ref)
        if latest.status in _TERMINAL_STATUSES:
            return latest
        for delay in self._cancel_confirm_delays:
            if delay > 0:
                sleep(delay)
            latest = self._adapter.get_order_status(order_ref)
            if latest.status in _TERMINAL_STATUSES:
                return latest
        return latest

    @staticmethod
    def _require_account_ref(account_ref: str) -> None:
        try:
            decode_account_ref(account_ref)
        except Exception as exc:  # pragma: no cover - thin validation wrapper
            raise TradeError(TradeErrorCode.INVALID_ACCOUNT_REF, "account_ref 非法") from exc

    @staticmethod
    def _require_order_ref(order_ref: str) -> None:
        try:
            decode_order_ref(order_ref)
        except Exception as exc:  # pragma: no cover - thin validation wrapper
            raise TradeError(TradeErrorCode.INVALID_ORDER_REF, "order_ref 非法") from exc

    @staticmethod
    def _account_parts(account_ref: str) -> dict[str, str]:
        try:
            return decode_account_ref(account_ref)
        except Exception as exc:  # pragma: no cover - validated by _require_account_ref
            raise TradeError(TradeErrorCode.INVALID_ACCOUNT_REF, "account_ref 非法") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _submit_result_summary(intent: SubmitLimitOrderIntent, order: TradeOrderSnapshot) -> str:
    return (
        f"已提交 {intent.side.upper()} {intent.quantity:g} {intent.symbol} "
        f"限价 {_format_price(intent.limit_price)}，当前状态 {order.status}"
    )


def _cancel_result_summary(order: TradeOrderSnapshot, *, finalized: bool) -> str:
    if finalized:
        return f"订单当前状态 {order.status}"
    return f"撤单请求已发送，当前状态仍为 {order.status}，待券商确认"


def _format_price(price: float) -> str:
    text = f"{float(price):.4f}".rstrip("0").rstrip(".")
    return text or "0"
