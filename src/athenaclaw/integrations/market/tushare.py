"""
[INPUT]: tushare, pandas, datetime, athenaclaw.tools.market.schema
[OUTPUT]: TushareAdapter — A 股日线/分钟/最新 bar 适配器
[POS]: MarketAdapter 实现，通过 tushare Pro API 获取真实 A 股数据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import tushare as ts

from athenaclaw.tools.market.schema import (
    MarketFetchResult,
    MarketQuery,
    make_fetch_result,
    normalize_frame_dates,
)


_TS_HISTORY_FREQ = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
}
_TS_LATEST_FREQ = {
    "1m": "1MIN",
    "5m": "5MIN",
    "15m": "15MIN",
    "30m": "30MIN",
    "60m": "60MIN",
}


class TushareAdapter:
    """A 股 OHLCV — tushare Pro API"""

    name = "tushare"

    def __init__(self, token: str) -> None:
        self._api = ts.pro_api(token)

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        if query.mode == "latest":
            df = self._fetch_latest(query)
        elif query.interval == "1d":
            df = self._fetch_daily(query)
        else:
            df = self._fetch_intraday(query)
        return make_fetch_result(
            df=df,
            query=query,
            source=self.name,
            timezone=query.timezone,
        )

    def _fetch_daily(self, query: MarketQuery) -> pd.DataFrame:
        end_dt = query.end_dt or datetime.now()
        start_dt = query.start_dt or (end_dt - timedelta(days=365))
        frame = self._api.daily(
            ts_code=query.normalized_symbol,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
        )
        return self._normalize_frame(frame, date_col="trade_date")

    def _fetch_intraday(self, query: MarketQuery) -> pd.DataFrame:
        end_dt = query.end_dt or datetime.now()
        start_dt = query.start_dt or (end_dt - timedelta(days=7))
        try:
            frame = self._api.stk_mins(
                ts_code=query.normalized_symbol,
                start_date=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                end_date=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                freq=_TS_HISTORY_FREQ[query.interval],
            )
        except Exception as exc:  # pragma: no cover - exercised via tests
            self._raise_minute_error(exc)

        df = self._normalize_frame(frame, date_col="trade_time")
        if query.start_dt is None and query.end_dt is None and not df.empty:
            latest_day = df["date"].dt.date.max()
            df = df[df["date"].dt.date == latest_day].reset_index(drop=True)
        return df

    def _fetch_latest(self, query: MarketQuery) -> pd.DataFrame:
        try:
            frame = self._api.rt_min_daily(
                ts_code=query.normalized_symbol,
                freq=_TS_LATEST_FREQ[query.interval],
            )
        except Exception as exc:  # pragma: no cover - exercised via tests
            self._raise_minute_error(exc)
        return self._normalize_realtime_frame(frame).tail(1).reset_index(drop=True)

    def _normalize_frame(self, frame: pd.DataFrame, *, date_col: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        df = frame.rename(columns={date_col: "date", "vol": "volume"})
        return normalize_frame_dates(df[["date", "open", "high", "low", "close", "volume"]])

    def _normalize_realtime_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        df = frame.copy()
        if "date" in df.columns and "time" in df.columns:
            df["date"] = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
        elif "time" in df.columns and "date" not in df.columns:
            time_text = df["time"].astype(str).str.strip()
            if time_text.str.contains("-").any():
                df["date"] = time_text
            else:
                today = datetime.now().strftime("%Y-%m-%d")
                df["date"] = today + " " + time_text
        elif "trade_time" in df.columns:
            df = df.rename(columns={"trade_time": "date"})
        elif "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df = df.rename(columns={"vol": "volume"})
        return normalize_frame_dates(df[["date", "open", "high", "low", "close", "volume"]])

    def _raise_minute_error(self, error: Exception) -> None:
        message = str(error)
        lowered = message.lower()
        if any(token in lowered for token in ("权限", "积分", "permission", "sorry", "not enough", "抱歉")):
            raise ValueError(
                f"tushare 分钟或最新 bar 接口未开通权限: {message}。请开通权限或切换 MARKET_CN=yfinance"
            ) from error
        raise error
