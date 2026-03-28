"""
[INPUT]: athenaclaw.tools.market.schema
[OUTPUT]: to_futu_code
[POS]: 富途交易 symbol 映射
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from athenaclaw.tools.market.schema import normalize_symbol


def to_futu_code(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if "." not in normalized:
        return f"US.{normalized}"
    code, market = normalized.split(".", 1)
    mapping = {
        "HK": "HK",
        "SH": "SH",
        "SZ": "SZ",
        "BJ": "BJ",
    }
    prefix = mapping.get(market)
    if prefix is None:
        raise ValueError(f"不支持的 symbol 市场: {symbol}")
    return f"{prefix}.{code}"
