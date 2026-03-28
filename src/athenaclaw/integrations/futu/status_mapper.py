"""
[INPUT]: 无
[OUTPUT]: map_order_status
[POS]: 富途订单状态到 canonical 状态的映射
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations


def map_order_status(raw: object) -> str:
    text = str(raw or "").strip().upper()
    if text in {"SUBMITTING", "SUBMITTED"}:
        return "submitted"
    if text in {"WAITING_SUBMIT"}:
        return "queued"
    if text in {"FILLED_PART", "PARTIALLY_FILLED"}:
        return "partially_filled"
    if text in {"FILLED_ALL", "FILLED"}:
        return "filled"
    if text in {"CANCELLED_ALL", "CANCELLED_PART", "CANCELLED"}:
        return "cancelled"
    if text in {"FAILED", "DELETED", "DISABLED", "REJECTED"}:
        return "rejected"
    if text in {"TIMEOUT", "EXPIRED"}:
        return "expired"
    return "unknown"
