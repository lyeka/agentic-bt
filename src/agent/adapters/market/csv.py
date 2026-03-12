"""
[INPUT]: pandas, agent.adapters.market.schema
[OUTPUT]: CsvAdapter — 基于 DataFrame dict 的测试用数据适配器
[POS]: 测试用 MarketAdapter 实现，不依赖外部数据源
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pandas as pd

from agent.adapters.market.schema import (
    MarketFetchResult,
    MarketQuery,
    make_fetch_result,
    normalize_frame_dates,
    normalize_symbol,
)


class CsvAdapter:
    """内存 OHLCV 适配器 — 用于测试和本地 CSV 数据"""

    name = "csv"

    def __init__(self, data: dict[str, pd.DataFrame | dict[object, pd.DataFrame]]) -> None:
        self._data = data

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        df = self._lookup(query)
        if df is None:
            raise ValueError(f"数据中无 symbol: {query.normalized_symbol}")

        normalized = normalize_frame_dates(df)
        if query.start_dt is not None:
            normalized = normalized[normalized["date"] >= pd.Timestamp(query.start_dt)]
        if query.end_dt is not None:
            normalized = normalized[normalized["date"] <= pd.Timestamp(query.end_dt)]
        if query.mode == "latest":
            normalized = normalized.tail(1)

        return make_fetch_result(
            df=normalized.reset_index(drop=True),
            query=query,
            source=self.name,
            timezone=query.timezone,
        )

    def _lookup(self, query: MarketQuery) -> pd.DataFrame | None:
        entry = self._data.get(query.normalized_symbol)
        if entry is None:
            entry = self._data.get(normalize_symbol(query.symbol))
        if entry is None:
            entry = self._data.get(query.symbol)
        if entry is None:
            return None
        if isinstance(entry, pd.DataFrame):
            return entry.copy()
        for key in ((query.interval, query.mode), f"{query.interval}:{query.mode}", query.interval):
            df = entry.get(key)
            if df is not None:
                return df.copy()
        return None
