"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.finnhub
[OUTPUT]: finnhub_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 FinnhubAdapter 日线行为与分钟拒绝逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import calendar
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agent.adapters.market.schema import build_market_query


FEATURE = "features/finnhub_adapter.feature"


@scenario(FEATURE, "日线 history 返回标准列")
def test_daily_columns(): pass


@scenario(FEATURE, "date 列为 datetime 类型")
def test_date_dtype(): pass


@scenario(FEATURE, "数据按日期升序排列")
def test_date_ascending(): pass


@scenario(FEATURE, "指定日期范围透传")
def test_date_range_passthrough(): pass


@scenario(FEATURE, "默认拉取最近一年")
def test_default_date_range(): pass


@scenario(FEATURE, "分钟与 latest 模式显式拒绝")
def test_reject_minute_latest(): pass


def _raw_finnhub_response(ascending: bool = True) -> dict:
    timestamps = [1704240000, 1704326400, 1704412800]
    if not ascending:
        timestamps = list(reversed(timestamps))
    return {
        "c": [153.0, 154.0, 155.0],
        "h": [155.0, 156.0, 157.0],
        "l": [149.0, 150.0, 151.0],
        "o": [150.0, 151.0, 152.0],
        "v": [1000000, 1100000, 1200000],
        "t": timestamps,
        "s": "ok",
    }


@given("一个 mock finnhub 环境", target_fixture="fhctx")
def given_mock_env():
    mock_client = MagicMock()
    mock_client.stock_candles.return_value = _raw_finnhub_response()
    return {"mock_client": mock_client}


@given("finnhub 返回原始 candle 数据")
def given_raw_data(fhctx):
    fhctx["mock_client"].stock_candles.return_value = _raw_finnhub_response()


@given("finnhub 返回倒序 candle 数据")
def given_reverse_data(fhctx):
    fhctx["mock_client"].stock_candles.return_value = _raw_finnhub_response(ascending=False)


def _make_adapter(mock_client: MagicMock):
    with patch("finnhub.Client", return_value=mock_client):
        from agent.adapters.market.finnhub import FinnhubAdapter

        return FinnhubAdapter(api_key="mock_key")


@when(parsers.parse('调用 finnhub fetch history "{symbol}"'), target_fixture="fhctx")
def when_fetch(fhctx, symbol):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(build_market_query(symbol=symbol, interval="1d", mode="history"))
    return fhctx


@when(parsers.parse('调用 finnhub fetch history "{symbol}" 从 "{start}" 到 "{end}"'), target_fixture="fhctx")
def when_fetch_range(fhctx, symbol, start, end):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(
        build_market_query(symbol=symbol, interval="1d", mode="history", start=start, end=end)
    )
    return fhctx


@when(parsers.parse('调用 finnhub fetch history "{symbol}" 不指定日期'), target_fixture="fhctx")
def when_fetch_default(fhctx, symbol):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(build_market_query(symbol=symbol, interval="1d", mode="history"))
    return fhctx


@when(parsers.parse('调用 finnhub fetch latest "{symbol}" interval "{interval}"'), target_fixture="fhctx")
def when_fetch_reject(fhctx, symbol, interval):
    adapter = _make_adapter(fhctx["mock_client"])
    try:
        adapter.fetch(build_market_query(symbol=symbol, interval=interval, mode="latest"))
        fhctx["error"] = None
    except Exception as exc:
        fhctx["error"] = exc
    return fhctx


@then(parsers.parse('finnhub 返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(fhctx, cols):
    expected = [column.strip() for column in cols.split(",")]
    assert list(fhctx["result"].df.columns) == expected


@then("finnhub date 列类型为 datetime")
def then_date_dtype(fhctx):
    assert pd.api.types.is_datetime64_any_dtype(fhctx["result"].df["date"])


@then("finnhub 数据按 date 升序排列")
def then_ascending(fhctx):
    dates = fhctx["result"].df["date"].tolist()
    assert dates == sorted(dates)


@then("finnhub client 收到正确的 UNIX 时间戳范围")
def then_passthrough(fhctx):
    args, _ = fhctx["mock_client"].stock_candles.call_args
    expected_from = int(calendar.timegm(datetime(2024, 1, 1).timetuple()))
    expected_to = int(calendar.timegm(datetime(2024, 6, 1).timetuple()))
    assert args[2] == expected_from
    assert args[3] == expected_to


@then("finnhub client 收到的 from_ 距今约 365 天")
def then_default_range(fhctx):
    args, _ = fhctx["mock_client"].stock_candles.call_args
    from_dt = datetime.fromtimestamp(args[2], tz=None)
    delta = datetime.now() - from_dt
    assert 360 <= delta.days <= 370


@then(parsers.parse('返回错误包含 "{text}"'))
def then_error_contains(fhctx, text):
    assert text in str(fhctx["error"])
