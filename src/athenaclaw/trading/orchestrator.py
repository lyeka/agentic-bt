"""
[INPUT]: uuid, datetime, athenaclaw.trading.*
[OUTPUT]: TradeOrchestrator
[POS]: 交易边界层的核心编排对象；负责 plan/apply/状态回读
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from athenaclaw.tools.market.schema import normalize_symbol
from athenaclaw.trading.errors import TradeError, TradeErrorCode
from athenaclaw.trading.protocol import TradeBrokerAdapter
from athenaclaw.trading.store import TradeAuditLog, TradePlanStore
from athenaclaw.trading.types import (
    SubmitLimitOrderIntent,
    TradeAccountSnapshot,
    TradeAccountSummary,
    TradeApplyResult,
    TradeOpenOrder,
    TradeOrderSnapshot,
    TradePlan,
    TradePreview,
    TradeReceipt,
)


_TERMINAL_STATUSES = {"filled", "cancelled", "rejected", "expired"}


class TradeOrchestrator:
    def __init__(
        self,
        *,
        adapter: TradeBrokerAdapter,
        plan_store: TradePlanStore,
        audit_log: TradeAuditLog,
        plan_ttl_sec: int = 120,
    ) -> None:
        self._adapter = adapter
        self._plan_store = plan_store
        self._audit_log = audit_log
        self._plan_ttl_sec = plan_ttl_sec

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

    def plan_submit_limit(
        self,
        *,
        account_ref: str,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: float,
    ) -> TradePlan:
        self._require_account_ref(account_ref)
        intent = SubmitLimitOrderIntent(
            account_ref=account_ref,
            symbol=normalize_symbol(symbol),
            side=self._normalize_side(side),
            quantity=self._validate_quantity(quantity),
            limit_price=self._validate_price(limit_price),
        )
        caps = self._adapter.capabilities()
        if "limit" not in caps.supported_order_types:
            raise TradeError(TradeErrorCode.UNSUPPORTED_ORDER_TYPE, "当前 broker 不支持限价单")

        preview = self._adapter.preview_limit_order(intent) if caps.supports_preview_limit_order else None
        warnings = tuple(preview.warnings if preview else ())
        created_at = _utc_now_iso()
        expires_at = _utc_expiry(self._plan_ttl_sec)
        plan = TradePlan(
            plan_id=f"plan-{uuid4().hex}",
            operation="submit_limit",
            plan_summary=_submit_plan_summary(intent),
            confirm_text=_submit_confirm_text(intent),
            warnings=warnings,
            created_at=created_at,
            expires_at=expires_at,
        )
        self._plan_store.save(plan, payload={"intent": intent.to_dict(), "preview": _preview_payload(preview)})
        self._audit_log.append({"event": "trade.plan.created", "plan": plan.to_dict()})
        return plan

    def plan_cancel(self, *, order_ref: str) -> TradePlan:
        self._require_order_ref(order_ref)
        order = self.get_order_status(order_ref)
        if order.status in _TERMINAL_STATUSES:
            raise TradeError(
                TradeErrorCode.ORDER_NOT_CANCELLABLE,
                f"订单当前状态不可撤销: {order.status}",
                details={"order_ref": order_ref, "status": order.status},
            )
        created_at = _utc_now_iso()
        plan = TradePlan(
            plan_id=f"plan-{uuid4().hex}",
            operation="cancel",
            plan_summary=_cancel_plan_summary(order),
            confirm_text=_cancel_confirm_text(order),
            warnings=(),
            created_at=created_at,
            expires_at=_utc_expiry(self._plan_ttl_sec),
        )
        self._plan_store.save(plan, payload={"order_ref": order_ref})
        self._audit_log.append({"event": "trade.plan.created", "plan": plan.to_dict()})
        return plan

    def apply(self, plan_id: str) -> TradeApplyResult:
        record = self._plan_store.load(plan_id)
        if record is None:
            raise TradeError(TradeErrorCode.PLAN_NOT_FOUND, f"未找到 plan: {plan_id}")
        status = str(record.get("status") or "")
        if status == "applied":
            raise TradeError(TradeErrorCode.PLAN_ALREADY_APPLIED, "该 plan 已执行")
        plan = record["plan"]
        if _is_expired(str(plan["expires_at"])):
            self._plan_store.mark_expired(plan_id)
            raise TradeError(TradeErrorCode.PLAN_EXPIRED, "该 plan 已过期，请重新 plan")

        operation = str(plan["operation"])
        if operation == "submit_limit":
            payload = record["payload"]["intent"]
            intent = SubmitLimitOrderIntent(
                account_ref=str(payload["account_ref"]),
                symbol=str(payload["symbol"]),
                side=str(payload["side"]),
                quantity=float(payload["quantity"]),
                limit_price=float(payload["limit_price"]),
            )
            receipt = self._adapter.submit_limit_order(intent)
            order_status = self._adapter.get_order_status(receipt.order_ref)
            account_snapshot = None
            if order_status.status in {"partially_filled", "filled"}:
                account_snapshot = self.get_positions(intent.account_ref)
            result = TradeApplyResult(
                plan_id=plan_id,
                operation=operation,
                result_summary=_submit_result_summary(intent, order_status),
                receipt=receipt,
                order_status=order_status,
                account_snapshot=account_snapshot,
            )
        elif operation == "cancel":
            order_ref = str(record["payload"]["order_ref"])
            receipt = self._adapter.cancel_order(order_ref)
            order_status = self._adapter.get_order_status(order_ref)
            result = TradeApplyResult(
                plan_id=plan_id,
                operation=operation,
                result_summary=_cancel_result_summary(order_status),
                receipt=receipt,
                order_status=order_status,
                account_snapshot=None,
            )
        else:
            raise TradeError(TradeErrorCode.UNSUPPORTED_OPERATION, f"不支持的 plan 操作: {operation}")

        self._plan_store.mark_applied(plan_id, result=result.to_dict(), applied_at=_utc_now_iso())
        self._audit_log.append({"event": "trade.plan.applied", "plan_id": plan_id, "result": result.to_dict()})
        return result

    def get_plan(self, plan_id: str) -> dict[str, object] | None:
        return self._plan_store.load(plan_id)

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
        value = float(price)
        if value <= 0:
            raise TradeError(TradeErrorCode.INVALID_PRICE, "limit_price 必须大于 0")
        return value

    @staticmethod
    def _require_account_ref(account_ref: str) -> None:
        from athenaclaw.trading.types import decode_account_ref

        try:
            decode_account_ref(account_ref)
        except Exception as exc:  # pragma: no cover - thin validation wrapper
            raise TradeError(TradeErrorCode.INVALID_ACCOUNT_REF, "account_ref 非法") from exc

    @staticmethod
    def _require_order_ref(order_ref: str) -> None:
        from athenaclaw.trading.types import decode_order_ref

        try:
            decode_order_ref(order_ref)
        except Exception as exc:  # pragma: no cover - thin validation wrapper
            raise TradeError(TradeErrorCode.INVALID_ORDER_REF, "order_ref 非法") from exc

    @staticmethod
    def _account_parts(account_ref: str) -> dict[str, str]:
        from athenaclaw.trading.types import decode_account_ref

        try:
            return decode_account_ref(account_ref)
        except Exception as exc:  # pragma: no cover - validated by _require_account_ref
            raise TradeError(TradeErrorCode.INVALID_ACCOUNT_REF, "account_ref 非法") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_expiry(ttl_sec: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()


def _is_expired(ts: str) -> bool:
    return datetime.fromisoformat(ts) < datetime.now(timezone.utc)


def _preview_payload(preview: TradePreview | None) -> dict | None:
    if preview is None:
        return None
    return preview.to_dict()


def _submit_plan_summary(intent: SubmitLimitOrderIntent) -> str:
    return (
        f"计划提交 {intent.side.upper()} {intent.quantity:g} {intent.symbol} "
        f"限价 {intent.limit_price:.2f}"
    )


def _submit_confirm_text(intent: SubmitLimitOrderIntent) -> str:
    return (
        f"确认提交 {intent.side.upper()} {intent.quantity:g} {intent.symbol} "
        f"限价 {intent.limit_price:.2f} 吗？"
    )


def _cancel_plan_summary(order: TradeOrderSnapshot) -> str:
    return f"计划撤销 {order.symbol} {order.side.upper()} {order.quantity:g} 的未完成订单"


def _cancel_confirm_text(order: TradeOrderSnapshot) -> str:
    return f"确认撤销 {order.symbol} {order.side.upper()} {order.quantity:g} 的订单吗？"


def _submit_result_summary(intent: SubmitLimitOrderIntent, order: TradeOrderSnapshot) -> str:
    return (
        f"已提交 {intent.side.upper()} {intent.quantity:g} {intent.symbol} "
        f"限价 {intent.limit_price:.2f}，当前状态 {order.status}"
    )


def _cancel_result_summary(order: TradeOrderSnapshot) -> str:
    return f"订单当前状态 {order.status}"
