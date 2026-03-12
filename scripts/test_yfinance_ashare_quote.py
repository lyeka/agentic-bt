"""
[INPUT]: argparse, datetime, threading, zoneinfo, yfinance
[OUTPUT]: CLI probe for Yahoo Finance A-share quote support and delay
[POS]: scripts/ utility script that checks latest available quote for an A-share symbol
[PROTOCOL]: When changing this file, update scripts/CLAUDE.md and scripts/README.md
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime
from threading import Event, Thread
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


TZ_SH = ZoneInfo("Asia/Shanghai")
DEFAULT_SYMBOL = "601689.SS"
DEFAULT_TIMEOUT = 5.0


@dataclass
class ProbeResult:
    price: float | None
    timestamp: datetime | None
    source: str
    extra: dict[str, Any]


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ_SH)
    return value.astimezone(TZ_SH).isoformat()


def _delay_seconds(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ_SH)
    return max(0.0, (now - value.astimezone(TZ_SH)).total_seconds())


def _fmt_delay(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}s ({value / 60:.2f}m)"


def _error_result(source: str, error: Exception) -> ProbeResult:
    return ProbeResult(price=None, timestamp=None, source=source, extra={"error": repr(error)})


def probe_fast_info(ticker: yf.Ticker) -> ProbeResult:
    try:
        fast_info = ticker.fast_info
        metadata = ticker.history_metadata or {}
        market_time = metadata.get("lastTrade", {}).get("Time")
        if market_time is None and metadata.get("regularMarketTime") is not None:
            market_time = datetime.fromtimestamp(metadata["regularMarketTime"], tz=TZ_SH)
        return ProbeResult(
            price=fast_info.get("lastPrice"),
            timestamp=market_time,
            source="fast_info",
            extra={
                "currency": fast_info.get("currency"),
                "exchange": fast_info.get("exchange"),
                "quote_type": fast_info.get("quoteType"),
            },
        )
    except Exception as error:
        return _error_result("fast_info", error)


def probe_minute_history(ticker: yf.Ticker) -> ProbeResult:
    try:
        frame = ticker.history(period="1d", interval="1m", auto_adjust=False, prepost=False)
        if frame.empty:
            return ProbeResult(price=None, timestamp=None, source="history_1m", extra={"rows": 0})
        last_row = frame.tail(1).iloc[0]
        last_index = frame.tail(1).index[0].to_pydatetime()
        return ProbeResult(
            price=float(last_row["Close"]),
            timestamp=last_index,
            source="history_1m",
            extra={
                "rows": int(len(frame)),
                "volume": int(last_row["Volume"]),
            },
        )
    except Exception as error:
        return _error_result("history_1m", error)


def probe_websocket(symbol: str, timeout: float) -> ProbeResult:
    try:
        event = Event()
        payload: dict[str, Any] = {}

        def on_message(message: dict[str, Any]) -> None:
            if message.get("id") != symbol:
                return
            payload.update(message)
            event.set()

        yf_logger = logging.getLogger("yfinance")
        original_level = yf_logger.level
        yf_logger.setLevel(logging.CRITICAL)
        try:
            ws = yf.WebSocket(verbose=False)
            ws.subscribe([symbol])
            listener = Thread(target=lambda: ws.listen(on_message), daemon=True)
            listener.start()
            event.wait(timeout=timeout)
            ws.close()
            listener.join(timeout=2.0)
        finally:
            yf_logger.setLevel(original_level)

        if not payload:
            return ProbeResult(price=None, timestamp=None, source="websocket", extra={"received": False})

        ts_ms = int(payload["time"])
        ts = pd.to_datetime(ts_ms, unit="ms", utc=True).tz_convert(TZ_SH).to_pydatetime()
        return ProbeResult(
            price=float(payload["price"]),
            timestamp=ts,
            source="websocket",
            extra={
                "exchange": payload.get("exchange"),
                "market_hours": payload.get("market_hours"),
                "day_volume": payload.get("day_volume"),
                "received": True,
            },
        )
    except Exception as error:
        return _error_result("websocket", error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe whether yfinance can fetch an A-share quote and how delayed it is."
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=f"Yahoo Finance ticker, default: {DEFAULT_SYMBOL}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Seconds to wait for websocket tick, default: {DEFAULT_TIMEOUT}",
    )
    return parser.parse_args()


def print_result(result: ProbeResult, now: datetime) -> None:
    delay = _delay_seconds(result.timestamp, now)
    print(f"[{result.source}]")
    print(f"  price: {result.price}")
    print(f"  timestamp: {_fmt_dt(result.timestamp)}")
    print(f"  delay_vs_now: {_fmt_delay(delay)}")
    for key, value in result.extra.items():
        print(f"  {key}: {value}")


def main() -> None:
    args = parse_args()
    symbol = args.symbol
    now = datetime.now(TZ_SH)

    print(f"symbol: {symbol}")
    print(f"checked_at: {now.isoformat()}")

    ticker = yf.Ticker(symbol)

    history_result = probe_minute_history(ticker)
    metadata = ticker.history_metadata or {}
    print(f"long_name: {metadata.get('longName')}")
    print(f"exchange: {metadata.get('exchangeName')}")
    print(f"currency: {metadata.get('currency')}")
    print_result(probe_fast_info(ticker), now)
    print_result(history_result, now)
    print_result(probe_websocket(symbol, args.timeout), now)


if __name__ == "__main__":
    main()
