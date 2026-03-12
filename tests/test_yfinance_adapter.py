"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.yfinance
[OUTPUT]: yfinance_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 YFinanceAdapter 日线/分钟/latest 行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agent.adapters.market.schema import build_market_query


FEATURE = "features/yfinance_adapter.feature"


@scenario(FEATURE, "日线 history 返回标准列")
def test_daily_columns(): pass


@scenario(FEATURE, "分钟 history 返回 datetime 且按时间升序")
def test_intraday_history(): pass


@scenario(FEATURE, "latest 模式只返回一行")
def test_latest_row(): pass


@scenario(FEATURE, "上海代码自动转换为 Yahoo 代码")
def test_shanghai_symbol_mapping(): pass


@scenario(FEATURE, "指定分钟范围透传到 yfinance")
def test_range_passthrough(): pass


def _raw_daily_df() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05"])
    df = pd.DataFrame({
        "Open": [150.0, 151.0, 152.0],
        "High": [155.0, 156.0, 157.0],
        "Low": [149.0, 150.0, 151.0],
        "Close": [153.0, 154.0, 155.0],
        "Volume": [1000000, 1100000, 1200000],
    }, index=dates)
    df.index.name = "Date"
    return df


def _raw_minute_df(ascending: bool = True) -> pd.DataFrame:
    dates = pd.to_datetime([
        "2024-01-02 09:31:00",
        "2024-01-02 09:32:00",
        "2024-01-02 09:33:00",
    ]).tz_localize("Asia/Shanghai")
    if not ascending:
        dates = dates[::-1]
    df = pd.DataFrame({
        "Open": [10.0, 10.1, 10.2],
        "High": [10.2, 10.3, 10.4],
        "Low": [9.9, 10.0, 10.1],
        "Close": [10.1, 10.2, 10.3],
        "Volume": [1000, 1100, 1200],
    }, index=dates)
    df.index.name = "Datetime"
    return df


@given("一个 mock yfinance 环境", target_fixture="yfctx")
def given_mock_env():
    ticker = MagicMock()
    ticker.history.return_value = _raw_daily_df()
    ticker_ctor = MagicMock(return_value=ticker)
    return {"ticker": ticker, "ticker_ctor": ticker_ctor}


@given("yfinance 返回原始日线数据")
def given_daily_data(yfctx):
    yfctx["ticker"].history.return_value = _raw_daily_df()


@given("yfinance 返回原始分钟数据")
def given_minute_data(yfctx):
    yfctx["ticker"].history.return_value = _raw_minute_df()


def _fetch(yfctx, *, symbol: str, interval: str, mode: str, start: str | None = None, end: str | None = None):
    from agent.adapters.market.yfinance import YFinanceAdapter

    with patch("yfinance.Ticker", yfctx["ticker_ctor"]):
        adapter = YFinanceAdapter()
        return adapter.fetch(build_market_query(
            symbol=symbol,
            interval=interval,
            mode=mode,
            start=start,
            end=end,
        ))


@when(parsers.parse('调用 yfinance fetch history "{symbol}" interval "{interval}"'), target_fixture="yfctx")
def when_fetch_history(yfctx, symbol, interval):
    yfctx["result"] = _fetch(yfctx, symbol=symbol, interval=interval, mode="history")
    return yfctx


@when(parsers.parse('调用 yfinance fetch latest "{symbol}" interval "{interval}"'), target_fixture="yfctx")
def when_fetch_latest(yfctx, symbol, interval):
    yfctx["result"] = _fetch(yfctx, symbol=symbol, interval=interval, mode="latest")
    return yfctx


@when(parsers.parse('调用 yfinance fetch history "{symbol}" interval "{interval}" 从 "{start}" 到 "{end}"'), target_fixture="yfctx")
def when_fetch_range(yfctx, symbol, interval, start, end):
    yfctx["result"] = _fetch(yfctx, symbol=symbol, interval=interval, mode="history", start=start, end=end)
    return yfctx


@then(parsers.parse('yfinance 返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(yfctx, cols):
    expected = [column.strip() for column in cols.split(",")]
    assert list(yfctx["result"].df.columns) == expected


@then("yfinance date 列类型为 datetime")
def then_date_dtype(yfctx):
    assert pd.api.types.is_datetime64_any_dtype(yfctx["result"].df["date"])


@then("yfinance 数据按 date 升序排列")
def then_ascending(yfctx):
    dates = yfctx["result"].df["date"].tolist()
    assert dates == sorted(dates)


@then("yfinance 返回 1 行数据")
def then_one_row(yfctx):
    assert len(yfctx["result"].df) == 1


@then(parsers.parse('yfinance Ticker 收到 symbol "{symbol}"'))
def then_ticker_symbol(yfctx, symbol):
    assert yfctx["ticker_ctor"].call_args.args[0] == symbol


@then(parsers.parse('yfinance history 收到 start "{start}" 和 end "{end}"'))
def then_passthrough(yfctx, start, end):
    kwargs = yfctx["ticker"].history.call_args.kwargs
    assert kwargs["start"] == start
    assert kwargs["end"] == end
