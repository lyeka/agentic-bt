"""
[INPUT]: pandas, athenaclaw.integrations.futu.*, athenaclaw.trading.*
[OUTPUT]: FutuTradeAdapter
[POS]: 富途交易 provider；对外实现 TradeBrokerAdapter
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from athenaclaw.integrations.futu.client_manager import FutuClientManager, _load_futu
from athenaclaw.integrations.futu.status_mapper import map_order_status
from athenaclaw.integrations.futu.symbols import to_futu_code
from athenaclaw.trading.errors import TradeError, TradeErrorCode
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
    decode_account_ref,
    decode_order_ref,
    encode_account_ref,
    encode_order_ref,
    utc_now_iso,
)


class FutuTradeAdapter:
    name = "futu"

    def __init__(self, *, config) -> None:
        self._config = config
        self._manager = FutuClientManager(config)

    def capabilities(self) -> TradeCapabilities:
        return TradeCapabilities(
            supported_assets=("stock", "etf"),
            supported_order_types=("limit",),
            supported_sides=("buy", "sell"),
            supported_envs=("simulate", "real"),
            supports_cancel=True,
            supports_account_summary=True,
            supports_preview_limit_order=True,
        )

    def list_accounts(self) -> list[TradeAccountDescriptor]:
        ctx = self._manager.trade_context()
        ret, data = ctx.get_acc_list()
        df = self._ensure_frame(ret, data, "get_acc_list")
        result: list[TradeAccountDescriptor] = []
        for _, row in df.iterrows():
            account_id = str(_col(row, "acc_id", "account_id") or "").strip()
            env = _normalize_env(_col(row, "trd_env", "trade_env"))
            label = _string_or_none(_col(row, "uni_card_num", "card_num"))
            supported_markets = _normalize_market_list(_col(row, "trdmarket_auth"))
            account_status = _normalize_account_status(_col(row, "acc_status"))
            account_kind = _normalize_account_kind(_col(row, "sim_acc_type"), _col(row, "acc_type"))
            extra = {
                "security_firm": _string_or_none(_col(row, "security_firm")),
                "acc_type": _string_or_none(_col(row, "acc_type")),
                "sim_acc_type": _string_or_none(_col(row, "sim_acc_type")),
                "acc_role": _string_or_none(_col(row, "acc_role")),
                "trdmarket_auth": list(supported_markets),
                "jp_acc_type": _normalize_string_list(_col(row, "jp_acc_type")),
                "uni_card_num": _string_or_none(_col(row, "uni_card_num")),
                "card_num": _string_or_none(_col(row, "card_num")),
            }
            display_name = _build_display_name(
                account_id=account_id,
                env=env,
                label=label,
                supported_markets=supported_markets,
                account_kind=account_kind,
            )
            result.append(
                TradeAccountDescriptor(
                    account_ref=encode_account_ref(broker=self.name, env=env, account_id=account_id),
                    broker=self.name,
                    account_id=account_id,
                    env=env,
                    display_name=display_name,
                    supported_markets=supported_markets,
                    account_status=account_status,
                    account_kind=account_kind,
                    is_simulated=(env == "simulate"),
                    extra=extra,
                    label=label,
                    capabilities=self.capabilities(),
                )
            )
        return result

    def get_positions(self, account_ref: str) -> list[TradePosition]:
        account = decode_account_ref(account_ref)
        ctx = self._manager.trade_context()
        ret, data = ctx.position_list_query(
            trd_env=_trd_env(account["env"]),
            acc_id=int(account["account_id"]),
        )
        df = self._ensure_frame(ret, data, "position_list_query")
        positions: list[TradePosition] = []
        for _, row in df.iterrows():
            positions.append(
                TradePosition(
                    symbol=_normalize_result_symbol(_col(row, "code")),
                    quantity=_float_or_zero(_col(row, "qty", "quantity")),
                    avg_cost=_float_or_none(_col(row, "cost_price", "average_cost")),
                    currency=_string_or_none(_col(row, "currency")),
                    can_sell_qty=_float_or_none(_col(row, "can_sell_qty")),
                    market_value=_float_or_none(_col(row, "market_val", "market_value")),
                )
            )
        return positions

    def get_open_orders(self, account_ref: str) -> list[TradeOpenOrder]:
        account = decode_account_ref(account_ref)
        ctx = self._manager.trade_context()
        ret, data = ctx.order_list_query(
            trd_env=_trd_env(account["env"]),
            acc_id=int(account["account_id"]),
        )
        df = self._ensure_frame(ret, data, "order_list_query")
        orders: list[TradeOpenOrder] = []
        for _, row in df.iterrows():
            order_id = str(_col(row, "order_id") or "").strip()
            status = map_order_status(_col(row, "order_status"))
            if status in {"filled", "cancelled", "rejected", "expired"}:
                continue
            orders.append(
                TradeOpenOrder(
                    order_ref=encode_order_ref(
                        broker=self.name,
                        env=account["env"],
                        account_id=account["account_id"],
                        order_id=order_id,
                    ),
                    account_ref=account_ref,
                    symbol=_normalize_result_symbol(_col(row, "code")),
                    side=_normalize_side(_col(row, "trd_side")),
                    quantity=_float_or_zero(_col(row, "qty", "order_qty")),
                    filled_quantity=_float_or_zero(_col(row, "dealt_qty", "filled_qty")),
                    limit_price=_float_or_none(_col(row, "price")),
                    status=status,
                    submitted_at=_string_or_none(_col(row, "create_time", "updated_time")),
                )
            )
        return orders

    def get_order_status(self, order_ref: str) -> TradeOrderSnapshot:
        order_parts = decode_order_ref(order_ref)
        account_ref = encode_account_ref(
            broker=order_parts["broker"],
            env=order_parts["env"],
            account_id=order_parts["account_id"],
        )
        ctx = self._manager.trade_context()
        ret, data = ctx.order_list_query(
            order_id=order_parts["order_id"],
            trd_env=_trd_env(order_parts["env"]),
            acc_id=int(order_parts["account_id"]),
        )
        df = self._ensure_frame(ret, data, "order_list_query", allow_empty=True)
        row = _find_order_row(df, order_parts["order_id"])
        if row is None:
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            ret, data = ctx.history_order_list_query(
                start=start,
                trd_env=_trd_env(order_parts["env"]),
                acc_id=int(order_parts["account_id"]),
            )
            df = self._ensure_frame(ret, data, "history_order_list_query", allow_empty=True)
            row = _find_order_row(df, order_parts["order_id"])
        if row is None:
            raise TradeError(TradeErrorCode.ORDER_NOT_FOUND, f"未找到订单: {order_parts['order_id']}")
        return TradeOrderSnapshot(
            order_ref=order_ref,
            account_ref=account_ref,
            symbol=_normalize_result_symbol(_col(row, "code")),
            side=_normalize_side(_col(row, "trd_side")),
            quantity=_float_or_zero(_col(row, "qty", "order_qty")),
            filled_quantity=_float_or_zero(_col(row, "dealt_qty", "filled_qty")),
            limit_price=_float_or_none(_col(row, "price")),
            status=map_order_status(_col(row, "order_status")),
            submitted_at=_string_or_none(_col(row, "create_time")),
            updated_at=_string_or_none(_col(row, "updated_time", "create_time")),
        )

    def submit_limit_order(self, intent: SubmitLimitOrderIntent) -> TradeReceipt:
        account = decode_account_ref(intent.account_ref)
        futu = _load_futu()
        ctx = self._manager.trade_context()
        side = futu.TrdSide.BUY if intent.side == "buy" else futu.TrdSide.SELL
        ret, data = ctx.place_order(
            price=float(intent.limit_price),
            qty=intent.quantity,
            code=to_futu_code(intent.symbol),
            trd_side=side,
            order_type=futu.OrderType.NORMAL,
            trd_env=_trd_env(account["env"]),
            acc_id=int(account["account_id"]),
        )
        df = self._ensure_frame(ret, data, "place_order")
        row = df.iloc[0]
        order_id = str(_col(row, "order_id") or "").strip()
        return TradeReceipt(
            order_ref=encode_order_ref(
                broker=self.name,
                env=account["env"],
                account_id=account["account_id"],
                order_id=order_id,
            ),
            status=map_order_status(_col(row, "order_status")) or "submitted",
            submitted_at=_string_or_none(_col(row, "create_time")) or utc_now_iso(),
            broker_order_id=order_id,
        )

    def cancel_order(self, order_ref: str) -> TradeReceipt:
        order = decode_order_ref(order_ref)
        futu = _load_futu()
        ctx = self._manager.trade_context()
        ret, data = ctx.modify_order(
            futu.ModifyOrderOp.CANCEL,
            int(order["order_id"]),
            0,
            0,
            trd_env=_trd_env(order["env"]),
            acc_id=int(order["account_id"]),
        )
        df = self._ensure_frame(ret, data, "modify_order")
        row = df.iloc[0] if not df.empty else None
        return TradeReceipt(
            order_ref=order_ref,
            status=map_order_status(_col(row, "order_status")) if row is not None else "cancelled",
            submitted_at=_string_or_none(_col(row, "updated_time")) if row is not None else utc_now_iso(),
            broker_order_id=order["order_id"],
        )

    def get_account_summary(self, account_ref: str) -> TradeAccountSummary | None:
        account = decode_account_ref(account_ref)
        ctx = self._manager.trade_context()
        ret, data = ctx.accinfo_query(
            trd_env=_trd_env(account["env"]),
            acc_id=int(account["account_id"]),
        )
        df = self._ensure_frame(ret, data, "accinfo_query", allow_empty=True)
        if df.empty:
            return None
        row = df.iloc[0]
        return TradeAccountSummary(
            account_ref=account_ref,
            cash=_float_or_zero(_col(row, "cash", "cash_balance")),
            equity=_float_or_zero(_col(row, "total_assets", "equity", "market_val")),
            currency=_string_or_none(_col(row, "currency")),
            updated_at=utc_now_iso(),
        )

    def preview_limit_order(self, intent: SubmitLimitOrderIntent) -> TradePreview | None:
        account = decode_account_ref(intent.account_ref)
        descriptor = self._find_account(intent.account_ref)
        if descriptor is None:
            raise TradeError(
                TradeErrorCode.ACCOUNT_NOT_FOUND,
                f"未找到账户: {account['account_id']}",
                details={"account_ref": intent.account_ref},
            )
        self._validate_account_for_intent(descriptor, intent)

        futu = _load_futu()
        ctx = self._manager.trade_context()
        ret, data = ctx.acctradinginfo_query(
            order_type=futu.OrderType.NORMAL,
            code=to_futu_code(intent.symbol),
            price=float(intent.limit_price),
            trd_env=_trd_env(account["env"]),
            acc_id=int(account["account_id"]),
        )
        df = self._ensure_frame(ret, data, "acctradinginfo_query", allow_empty=True)
        if df.empty:
            raise TradeError(
                TradeErrorCode.PREVIEW_REJECTED,
                f"无法预检查账户 {account['account_id']} 对 {intent.symbol} 的交易能力",
                details={"account_ref": intent.account_ref, "symbol": intent.symbol},
            )

        row = df.iloc[0]
        max_buy = _float_or_none(_col(row, "max_cash_and_margin_buy", "max_cash_buy"))
        max_sell = _float_or_none(_col(row, "max_position_sell"))
        if intent.side == "buy" and max_buy is not None and intent.quantity > max_buy:
            raise TradeError(
                TradeErrorCode.PREVIEW_REJECTED,
                f"当前账户最多可买 {max_buy:g}，无法提交 BUY {intent.quantity:g} {intent.symbol}",
                details={
                    "account_ref": intent.account_ref,
                    "symbol": intent.symbol,
                    "requested_quantity": intent.quantity,
                    "max_buy": max_buy,
                },
            )
        if intent.side == "sell" and max_sell is not None and intent.quantity > max_sell:
            raise TradeError(
                TradeErrorCode.PREVIEW_REJECTED,
                f"当前账户最多可卖 {max_sell:g}，无法提交 SELL {intent.quantity:g} {intent.symbol}",
                details={
                    "account_ref": intent.account_ref,
                    "symbol": intent.symbol,
                    "requested_quantity": intent.quantity,
                    "max_sell": max_sell,
                },
            )

        warnings: list[str] = []
        session = _string_or_none(_col(row, "session"))
        if session and session.upper() not in {"N/A", "NONE"}:
            warnings.append(f"provider session={session}")
        return TradePreview(warnings=tuple(warnings), max_buy=max_buy, max_sell=max_sell)

    def _find_account(self, account_ref: str) -> TradeAccountDescriptor | None:
        for item in self.list_accounts():
            if item.account_ref == account_ref:
                return item
        return None

    def _validate_account_for_intent(self, descriptor: TradeAccountDescriptor, intent: SubmitLimitOrderIntent) -> None:
        if descriptor.account_status == "disabled":
            raise TradeError(
                TradeErrorCode.ACCOUNT_INACTIVE,
                "当前账户已失效，不能用于下单",
                details={
                    "account_ref": descriptor.account_ref,
                    "account_status": descriptor.account_status,
                },
            )

        required_markets = _required_markets_for_symbol(intent.symbol)
        if descriptor.supported_markets and not any(market in descriptor.supported_markets for market in required_markets):
            raise TradeError(
                TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED,
                f"当前账户不支持交易 {intent.symbol}",
                details={
                    "account_ref": descriptor.account_ref,
                    "symbol": intent.symbol,
                    "required_markets": list(required_markets),
                    "supported_markets": list(descriptor.supported_markets),
                },
            )

        if descriptor.account_kind not in {"stock", "mixed", "unknown"}:
            raise TradeError(
                TradeErrorCode.PREVIEW_REJECTED,
                f"当前账户类型不适合股票/ETF 交易: {descriptor.account_kind}",
                details={
                    "account_ref": descriptor.account_ref,
                    "account_kind": descriptor.account_kind,
                },
            )

    @staticmethod
    def _ensure_frame(ret: int, data: Any, op: str, *, allow_empty: bool = False) -> pd.DataFrame:
        futu = _load_futu()
        if ret != futu.RET_OK:
            text = str(data)
            code = _translate_error_code(text, op=op)
            raise TradeError(code, f"{op} 失败: {text}")
        if isinstance(data, pd.DataFrame):
            return data
        if allow_empty:
            return pd.DataFrame()
        raise TradeError(TradeErrorCode.PROVIDER_ERROR, f"{op} 返回了非表格数据")


def _trd_env(env: str):
    futu = _load_futu()
    return futu.TrdEnv.SIMULATE if env == "simulate" else futu.TrdEnv.REAL


def _normalize_env(raw: object) -> str:
    text = _enum_name(raw)
    return "simulate" if "SIM" in text else "real"


def _normalize_side(raw: object) -> str:
    text = _enum_name(raw)
    return "buy" if "BUY" in text else "sell"


def _normalize_market_list(raw: object) -> tuple[str, ...]:
    values = _normalize_string_list(raw)
    normalized: list[str] = []
    for item in values:
        market = _enum_name(item)
        if market and market not in normalized:
            normalized.append(market)
    return tuple(normalized)


def _normalize_account_status(raw: object) -> str:
    text = _enum_name(raw)
    if text == "ACTIVE":
        return "active"
    if text == "DISABLED":
        return "disabled"
    return "unknown"


def _normalize_account_kind(sim_acc_type: object, acc_type: object) -> str:
    sim = _enum_name(sim_acc_type)
    if sim == "STOCK":
        return "stock"
    if sim == "OPTION":
        return "option"
    if sim == "FUTURES":
        return "futures"
    if sim == "STOCK_AND_OPTION":
        return "mixed"

    acc = _enum_name(acc_type)
    if acc in {"CASH", "MARGIN"}:
        return "stock"
    if "OPTION" in acc:
        return "option"
    if "FUTURE" in acc:
        return "futures"
    return "unknown"


def _build_display_name(
    *,
    account_id: str,
    env: str,
    label: str | None,
    supported_markets: tuple[str, ...],
    account_kind: str,
) -> str:
    base = label or account_id
    market_text = "/".join(supported_markets) if supported_markets else "unknown-market"
    return f"{base} ({env} | {market_text} | {account_kind})"


def _required_markets_for_symbol(symbol: str) -> tuple[str, ...]:
    code = to_futu_code(symbol)
    if code.startswith("US."):
        return ("US",)
    if code.startswith("HK."):
        return ("HK",)
    if code.startswith(("SH.", "SZ.", "BJ.")):
        return ("HKCC",)
    return ()


def _normalize_result_symbol(raw: object) -> str:
    text = str(raw or "").strip().upper()
    if text.startswith("US."):
        return text[3:]
    if text.startswith(("HK.", "SH.", "SZ.", "BJ.")):
        prefix, code = text.split(".", 1)
        return f"{code}.{prefix}"
    return text


def _find_order_row(df: pd.DataFrame, order_id: str):
    if df.empty:
        return None
    for _, row in df.iterrows():
        if str(_col(row, "order_id") or "").strip() == str(order_id):
            return row
    return None


def _col(row, *names: str):
    if row is None:
        return None
    for name in names:
        if name not in row.index:
            continue
        value = row[name]
        if isinstance(value, (list, tuple, set, dict)):
            return value
        try:
            if pd.notna(value):
                return value
        except Exception:
            if value is not None:
                return value
    return None


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _float_or_zero(value: object) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _string_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    if text.upper() == "N/A":
        return None
    return text or None


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        text = str(value).strip()
        if not text or text.upper() == "N/A":
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        items = [part.strip() for part in text.split(",")]
    normalized: list[str] = []
    for item in items:
        text = _enum_name(str(item or "").strip().strip("'").strip('"'))
        if not text or text.upper() == "N/A":
            continue
        normalized.append(text)
    return normalized


def _enum_name(value: object) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".")[-1]
    return text


def _translate_error_code(text: str, *, op: str) -> TradeErrorCode:
    lowered = text.lower()
    if "unlock" in lowered:
        return TradeErrorCode.TRADE_LOCKED
    if "不支持交易" in text or "not support" in lowered:
        return TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED
    if "disabled" in lowered or "失效" in text:
        return TradeErrorCode.ACCOUNT_INACTIVE
    if op == "acctradinginfo_query":
        return TradeErrorCode.PREVIEW_REJECTED
    return TradeErrorCode.PROVIDER_ERROR
