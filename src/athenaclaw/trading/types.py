"""
[INPUT]: base64, dataclasses, datetime, json
[OUTPUT]: 交易域 canonical dataclass 与 ref 编解码工具
[POS]: TradeOrchestrator 与 provider adapter 共享协议对象
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_account_ref(*, broker: str, env: str, account_id: str) -> str:
    return _encode_ref("account", {"broker": broker, "env": env, "account_id": account_id})


def decode_account_ref(ref: str) -> dict[str, str]:
    payload = _decode_ref(ref, expected_kind="account")
    return {
        "broker": str(payload["broker"]),
        "env": str(payload["env"]),
        "account_id": str(payload["account_id"]),
    }


def encode_order_ref(
    *,
    broker: str,
    env: str,
    account_id: str,
    order_id: str,
) -> str:
    return _encode_ref(
        "order",
        {
            "broker": broker,
            "env": env,
            "account_id": account_id,
            "order_id": str(order_id),
        },
    )


def decode_order_ref(ref: str) -> dict[str, str]:
    payload = _decode_ref(ref, expected_kind="order")
    return {
        "broker": str(payload["broker"]),
        "env": str(payload["env"]),
        "account_id": str(payload["account_id"]),
        "order_id": str(payload["order_id"]),
    }


def _encode_ref(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, **payload}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_ref(ref: str, *, expected_kind: str) -> dict[str, Any]:
    if not str(ref or "").strip():
        raise ValueError("empty ref")
    raw = str(ref).strip()
    padding = "=" * (-len(raw) % 4)
    data = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
    payload = json.loads(data)
    if payload.get("kind") != expected_kind:
        raise ValueError(f"invalid ref kind: {payload.get('kind')!r}")
    return payload


@dataclass(frozen=True)
class TradeCapabilities:
    supported_assets: tuple[str, ...] = ("stock", "etf")
    supported_order_types: tuple[str, ...] = ("limit",)
    supported_sides: tuple[str, ...] = ("buy", "sell")
    supported_envs: tuple[str, ...] = ("simulate", "real")
    supports_cancel: bool = True
    supports_account_summary: bool = False
    supports_preview_limit_order: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported_assets": list(self.supported_assets),
            "supported_order_types": list(self.supported_order_types),
            "supported_sides": list(self.supported_sides),
            "supported_envs": list(self.supported_envs),
            "supports_cancel": self.supports_cancel,
            "supports_account_summary": self.supports_account_summary,
            "supports_preview_limit_order": self.supports_preview_limit_order,
        }


@dataclass(frozen=True)
class TradeAccountDescriptor:
    account_ref: str
    broker: str
    account_id: str
    env: str
    display_name: str
    supported_markets: tuple[str, ...] = ()
    account_status: str = "unknown"
    account_kind: str = "unknown"
    is_simulated: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    capabilities: TradeCapabilities = field(default_factory=TradeCapabilities)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["supported_markets"] = list(self.supported_markets)
        data["capabilities"] = self.capabilities.to_dict()
        return data


@dataclass(frozen=True)
class TradeAccountSummary:
    account_ref: str
    cash: float = 0.0
    equity: float = 0.0
    currency: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradePosition:
    symbol: str
    quantity: float
    avg_cost: float | None = None
    currency: str | None = None
    can_sell_qty: float | None = None
    market_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeOpenOrder:
    order_ref: str
    account_ref: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float = 0.0
    limit_price: float | None = None
    status: str = "unknown"
    submitted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeOrderSnapshot:
    order_ref: str
    account_ref: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float = 0.0
    limit_price: float | None = None
    status: str = "unknown"
    submitted_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeAccountSnapshot:
    account_ref: str
    broker: str
    account_id: str
    env: str
    positions: tuple[TradePosition, ...]
    cash: float = 0.0
    equity: float = 0.0
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["positions"] = [item.to_dict() for item in self.positions]
        return data


@dataclass(frozen=True)
class SubmitLimitOrderIntent:
    account_ref: str
    symbol: str
    side: str
    quantity: float
    limit_price: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradePreview:
    warnings: tuple[str, ...] = ()
    max_buy: float | None = None
    max_sell: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "warnings": list(self.warnings),
            "max_buy": self.max_buy,
            "max_sell": self.max_sell,
        }


@dataclass(frozen=True)
class TradePlan:
    plan_id: str
    operation: str
    plan_summary: str
    confirm_text: str
    warnings: tuple[str, ...]
    created_at: str
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "operation": self.operation,
            "plan_summary": self.plan_summary,
            "confirm_text": self.confirm_text,
            "warnings": list(self.warnings),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "requires_confirmation": True,
        }


@dataclass(frozen=True)
class TradeReceipt:
    order_ref: str
    status: str
    submitted_at: str
    broker_order_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeApplyResult:
    plan_id: str
    operation: str
    result_summary: str
    receipt: TradeReceipt | None
    order_status: TradeOrderSnapshot | None
    account_snapshot: TradeAccountSnapshot | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "operation": self.operation,
            "result_summary": self.result_summary,
            "receipt": self.receipt.to_dict() if self.receipt else None,
            "order_status": self.order_status.to_dict() if self.order_status else None,
            "account_snapshot": self.account_snapshot.to_dict() if self.account_snapshot else None,
        }
