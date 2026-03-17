"""
[INPUT]: json, pathlib, datetime, athenaclaw.tools.market.schema
[OUTPUT]: register()
[POS]: watchlist 工具 — 维护结构化自选列表快照（读取/更新/删除列表）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from athenaclaw.tools.market.schema import normalize_symbol


WATCHLIST_PATH = "watchlist.json"
_MISSING = object()


def register(kernel: object, workspace: Path) -> None:
    """向 Kernel 注册 watchlist 工具。"""

    path = workspace / WATCHLIST_PATH

    def watchlist_handler(args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        if action == "get":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": WATCHLIST_PATH}

            list_id = _clean(args.get("list_id"))
            kernel.data.set("watchlist", state)
            if not list_id:
                return {"status": "ok", "lists": state["lists"]}

            items = state["lists"].get(list_id)
            if items is None:
                return {"error": "未找到对应列表"}
            snapshot = {"list_id": list_id, "items": items}
            kernel.data.set(f"watchlist:{list_id}", snapshot)
            return {"status": "ok", "list": snapshot}

        if action == "upsert":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": WATCHLIST_PATH}

            list_id = _clean(args.get("list_id")) or "default"
            items_mode = str(args.get("items_mode") or "replace").strip().lower()
            if items_mode not in {"replace", "merge"}:
                return {"error": "items_mode 必须是 replace 或 merge"}
            if "items" not in args:
                return {"error": "items 必须提供"}

            try:
                snapshot, created = _upsert_list(
                    state,
                    list_id=list_id,
                    raw_items=args.get("items"),
                    items_mode=items_mode,
                    now_iso=_now_iso(),
                )
            except ValueError as exc:
                return {"error": str(exc)}

            _save_state(path, state)
            kernel.data.set("watchlist", state)
            kernel.data.set(f"watchlist:{list_id}", snapshot)
            kernel.emit(
                "watchlist.changed",
                {
                    "action": "upsert",
                    "list_id": list_id,
                    "items_mode": items_mode,
                    "created": created,
                    "path": WATCHLIST_PATH,
                },
            )
            return {
                "status": "ok",
                "path": WATCHLIST_PATH,
                "list": snapshot,
                "created": created,
                "items_mode": items_mode,
            }

        if action == "remove_items":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": WATCHLIST_PATH}

            list_id = _clean(args.get("list_id"))
            if not list_id:
                return {"error": "remove_items 需要提供 list_id"}
            try:
                snapshot, removed_symbols, deleted_list = _remove_items(
                    state,
                    list_id=list_id,
                    raw_symbols=args.get("symbols"),
                )
            except ValueError as exc:
                return {"error": str(exc)}

            _save_state(path, state)
            kernel.data.set("watchlist", state)
            kernel.data.set(f"watchlist:{list_id}", snapshot)
            kernel.emit(
                "watchlist.changed",
                {
                    "action": "remove_items",
                    "list_id": list_id,
                    "removed_symbols": removed_symbols,
                    "deleted_list": deleted_list,
                    "path": WATCHLIST_PATH,
                },
            )
            return {
                "status": "ok",
                "path": WATCHLIST_PATH,
                "list": snapshot,
                "removed_symbols": removed_symbols,
                "deleted_list": deleted_list,
            }

        if action == "delete_list":
            try:
                state = _load_state(path)
            except ValueError as exc:
                return {"error": str(exc), "path": WATCHLIST_PATH}

            list_id = _clean(args.get("list_id"))
            if not list_id:
                return {"error": "delete_list 需要提供 list_id"}
            if list_id not in state["lists"]:
                return {"error": "未找到对应列表"}

            state["lists"].pop(list_id, None)
            _save_state(path, state)
            kernel.data.set("watchlist", state)
            kernel.data.set(f"watchlist:{list_id}", {"list_id": list_id, "items": []})
            kernel.emit(
                "watchlist.changed",
                {
                    "action": "delete_list",
                    "list_id": list_id,
                    "path": WATCHLIST_PATH,
                },
            )
            return {
                "status": "ok",
                "path": WATCHLIST_PATH,
                "deleted_list_id": list_id,
            }

        return {"error": "未知 action，可用值: get/upsert/remove_items/delete_list"}

    kernel.tool(
        name="watchlist",
        description=(
            "维护用户的结构化自选列表快照，真相源是 workspace 下的 watchlist.json。"
            "何时使用: 用户说加入自选、移出自选、给出当前完整自选列表，"
            "或要求围绕某个观察理由持续跟踪标的时。"
            "何时不要用: 用户给的是当前持仓、一次性闲聊、长篇研究日志、"
            "价格提醒规则，或 symbol 无法可靠识别时。"
            "自选条目只保留 symbol、name、watch_reason、added_at。"
            "name 是可选显示名，便于人和 UI 阅读；symbol 仍然是唯一身份。"
            "watch_reason 表示当前这轮观察的核心问题；added_at 表示本轮观察开始时间。"
            "更新时统一使用 upsert。items_mode=replace 表示本次给出的 items 就是该列表当前完整快照；"
            "items_mode=merge 表示只更新提到的 symbol，未提到的不动。"
            "name 在 merge/replace 时：省略=保留旧值，传 null=清空，空字符串报错。"
            "watch_reason 在 merge/replace 时：省略=保留旧值，传 null=清空，空字符串报错。"
            "分析自选复盘、加入后走势、开盘前巡检前，如果需要当前自选列表，先调用 get。"
            "具体自选 symbol 清单不要再写进 memory.md；memory.md 只保留高层关注方向和长期偏好。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "upsert", "remove_items", "delete_list"],
                    "description": "操作类型",
                },
                "list_id": {
                    "type": "string",
                    "description": "列表 ID；upsert 不传时默认 default",
                },
                "items_mode": {
                    "type": "string",
                    "enum": ["replace", "merge"],
                    "description": "仅 upsert 使用；replace=整体替换列表，merge=按 symbol 局部更新",
                    "default": "replace",
                },
                "items": {
                    "type": "array",
                    "description": (
                        "仅 upsert 使用；自选条目列表。每项至少提供 symbol。"
                        "name 是可选显示名；省略=保留旧值，null=清空，空字符串不允许。"
                        "watch_reason 表示当前观察锚点；省略=保留旧值，null=清空，空字符串不允许。"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "name": {
                                "type": ["string", "null"],
                                "description": "可选显示名；允许传 null 清空",
                            },
                            "watch_reason": {
                                "type": ["string", "null"],
                                "description": "当前这轮观察的核心问题；允许传 null 清空",
                            },
                        },
                        "required": ["symbol"],
                    },
                },
                "symbols": {
                    "type": "array",
                    "description": "仅 remove_items 使用；要删除的 symbol 列表",
                    "items": {"type": "string"},
                },
            },
            "required": ["action"],
        },
        handler=watchlist_handler,
    )


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"lists": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("watchlist.json 不是合法 JSON，请先修复文件") from exc
    if not isinstance(data, dict):
        raise ValueError("watchlist.json 顶层必须是 object")
    lists = data.get("lists")
    if not isinstance(lists, dict):
        raise ValueError("watchlist.json.lists 必须是 object")

    normalized: dict[str, list[dict[str, Any]]] = {}
    for raw_list_id, raw_items in lists.items():
        list_id = _clean(raw_list_id)
        if not list_id:
            raise ValueError("watchlist.json.lists 的 key 不能为空")
        normalized[list_id] = _normalize_stored_items(raw_items, list_id=list_id)
    return {"lists": normalized}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_list(
    state: dict[str, Any],
    *,
    list_id: str,
    raw_items: Any,
    items_mode: str,
    now_iso: str,
) -> tuple[dict[str, Any], bool]:
    incoming = _normalize_incoming_items(raw_items, list_id=list_id)
    existing = state["lists"].get(list_id)
    created = existing is None
    if items_mode == "replace":
        merged = _replace_items(existing or [], incoming, now_iso=now_iso)
    else:
        merged = _merge_items(existing or [], incoming, now_iso=now_iso)

    if merged:
        state["lists"][list_id] = merged
    else:
        state["lists"].pop(list_id, None)
    return {"list_id": list_id, "items": merged}, created


def _remove_items(
    state: dict[str, Any],
    *,
    list_id: str,
    raw_symbols: Any,
) -> tuple[dict[str, Any], list[str], bool]:
    existing = state["lists"].get(list_id)
    if existing is None:
        raise ValueError("未找到对应列表")
    symbols = _normalize_symbol_list(raw_symbols)
    removed = [item["symbol"] for item in existing if item["symbol"] in symbols]
    remaining = [dict(item) for item in existing if item["symbol"] not in symbols]
    deleted_list = not remaining
    if deleted_list:
        state["lists"].pop(list_id, None)
    else:
        state["lists"][list_id] = remaining
    return {"list_id": list_id, "items": remaining}, removed, deleted_list


def _normalize_stored_items(raw: Any, *, list_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError(f"watchlist.json.lists[{list_id}] 必须是 array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"watchlist.json.lists[{list_id}][{index}] 必须是 object")
        symbol_raw = _clean(item.get("symbol"))
        if not symbol_raw:
            raise ValueError(f"watchlist.json.lists[{list_id}][{index}].symbol 不能为空")
        symbol = normalize_symbol(symbol_raw)
        if symbol in seen:
            raise ValueError(f"watchlist.json.lists[{list_id}] 中存在重复 symbol: {symbol}")
        added_at = _clean(item.get("added_at"))
        if not added_at:
            raise ValueError(f"watchlist.json.lists[{list_id}][{index}].added_at 不能为空")
        record: dict[str, Any] = {"symbol": symbol, "added_at": added_at}
        if "name" in item:
            record["name"] = _normalize_stored_text_field(
                item.get("name"),
                label=f"watchlist.json.lists[{list_id}][{index}].name",
            )
        if "watch_reason" in item:
            record["watch_reason"] = _normalize_stored_text_field(
                item.get("watch_reason"),
                label=f"watchlist.json.lists[{list_id}][{index}].watch_reason",
            )
        normalized.append(record)
        seen.add(symbol)
    return normalized


def _normalize_incoming_items(raw: Any, *, list_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("items 必须是 array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("items 中每项都必须是 object")
        symbol_raw = _clean(item.get("symbol"))
        if not symbol_raw:
            raise ValueError("item.symbol 不能为空")
        symbol = normalize_symbol(symbol_raw)
        if symbol in seen:
            raise ValueError(f"{list_id} 中存在重复 symbol: {symbol}")
        record = {
            "symbol": symbol,
            "name": _normalize_optional_text_field(item, field="name"),
            "watch_reason": _normalize_optional_text_field(item, field="watch_reason"),
        }
        normalized.append(record)
        seen.add(symbol)
    return normalized


def _normalize_optional_text_field(item: dict[str, Any], *, field: str) -> object:
    if field not in item:
        return _MISSING
    value = item.get(field)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} 不能为空字符串；清空请传 null")
    return text


def _normalize_stored_text_field(value: Any, *, label: str) -> str:
    if value is None:
        raise ValueError(f"{label} 不能为 null")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} 不能为空字符串")
    return text


def _normalize_symbol_list(raw: Any) -> set[str]:
    if not isinstance(raw, list):
        raise ValueError("symbols 必须是 array")
    normalized: set[str] = set()
    for symbol in raw:
        text = _clean(symbol)
        if not text:
            raise ValueError("symbols 中不能有空值")
        normalized.add(normalize_symbol(text))
    return normalized


def _replace_items(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    now_iso: str,
) -> list[dict[str, Any]]:
    existing_by_symbol = {item["symbol"]: item for item in existing}
    replaced: list[dict[str, Any]] = []
    for item in incoming:
        current = existing_by_symbol.get(item["symbol"])
        record: dict[str, Any] = {
            "symbol": item["symbol"],
            "added_at": current["added_at"] if current else now_iso,
        }
        _apply_optional_text_field(record, current, field="name", value=item["name"])
        _apply_watch_reason(record, current, item["watch_reason"])
        replaced.append(record)
    return replaced


def _merge_items(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    now_iso: str,
) -> list[dict[str, Any]]:
    merged = [dict(item) for item in existing]
    index_by_symbol = {item["symbol"]: idx for idx, item in enumerate(merged)}
    for item in incoming:
        idx = index_by_symbol.get(item["symbol"])
        current = merged[idx] if idx is not None else None
        record = dict(current) if current else {"symbol": item["symbol"], "added_at": now_iso}
        _apply_optional_text_field(record, current, field="name", value=item["name"])
        _apply_watch_reason(record, current, item["watch_reason"])
        if idx is None:
            index_by_symbol[item["symbol"]] = len(merged)
            merged.append(record)
        else:
            merged[idx] = record
    return merged


def _apply_watch_reason(
    record: dict[str, Any],
    current: dict[str, Any] | None,
    watch_reason: object,
) -> None:
    _apply_optional_text_field(record, current, field="watch_reason", value=watch_reason)


def _apply_optional_text_field(
    record: dict[str, Any],
    current: dict[str, Any] | None,
    *,
    field: str,
    value: object,
) -> None:
    if value is _MISSING:
        if current and field in current:
            record[field] = current[field]
        return
    if value is None:
        record.pop(field, None)
        return
    record[field] = str(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
