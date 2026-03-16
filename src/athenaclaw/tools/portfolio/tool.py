"""
[INPUT]: json, pathlib, re, athenaclaw.tools.market.schema
[OUTPUT]: register()
[POS]: portfolio 工具 — 维护结构化当前持仓快照（读取/更新/删除账户）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from athenaclaw.tools.market.schema import normalize_symbol


PORTFOLIO_PATH = "portfolio.json"


def register(kernel: object, workspace: Path) -> None:
    """向 Kernel 注册 portfolio 工具。"""

    path = workspace / PORTFOLIO_PATH

    def portfolio_handler(args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        if action == "get":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": PORTFOLIO_PATH}
            selector_error = _selector_error(
                account_id=args.get("account_id"),
                broker=args.get("broker"),
                label=args.get("label"),
                allow_empty=True,
            )
            if selector_error:
                return {"error": selector_error}
            target = _find_account(
                state,
                account_id=args.get("account_id"),
                broker=args.get("broker"),
                label=args.get("label"),
            )
            kernel.data.set("portfolio", state)
            if target is None and any(args.get(key) for key in ("account_id", "broker", "label")):
                return {"error": "未找到对应账户"}
            if target is None:
                return {"status": "ok", "accounts": state["accounts"]}
            return {"status": "ok", "account": target}

        if action == "upsert":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": PORTFOLIO_PATH}
            payload = args.get("account")
            if not isinstance(payload, dict):
                return {"error": "account 必须是 object"}

            positions_mode = str(args.get("positions_mode") or "replace").strip().lower()
            if positions_mode not in {"replace", "merge"}:
                return {"error": "positions_mode 必须是 replace 或 merge"}

            try:
                account, created = _upsert_account(state, payload, positions_mode=positions_mode)
            except ValueError as exc:
                return {"error": str(exc)}

            _save_state(path, state)
            kernel.data.set("portfolio", state)
            kernel.data.set(f"portfolio:{account['account_id']}", account)
            kernel.emit(
                "portfolio.changed",
                {
                    "action": "upsert",
                    "account_id": account["account_id"],
                    "positions_mode": positions_mode,
                    "created": created,
                    "path": PORTFOLIO_PATH,
                },
            )
            return {
                "status": "ok",
                "path": PORTFOLIO_PATH,
                "account": account,
                "created": created,
                "positions_mode": positions_mode,
            }

        if action == "delete_account":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": PORTFOLIO_PATH}
            selector_error = _selector_error(
                account_id=args.get("account_id"),
                broker=args.get("broker"),
                label=args.get("label"),
                allow_empty=False,
            )
            if selector_error:
                return {"error": selector_error}
            target = _find_account(
                state,
                account_id=args.get("account_id"),
                broker=args.get("broker"),
                label=args.get("label"),
            )
            if target is None:
                return {"error": "未找到对应账户"}

            state["accounts"] = [
                account for account in state["accounts"]
                if account.get("account_id") != target["account_id"]
            ]
            _save_state(path, state)
            kernel.data.set("portfolio", state)
            kernel.emit(
                "portfolio.changed",
                {
                    "action": "delete_account",
                    "account_id": target["account_id"],
                    "path": PORTFOLIO_PATH,
                },
            )
            return {
                "status": "ok",
                "path": PORTFOLIO_PATH,
                "deleted_account_id": target["account_id"],
            }

        return {"error": "未知 action，可用值: get/upsert/delete_account"}

    kernel.tool(
        name="portfolio",
        description=(
            "维护用户的结构化当前持仓快照，真相源是 workspace 下的 portfolio.json。"
            "何时使用: 用户发完整持仓截图、直接给出当前某账户持仓、或明确说某笔已执行交易后当前仓位变了。"
            "何时不要用: 用户只是说想买/想卖、讨论 watchlist、计划、假设，或截图明显不完整时。"
            "分析仓位、集中度、风险暴露前，如果你需要当前持仓，先调用 get。"
            "更新时统一使用 upsert。positions_mode=replace 表示本次给出的 positions 就是该账户最新完整持仓；"
            "positions_mode=merge 表示只更新本次提到的 symbol，未提到的不动，quantity=0 表示删除该持仓。"
            "如果只是口述一笔已执行交易，通常先 get 当前账户，再自行算出新的绝对数量和成本，再调用 upsert。"
            "详细持仓不要再写进 memory.md；memory.md 只保留高层偏好和长期背景。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "upsert", "delete_account"],
                    "description": "操作类型",
                },
                "account_id": {"type": "string", "description": "账户 ID；优先使用"},
                "broker": {"type": "string", "description": "券商名；当 account_id 未知时可与 label 一起定位账户"},
                "label": {"type": "string", "description": "账户标签；如 default、港股、尾号等"},
                "positions_mode": {
                    "type": "string",
                    "enum": ["replace", "merge"],
                    "description": "仅 upsert 使用；replace=整体替换持仓，merge=按 symbol 局部更新",
                    "default": "replace",
                },
                "account": {
                    "type": "object",
                    "description": "仅 upsert 使用；账户快照。创建新账户时至少提供 broker、label、as_of。",
                    "properties": {
                        "account_id": {"type": "string"},
                        "broker": {"type": "string"},
                        "label": {"type": "string"},
                        "as_of": {"type": "string", "description": "快照时间，建议 ISO 8601"},
                        "cash_by_currency": {
                            "type": "object",
                            "description": "现金按币种分桶，如 {\"USD\": 1200, \"HKD\": 5000}",
                            "additionalProperties": {"type": "number"},
                        },
                        "positions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string"},
                                    "name": {"type": "string"},
                                    "quantity": {"type": "number"},
                                    "avg_cost": {"type": "number"},
                                    "currency": {"type": "string"},
                                },
                                "required": ["symbol", "quantity"],
                            },
                        },
                    },
                },
            },
            "required": ["action"],
        },
        handler=portfolio_handler,
    )


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"accounts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("portfolio.json 不是合法 JSON，请先修复文件") from exc
    if not isinstance(data, dict):
        raise ValueError("portfolio.json 顶层必须是 object")
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("portfolio.json.accounts 必须是 array")
    normalized = []
    for index, item in enumerate(accounts):
        if not isinstance(item, dict):
            raise ValueError(f"portfolio.json.accounts[{index}] 必须是 object")
        try:
            normalized.append(_normalize_account(item, creating=False))
        except ValueError as exc:
            raise ValueError(f"portfolio.json.accounts[{index}] 非法: {exc}") from exc
    return {"accounts": normalized}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _find_account(
    state: dict[str, Any],
    *,
    account_id: Any = None,
    broker: Any = None,
    label: Any = None,
) -> dict[str, Any] | None:
    want_id = _clean(account_id)
    want_broker = _clean(broker)
    want_label = _clean(label)

    for account in state["accounts"]:
        if want_id and account.get("account_id") == want_id:
            return account
        if want_broker and want_label:
            if account.get("broker") == want_broker and account.get("label") == want_label:
                return account
    return None


def _selector_error(
    *,
    account_id: Any = None,
    broker: Any = None,
    label: Any = None,
    allow_empty: bool,
) -> str | None:
    want_id = _clean(account_id)
    want_broker = _clean(broker)
    want_label = _clean(label)

    if want_id:
        return None
    if not want_broker and not want_label:
        if allow_empty:
            return None
        return "需要提供 account_id，或同时提供 broker 和 label"
    if bool(want_broker) != bool(want_label):
        return "broker 和 label 需要一起提供"
    return None


def _upsert_account(
    state: dict[str, Any],
    payload: dict[str, Any],
    *,
    positions_mode: str,
) -> tuple[dict[str, Any], bool]:
    existing = _find_account(
        state,
        account_id=payload.get("account_id"),
        broker=payload.get("broker"),
        label=payload.get("label"),
    )

    if existing is None:
        account = _normalize_account(payload, creating=True)
        state["accounts"].append(account)
        state["accounts"].sort(key=lambda item: item["account_id"])
        return account, True

    merged = dict(existing)
    if "broker" in payload and _clean(payload.get("broker")):
        merged["broker"] = _clean(payload["broker"])
    if "label" in payload and _clean(payload.get("label")):
        merged["label"] = _clean(payload["label"])
    if "as_of" in payload and _clean(payload.get("as_of")):
        merged["as_of"] = _clean(payload["as_of"])
    if "cash_by_currency" in payload:
        merged["cash_by_currency"] = _normalize_cash(payload.get("cash_by_currency"))
    if "positions" in payload:
        incoming = _normalize_positions(payload.get("positions"))
        if positions_mode == "replace":
            merged["positions"] = incoming
        else:
            merged["positions"] = _merge_positions(existing.get("positions", []), incoming)

    normalized = _normalize_account(merged, creating=False)
    for idx, account in enumerate(state["accounts"]):
        if account.get("account_id") == existing["account_id"]:
            state["accounts"][idx] = normalized
            break
    return normalized, False


def _normalize_account(payload: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    account_id = _clean(payload.get("account_id"))
    broker = _clean(payload.get("broker"))
    label = _clean(payload.get("label"))
    as_of = _clean(payload.get("as_of"))

    if not account_id:
        if not broker or not label:
            raise ValueError("account_id 未提供时，broker 和 label 不能为空")
        account_id = _default_account_id(broker, label)

    if creating and (not broker or not label or not as_of):
        raise ValueError("创建账户时必须提供 broker、label、as_of")
    if not broker or not label:
        raise ValueError("账户必须包含 broker 和 label")
    if not as_of:
        raise ValueError("账户必须包含 as_of")

    positions = payload.get("positions", [])
    cash_by_currency = payload.get("cash_by_currency", {})

    return {
        "account_id": account_id,
        "broker": broker,
        "label": label,
        "as_of": as_of,
        "cash_by_currency": _normalize_cash(cash_by_currency),
        "positions": _normalize_positions(positions),
    }


def _normalize_cash(raw: Any) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("cash_by_currency 必须是 object")
    result: dict[str, float] = {}
    for key, value in raw.items():
        currency = _clean(key).upper()
        if not currency:
            continue
        result[currency] = _as_number(value, label=f"cash_by_currency.{currency}")
    return dict(sorted(result.items()))


def _normalize_positions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("positions 必须是 array")
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("positions 中每项都必须是 object")
        symbol_raw = _clean(item.get("symbol"))
        if not symbol_raw:
            raise ValueError("position.symbol 不能为空")
        quantity = _as_number(item.get("quantity"), label=f"positions[{symbol_raw}].quantity")
        record: dict[str, Any] = {
            "symbol": normalize_symbol(symbol_raw),
            "quantity": quantity,
        }
        name = _clean(item.get("name"))
        if name:
            record["name"] = name
        if "avg_cost" in item and item.get("avg_cost") is not None:
            record["avg_cost"] = _as_number(item.get("avg_cost"), label=f"positions[{symbol_raw}].avg_cost")
        currency = _clean(item.get("currency"))
        if currency:
            record["currency"] = currency.upper()
        normalized.append(record)
    normalized.sort(key=lambda item: item["symbol"])
    return normalized


def _merge_positions(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {item["symbol"]: dict(item) for item in existing}
    for item in incoming:
        symbol = item["symbol"]
        if item["quantity"] == 0:
            merged.pop(symbol, None)
            continue
        current = merged.get(symbol, {})
        current.update(item)
        merged[symbol] = current
    return [merged[symbol] for symbol in sorted(merged)]


def _default_account_id(broker: str, label: str) -> str:
    raw = f"{broker}-{label}".strip().lower()
    normalized = re.sub(r"[^\w]+", "-", raw, flags=re.UNICODE).strip("-")
    return normalized or "account"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_number(value: Any, *, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数字") from exc
