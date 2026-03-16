"""
[INPUT]: dataclasses, datetime, pandas
[OUTPUT]: MarketQuery/MarketFetchResult + query validation/storage helpers
[POS]: market 适配器共享协议层，统一 interval/mode/start/end 语义、symbol 归一化与 DataStore key
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


VALID_INTERVALS = ("1d", "1m", "5m", "15m", "30m", "60m")
VALID_MODES = ("history", "latest")
MINUTE_INTERVALS = VALID_INTERVALS[1:]
DEFAULT_CN_TIMEZONE = "Asia/Shanghai"
DEFAULT_US_TIMEZONE = "America/New_York"


@dataclass(frozen=True)
class MarketQuery:
    symbol: str
    normalized_symbol: str
    interval: str
    mode: str
    start: str | None
    end: str | None
    start_dt: datetime | None
    end_dt: datetime | None
    timezone: str

    @property
    def selector_key(self) -> str:
        return f"ohlcv:{self.normalized_symbol}:{self.interval}:{self.mode}"

    @property
    def exact_key(self) -> str:
        return (
            f"{self.selector_key}:{_window_token(self.start, default='default')}:"
            f"{_window_token(self.end, default='open')}"
        )

    @property
    def symbol_key(self) -> str:
        return f"ohlcv:{self.normalized_symbol}"

    @property
    def default_selector_key(self) -> str:
        return f"_default_ohlcv:{self.interval}:{self.mode}"


@dataclass(frozen=True)
class MarketFetchResult:
    df: pd.DataFrame
    source: str
    timezone: str
    as_of: str | None
    effective_start: str | None
    effective_end: str | None
    warning: str | None = None

    def meta(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "timezone": self.timezone,
            "as_of": self.as_of,
            "effective_start": self.effective_start,
            "effective_end": self.effective_end,
            "warning": self.warning,
        }


def build_market_query(
    *,
    symbol: str,
    interval: str | None = None,
    mode: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> MarketQuery:
    raw_symbol = (symbol or "").strip().upper()
    if not raw_symbol:
        raise ValueError("symbol 不能为空")

    normalized_symbol = normalize_symbol(raw_symbol)
    normalized_interval = normalize_interval(interval)
    normalized_mode = normalize_mode(mode)
    timezone = market_timezone(normalized_symbol)
    normalized_start, start_dt = _normalize_boundary(start, normalized_interval, "start")
    normalized_end, end_dt = _normalize_boundary(end, normalized_interval, "end")

    if normalized_mode == "latest":
        if normalized_start or normalized_end:
            raise ValueError("mode=latest 不接受 start/end")
        if normalized_interval == "1d":
            raise ValueError("mode=latest 只支持分钟级 interval，不支持 1d")

    if normalized_mode == "history" and normalized_end and not normalized_start:
        raise ValueError("仅提供 end 不受支持，请同时提供 start 或省略 end")

    if start_dt and end_dt and end_dt < start_dt:
        raise ValueError("end 不能早于 start")

    return MarketQuery(
        symbol=raw_symbol,
        normalized_symbol=normalized_symbol,
        interval=normalized_interval,
        mode=normalized_mode,
        start=normalized_start,
        end=normalized_end,
        start_dt=start_dt,
        end_dt=end_dt,
        timezone=timezone,
    )


def normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.endswith(".SS"):
        return f"{value[:-3]}.SH"
    return value


def market_timezone(symbol: str) -> str:
    if symbol.endswith((".SH", ".SZ", ".BJ")):
        return DEFAULT_CN_TIMEZONE
    return DEFAULT_US_TIMEZONE


def normalize_interval(interval: str | None) -> str:
    value = (interval or "1d").strip().lower()
    if value not in VALID_INTERVALS:
        raise ValueError(
            f"interval 必须是 {', '.join(VALID_INTERVALS)}，收到: {interval!r}"
        )
    return value


def normalize_mode(mode: str | None) -> str:
    value = (mode or "history").strip().lower()
    if value not in VALID_MODES:
        raise ValueError(f"mode 必须是 history 或 latest，收到: {mode!r}")
    return value


def format_boundary(value: datetime, interval: str) -> str:
    if interval == "1d":
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_record_timestamp(value: Any, interval: str) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    if interval == "1d":
        return ts.strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def make_fetch_result(
    *,
    df: pd.DataFrame,
    query: MarketQuery,
    source: str,
    timezone: str,
    warning: str | None = None,
) -> MarketFetchResult:
    if df.empty:
        return MarketFetchResult(
            df=df,
            source=source,
            timezone=timezone,
            as_of=None,
            effective_start=None,
            effective_end=None,
            warning=warning,
        )

    start = format_record_timestamp(df.iloc[0]["date"], query.interval)
    end = format_record_timestamp(df.iloc[-1]["date"], query.interval)
    return MarketFetchResult(
        df=df,
        source=source,
        timezone=timezone,
        as_of=end,
        effective_start=start,
        effective_end=end,
        warning=warning,
    )


def default_selector_key(interval: str, mode: str) -> str:
    return f"_default_ohlcv:{normalize_interval(interval)}:{normalize_mode(mode)}"


def meta_key(data_key: str) -> str:
    return f"meta:{data_key}"


def yfinance_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized.endswith(".SH"):
        return f"{normalized[:-3]}.SS"
    return normalized


def minute_delta(interval: str) -> pd.Timedelta:
    if interval == "1d":
        return pd.Timedelta(days=1)
    return pd.Timedelta(minutes=int(interval[:-1]))


def normalize_frame_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    normalized = df.copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    if getattr(normalized["date"].dt, "tz", None) is not None:
        normalized["date"] = normalized["date"].dt.tz_localize(None)
    return normalized.sort_values("date").reset_index(drop=True)


def _normalize_boundary(
    value: str | None,
    interval: str,
    label: str,
) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    raw = value.strip()
    if not raw:
        return None, None
    if interval == "1d":
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{label} 必须是 YYYY-MM-DD") from exc
    else:
        text = raw.replace("T", " ")
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"{label} 必须是 YYYY-MM-DD HH:MM:SS") from exc
        raw = text
    return format_boundary(dt, interval), dt


def _window_token(value: str | None, *, default: str) -> str:
    if value is None:
        return f"__{default}__"
    return value.replace("-", "").replace(" ", "T").replace(":", "")
