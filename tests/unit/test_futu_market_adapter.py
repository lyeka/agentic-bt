from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from athenaclaw.integrations.futu.config import FutuConfig
from athenaclaw.integrations.market.futu import FutuAdapter
from athenaclaw.tools.market.schema import build_market_query


class _FakeFutu:
    RET_OK = 0

    class KLType:
        K_DAY = "K_DAY"
        K_1M = "K_1M"
        K_5M = "K_5M"
        K_15M = "K_15M"
        K_30M = "K_30M"
        K_60M = "K_60M"

    class AuType:
        NONE = "NONE"

    class Session:
        NONE = "NONE"

    class KL_FIELD:
        ALL = "ALL"

    class SubType:
        K_DAY = "K_DAY"
        K_1M = "K_1M"
        K_5M = "K_5M"
        K_15M = "K_15M"
        K_30M = "K_30M"
        K_60M = "K_60M"


@dataclass
class _FakeManager:
    quote: object

    def quote_context(self):
        return self.quote


class _FakeQuoteContext:
    def __init__(self) -> None:
        self.history_responses: list[tuple[int, object, object]] = []
        self.latest_response: tuple[int, object] = (_FakeFutu.RET_OK, pd.DataFrame())
        self.subscribe_response: tuple[int, object] = (_FakeFutu.RET_OK, "ok")
        self.history_calls: list[dict] = []
        self.latest_calls: list[dict] = []
        self.subscribe_calls: list[dict] = []

    def request_history_kline(self, **kwargs):
        self.history_calls.append(kwargs)
        return self.history_responses.pop(0)

    def subscribe(self, code_list, subtype_list, **kwargs):
        self.subscribe_calls.append(
            {
                "code_list": list(code_list),
                "subtype_list": list(subtype_list),
                **kwargs,
            }
        )
        return self.subscribe_response

    def get_cur_kline(self, **kwargs):
        self.latest_calls.append(kwargs)
        return self.latest_response


def _make_adapter(monkeypatch, quote_ctx: _FakeQuoteContext) -> FutuAdapter:
    monkeypatch.setattr("athenaclaw.integrations.market.futu._load_futu", lambda: _FakeFutu)
    adapter = FutuAdapter(config=FutuConfig())
    adapter._manager = _FakeManager(quote=quote_ctx)  # type: ignore[assignment]
    return adapter


def test_futu_history_paginates_and_normalizes(monkeypatch):
    quote_ctx = _FakeQuoteContext()
    quote_ctx.history_responses = [
        (
            _FakeFutu.RET_OK,
            pd.DataFrame(
                {
                    "time_key": ["2024-01-04", "2024-01-03"],
                    "open": [11.0, 10.0],
                    "high": [12.0, 11.0],
                    "low": [10.5, 9.5],
                    "close": [11.5, 10.5],
                    "volume": [1100, 1000],
                }
            ),
            "next-page",
        ),
        (
            _FakeFutu.RET_OK,
            pd.DataFrame(
                {
                    "time_key": ["2024-01-02"],
                    "open": [9.0],
                    "high": [10.0],
                    "low": [8.5],
                    "close": [9.5],
                    "volume": [900],
                }
            ),
            None,
        ),
    ]
    adapter = _make_adapter(monkeypatch, quote_ctx)

    result = adapter.fetch(
        build_market_query(
            symbol="AAPL",
            interval="1d",
            mode="history",
            start="2024-01-02",
            end="2024-01-04",
        )
    )

    assert list(result.df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert result.source == "futu"
    assert result.timezone == "America/New_York"
    assert result.df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert quote_ctx.history_calls[0]["page_req_key"] is None
    assert quote_ctx.history_calls[1]["page_req_key"] == "next-page"
    assert quote_ctx.history_calls[0]["autype"] == _FakeFutu.AuType.NONE
    assert quote_ctx.history_calls[0]["session"] == _FakeFutu.Session.NONE


def test_futu_latest_auto_subscribes_and_returns_one_row(monkeypatch):
    quote_ctx = _FakeQuoteContext()
    quote_ctx.latest_response = (
        _FakeFutu.RET_OK,
        pd.DataFrame(
            {
                "time_key": ["2024-01-02 09:31:00", "2024-01-02 09:32:00"],
                "open": [10.0, 10.1],
                "high": [10.2, 10.3],
                "low": [9.9, 10.0],
                "close": [10.1, 10.2],
                "volume": [1000, 1100],
            }
        ),
    )
    adapter = _make_adapter(monkeypatch, quote_ctx)

    result = adapter.fetch(build_market_query(symbol="AAPL", interval="1m", mode="latest"))

    assert len(result.df) == 1
    assert result.df.iloc[0]["close"] == 10.2
    assert quote_ctx.subscribe_calls == [
        {
            "code_list": ["US.AAPL"],
            "subtype_list": [_FakeFutu.SubType.K_1M],
            "subscribe_push": False,
            "session": _FakeFutu.Session.NONE,
        }
    ]
    assert quote_ctx.latest_calls[0]["code"] == "US.AAPL"
    assert quote_ctx.latest_calls[0]["num"] == 1
    assert quote_ctx.latest_calls[0]["ktype"] == _FakeFutu.KLType.K_1M
    assert quote_ctx.latest_calls[0]["autype"] == _FakeFutu.AuType.NONE


def test_futu_intraday_history_without_window_keeps_latest_trading_day(monkeypatch):
    quote_ctx = _FakeQuoteContext()
    quote_ctx.history_responses = [
        (
            _FakeFutu.RET_OK,
            pd.DataFrame(
                {
                    "time_key": [
                        "2024-01-02 15:59:00",
                        "2024-01-03 09:31:00",
                        "2024-01-03 09:32:00",
                    ],
                    "open": [9.9, 10.0, 10.1],
                    "high": [10.0, 10.2, 10.3],
                    "low": [9.8, 9.9, 10.0],
                    "close": [9.95, 10.1, 10.2],
                    "volume": [900, 1000, 1100],
                }
            ),
            None,
        )
    ]
    adapter = _make_adapter(monkeypatch, quote_ctx)

    result = adapter.fetch(build_market_query(symbol="00700.HK", interval="1m", mode="history"))

    assert result.timezone == "Asia/Hong_Kong"
    assert result.df["date"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist() == [
        "2024-01-03 09:31:00",
        "2024-01-03 09:32:00",
    ]


def test_futu_history_permission_error_is_translated(monkeypatch):
    quote_ctx = _FakeQuoteContext()
    quote_ctx.history_responses = [
        (
            1,
            "没有权限或者额度不足",
            None,
        )
    ]
    adapter = _make_adapter(monkeypatch, quote_ctx)

    with pytest.raises(ValueError, match="Futu 行情权限或额度不足"):
        adapter.fetch(build_market_query(symbol="AAPL", interval="1d", mode="history"))


def test_market_query_uses_hk_timezone():
    query = build_market_query(symbol="00700.HK", interval="1m", mode="history")
    assert query.timezone == "Asia/Hong_Kong"
