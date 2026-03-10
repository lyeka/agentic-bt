"""
[INPUT]: finnhub-python, pandas, datetime, calendar
[OUTPUT]: FinnhubAdapter — 美股日线 OHLCV 数据适配器（后备源）
[POS]: MarketAdapter 实现，通过 Finnhub REST API 获取美股数据（需免费 API Key）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

import pandas as pd


def _to_unix(date_str: str) -> int:
    """YYYY-MM-DD → UNIX timestamp (int)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(calendar.timegm(dt.timetuple()))


class FinnhubAdapter:
    """美股日线 OHLCV — Finnhub REST API"""

    name = "finnhub"

    def __init__(self, api_key: str) -> None:
        import finnhub
        self._client = finnhub.Client(api_key=api_key)

    def fetch(
        self,
        symbol: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        if start is None:
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        from_ = _to_unix(start)
        to_ = _to_unix(end)
        raw = self._client.stock_candles(symbol, "D", from_, to_)

        # ── 空数据处理 ──
        if raw.get("s") != "ok":
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        # ── dict → DataFrame ──
        df = pd.DataFrame({
            "date": pd.to_datetime(raw["t"], unit="s"),
            "open": raw["o"],
            "high": raw["h"],
            "low": raw["l"],
            "close": raw["c"],
            "volume": raw["v"],
        })
        df = df.sort_values("date").reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]
