"""
[INPUT]: pandas
[OUTPUT]: CsvAdapter — 基于 DataFrame dict 的测试用数据适配器
[POS]: 测试用 MarketAdapter 实现，不依赖外部数据源
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pandas as pd


class CsvAdapter:
    """内存 OHLCV 适配器 — 用于测试和本地 CSV 数据"""

    name = "csv"

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data

    def fetch(
        self,
        symbol: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        df = self._data.get(symbol)
        if df is None:
            raise ValueError(f"数据中无 symbol: {symbol}")
        return df.copy()
