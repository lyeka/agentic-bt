"""
[INPUT]: re, typing (Callable), athenaclaw.tools.market.schema
[OUTPUT]: CompositeMarketAdapter — 多数据源聚合路由器, is_ashare — A 股 symbol 识别
[POS]: adapter 层组合模式，对外满足 MarketAdapter Protocol，market tool 零感知
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import re
from typing import Callable

from athenaclaw.tools.market.schema import MarketFetchResult, MarketQuery


# ─────────────────────────────────────────────────────────────────────────────
# Composite
# ─────────────────────────────────────────────────────────────────────────────

class CompositeMarketAdapter:
    """多数据源聚合 — 对外就是一个 MarketAdapter"""

    name = "composite"

    def __init__(self) -> None:
        self._routes: list[tuple[Callable[[str], bool], object]] = []
        self._fallback: object | None = None

    def route(self, matcher: Callable[[str], bool], adapter: object) -> CompositeMarketAdapter:
        """注册路由规则（first-match-wins）"""
        self._routes.append((matcher, adapter))
        return self

    def fallback(self, adapter: object) -> CompositeMarketAdapter:
        """设置兜底 adapter"""
        self._fallback = adapter
        return self

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        for matcher, adapter in self._routes:
            if matcher(query.normalized_symbol):
                return adapter.fetch(query)
        if self._fallback:
            return self._fallback.fetch(query)
        raise ValueError(f"No adapter for symbol: {query.normalized_symbol}")


# ─────────────────────────────────────────────────────────────────────────────
# Matcher
# ─────────────────────────────────────────────────────────────────────────────

_ASHARE_RE = re.compile(r"^\d{6}\.(SZ|SS|SH|BJ)$", re.IGNORECASE)


def is_ashare(symbol: str) -> bool:
    """A 股 symbol：000001.SZ / 600519.SS / 688001.SH / 830001.BJ"""
    return bool(_ASHARE_RE.match(symbol))
