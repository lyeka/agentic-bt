"""
[INPUT]: yfinance, pandas, athenaclaw.tools.market.schema
[OUTPUT]: YFinanceAdapter — Yahoo Finance 日线/分钟/最新 bar 适配器
[POS]: MarketAdapter 实现，通过 yfinance 获取 Yahoo Finance OHLCV 数据（零 API Key）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import sys
from types import ModuleType

import pandas as pd

try:
    import yfinance as yf  # type: ignore
except ModuleNotFoundError:
    yf = ModuleType("yfinance")

    class _MissingTicker:
        def __init__(self, *_args, **_kwargs) -> None:
            raise ModuleNotFoundError("缺少依赖: yfinance。请安装 `pip install -e '.[market]'`")

    yf.Ticker = _MissingTicker  # type: ignore[attr-defined]
    sys.modules.setdefault("yfinance", yf)

from athenaclaw.tools.market.schema import (
    MINUTE_INTERVALS,
    MarketFetchResult,
    MarketQuery,
    make_fetch_result,
    minute_delta,
    normalize_frame_dates,
    yfinance_symbol,
)


class YFinanceAdapter:
    """Yahoo Finance OHLCV — 支持 1d/history 与分钟 history/latest"""

    name = "yfinance"

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        ticker = yf.Ticker(yfinance_symbol(query.normalized_symbol))
        if query.interval == "1d":
            df = self._fetch_daily(ticker, query)
        else:
            df = self._fetch_intraday(ticker, query)

        warning = None
        if query.interval in MINUTE_INTERVALS and query.normalized_symbol.endswith((".SH", ".SZ", ".BJ")):
            warning = "Yahoo Finance intraday data may be delayed for this market."
        return make_fetch_result(
            df=df,
            query=query,
            source=self.name,
            timezone=query.timezone,
            warning=warning,
        )

    def _fetch_daily(self, ticker: yf.Ticker, query: MarketQuery) -> pd.DataFrame:
        kwargs: dict[str, object] = {"interval": "1d", "auto_adjust": False}
        if query.start_dt is None and query.end_dt is None:
            kwargs["period"] = "1y"
        else:
            if query.start_dt is not None:
                kwargs["start"] = query.start
            if query.end_dt is not None:
                kwargs["end"] = (pd.Timestamp(query.end_dt) + minute_delta("1d")).strftime("%Y-%m-%d")
        return self._normalize_history_frame(ticker.history(**kwargs))

    def _fetch_intraday(self, ticker: yf.Ticker, query: MarketQuery) -> pd.DataFrame:
        kwargs: dict[str, object] = {
            "interval": query.interval,
            "auto_adjust": False,
            "prepost": False,
        }
        if query.start_dt is None and query.end_dt is None:
            kwargs["period"] = "5d"
        else:
            if query.start_dt is not None:
                kwargs["start"] = query.start
            if query.end_dt is not None:
                kwargs["end"] = (
                    pd.Timestamp(query.end_dt) + minute_delta(query.interval)
                ).strftime("%Y-%m-%d %H:%M:%S")

        df = self._normalize_history_frame(ticker.history(**kwargs))
        if df.empty:
            return df

        if query.start_dt is None and query.end_dt is None:
            latest_day = df["date"].dt.date.max()
            df = df[df["date"].dt.date == latest_day].reset_index(drop=True)
        else:
            if query.start_dt is not None:
                df = df[df["date"] >= pd.Timestamp(query.start_dt)]
            if query.end_dt is not None:
                df = df[df["date"] <= pd.Timestamp(query.end_dt)]
            df = df.reset_index(drop=True)

        if query.mode == "latest":
            return df.tail(1).reset_index(drop=True)
        return df

    def _normalize_history_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)

        df = frame.reset_index()
        date_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={
            date_col: "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        return normalize_frame_dates(df[["date", "open", "high", "low", "close", "volume"]])
