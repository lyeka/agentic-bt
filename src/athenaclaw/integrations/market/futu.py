"""
[INPUT]: pandas, datetime, athenaclaw.integrations.futu.*, athenaclaw.tools.market.schema
[OUTPUT]: FutuAdapter — Futu OpenD Quote OHLCV 适配器
[POS]: MarketAdapter 实现，通过 Futu request_history_kline/get_cur_kline 获取 CN/HK/US OHLCV
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from athenaclaw.integrations.futu.client_manager import FutuClientManager, _load_futu
from athenaclaw.integrations.futu.symbols import to_futu_code
from athenaclaw.tools.market.schema import (
    MarketFetchResult,
    MarketQuery,
    format_boundary,
    make_fetch_result,
    normalize_frame_dates,
)


_KLTYPE_BY_INTERVAL = {
    "1d": "K_DAY",
    "1m": "K_1M",
    "5m": "K_5M",
    "15m": "K_15M",
    "30m": "K_30M",
    "60m": "K_60M",
}

_SUBTYPE_BY_INTERVAL = {
    "1d": "K_DAY",
    "1m": "K_1M",
    "5m": "K_5M",
    "15m": "K_15M",
    "30m": "K_30M",
    "60m": "K_60M",
}


class FutuAdapter:
    """Futu Quote OHLCV provider。

    V1 统一使用不复权口径，不暴露 autype/session/extended_time 公共参数。
    """

    name = "futu"

    def __init__(self, *, config) -> None:
        self._config = config
        self._manager = FutuClientManager(config)

    def fetch(self, query: MarketQuery) -> MarketFetchResult:
        try:
            futu = _load_futu()
            quote_ctx = self._manager.quote_context()
            if query.mode == "latest":
                df = self._fetch_latest(quote_ctx, futu, query)
            else:
                df = self._fetch_history(quote_ctx, futu, query)
            return make_fetch_result(
                df=df,
                query=query,
                source=self.name,
                timezone=query.timezone,
            )
        except Exception as exc:
            raise ValueError(_friendly_error_message(exc)) from exc

    def _fetch_history(self, quote_ctx, futu, query: MarketQuery) -> pd.DataFrame:
        start, end = _default_window(query)
        page_req_key = None
        frames: list[pd.DataFrame] = []

        while True:
            ret, data, page_req_key = quote_ctx.request_history_kline(
                code=to_futu_code(query.normalized_symbol),
                start=start,
                end=end,
                ktype=_kl_type(futu, query.interval),
                autype=futu.AuType.NONE,
                fields=[futu.KL_FIELD.ALL],
                max_count=1000,
                page_req_key=page_req_key,
                extended_time=False,
                session=futu.Session.NONE,
            )
            df = _ensure_frame(ret, data, futu=futu, op="request_history_kline")
            if not df.empty:
                frames.append(_normalize_kline_frame(df))
            if page_req_key is None:
                break

        if not frames:
            return _empty_ohlcv_frame()

        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

        if query.interval != "1d" and query.start_dt is None and query.end_dt is None and not merged.empty:
            latest_day = merged["date"].dt.date.max()
            merged = merged[merged["date"].dt.date == latest_day].reset_index(drop=True)

        return merged

    def _fetch_latest(self, quote_ctx, futu, query: MarketQuery) -> pd.DataFrame:
        code = to_futu_code(query.normalized_symbol)
        subtype = _subtype(futu, query.interval)
        ret, data = quote_ctx.subscribe(
            [code],
            [subtype],
            subscribe_push=False,
            session=futu.Session.NONE,
        )
        if ret != futu.RET_OK:
            raise ValueError(f"Futu 行情订阅失败: {data}")

        ret, data = quote_ctx.get_cur_kline(
            code=code,
            num=1,
            ktype=_kl_type(futu, query.interval),
            autype=futu.AuType.NONE,
        )
        df = _ensure_frame(ret, data, futu=futu, op="get_cur_kline")
        return _normalize_kline_frame(df).tail(1).reset_index(drop=True)


def _default_window(query: MarketQuery) -> tuple[str | None, str | None]:
    if query.start_dt is not None or query.end_dt is not None:
        return query.start, query.end

    end_dt = datetime.now()
    lookback = timedelta(days=365) if query.interval == "1d" else timedelta(days=7)
    start_dt = end_dt - lookback
    return format_boundary(start_dt, query.interval), format_boundary(end_dt, query.interval)


def _kl_type(futu, interval: str):
    return getattr(futu.KLType, _KLTYPE_BY_INTERVAL[interval])


def _subtype(futu, interval: str):
    return getattr(futu.SubType, _SUBTYPE_BY_INTERVAL[interval])


def _normalize_kline_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_ohlcv_frame()

    df = frame.rename(
        columns={
            "time_key": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )
    normalized = df[["date", "open", "high", "low", "close", "volume"]].copy()
    normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(0)
    return normalize_frame_dates(normalized)


def _empty_ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])


def _ensure_frame(ret: int, data: Any, *, futu, op: str) -> pd.DataFrame:
    if ret != futu.RET_OK:
        raise ValueError(f"{op} 失败: {data}")
    if isinstance(data, pd.DataFrame):
        return data
    raise ValueError(f"{op} 返回了非表格数据")


def _friendly_error_message(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if any(token in lowered for token in ("opend", "无法连接", "connect", "quote")):
        return f"无法连接 Futu OpenD 行情服务: {text}"
    if any(token in lowered for token in ("登录", "login", "logined", "qot_logined")):
        return f"Futu 行情账户未登录或登录已失效: {text}"
    if any(token in lowered for token in ("权限", "额度", "quota", "permission", "not enough")):
        return f"Futu 行情权限或额度不足: {text}"
    if "订阅" in text or "subscribe" in lowered:
        return f"Futu 行情订阅失败: {text}"
    return text
