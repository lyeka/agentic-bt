"""
[INPUT]: finnhub-python, pandas, datetime, calendar, agent.adapters.market.schema
[OUTPUT]: FinnhubAdapter — 美股日线 OHLCV 数据适配器（后备源）
[POS]: MarketAdapter 实现，通过 Finnhub REST API 获取美股数据（需免费 API Key）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

import pandas as pd

from agent.adapters.market.schema import MarketFetchResult, MarketQuery, make_fetch_result


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

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        if query.interval != "1d" or query.mode != "history":
            raise ValueError("finnhub 仅支持 1d history")

        start = query.start or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end = query.end or datetime.now().strftime("%Y-%m-%d")

        raw = self._client.stock_candles(query.normalized_symbol, "D", _to_unix(start), _to_unix(end))
        if raw.get("s") != "ok":
            df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        else:
            df = pd.DataFrame({
                "date": pd.to_datetime(raw["t"], unit="s"),
                "open": raw["o"],
                "high": raw["h"],
                "low": raw["l"],
                "close": raw["c"],
                "volume": raw["v"],
            }).sort_values("date").reset_index(drop=True)

        return make_fetch_result(
            df=df[["date", "open", "high", "low", "close", "volume"]],
            query=query,
            source=self.name,
            timezone=query.timezone,
        )
