"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.tushare
[OUTPUT]: tushare_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 TushareAdapter 日线/分钟/latest 行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agent.adapters.market.schema import build_market_query


FEATURE = "features/tushare_adapter.feature"


@scenario(FEATURE, "日线 history 返回标准列")
def test_daily_columns(): pass


@scenario(FEATURE, "分钟 history 使用 stk_mins")
def test_intraday_history(): pass


@scenario(FEATURE, "最新 bar 使用 rt_min_daily 且只返回一行")
def test_latest_row(): pass


@scenario(FEATURE, "数据按 date 升序排列")
def test_intraday_sorted(): pass


@scenario(FEATURE, "分钟接口权限不足时返回清晰错误")
def test_permission_error(): pass


@scenario(FEATURE, "上交所 .SS 会归一化为 .SH")
def test_symbol_normalized(): pass


def _raw_daily_df() -> pd.DataFrame:
    return pd.DataFrame({
        "ts_code": ["000001.SZ"] * 3,
        "trade_date": ["20240105", "20240104", "20240103"],
        "open": [10.0, 11.0, 12.0],
        "high": [11.0, 12.0, 13.0],
        "low": [9.5, 10.5, 11.5],
        "close": [10.5, 11.5, 12.5],
        "vol": [1000.0, 1100.0, 1200.0],
    })


def _raw_minute_df(ascending: bool = True) -> pd.DataFrame:
    times = [
        "2024-01-02 09:33:00",
        "2024-01-02 09:32:00",
        "2024-01-02 09:31:00",
    ]
    if ascending:
        times = list(reversed(times))
    return pd.DataFrame({
        "ts_code": ["000001.SZ"] * 3,
        "trade_time": times,
        "open": [10.0, 10.1, 10.2],
        "high": [10.2, 10.3, 10.4],
        "low": [9.9, 10.0, 10.1],
        "close": [10.1, 10.2, 10.3],
        "vol": [1000.0, 1100.0, 1200.0],
    })


def _raw_latest_df() -> pd.DataFrame:
    return pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ"],
        "date": ["2024-01-02", "2024-01-02"],
        "time": ["09:31:00", "09:32:00"],
        "open": [10.0, 10.1],
        "high": [10.2, 10.3],
        "low": [9.9, 10.0],
        "close": [10.1, 10.2],
        "vol": [1000.0, 1100.0],
    })


@given("一个 mock tushare 环境", target_fixture="tsctx")
def given_mock_env():
    mock_api = MagicMock()
    mock_api.daily.return_value = _raw_daily_df()
    mock_api.stk_mins.return_value = _raw_minute_df()
    mock_api.rt_min_daily.return_value = _raw_latest_df()
    return {"mock_api": mock_api}


@given("tushare 返回原始日线数据")
def given_daily_data(tsctx):
    tsctx["mock_api"].daily.return_value = _raw_daily_df()


@given("tushare 返回原始分钟数据")
def given_minute_data(tsctx):
    tsctx["mock_api"].stk_mins.return_value = _raw_minute_df()


@given("tushare 返回原始实时分钟数据")
def given_latest_data(tsctx):
    tsctx["mock_api"].rt_min_daily.return_value = _raw_latest_df()


@given("tushare 返回倒序分钟数据")
def given_reverse_minute(tsctx):
    tsctx["mock_api"].stk_mins.return_value = _raw_minute_df(ascending=False)


@given("tushare 分钟接口无权限")
def given_permission_denied(tsctx):
    tsctx["mock_api"].stk_mins.side_effect = Exception("抱歉，您没有访问权限")


def _make_adapter(mock_api: MagicMock):
    from agent.adapters.market.tushare import TushareAdapter

    with patch("tushare.pro_api", return_value=mock_api):
        return TushareAdapter(token="mock_token")


@when(parsers.parse('调用 tushare fetch history "{symbol}" interval "{interval}"'), target_fixture="tsctx")
def when_fetch_history(tsctx, symbol, interval):
    adapter = _make_adapter(tsctx["mock_api"])
    try:
        tsctx["result"] = adapter.fetch(build_market_query(symbol=symbol, interval=interval, mode="history"))
        tsctx["error"] = None
    except Exception as exc:
        tsctx["result"] = None
        tsctx["error"] = exc
    return tsctx


@when(parsers.parse('调用 tushare fetch latest "{symbol}" interval "{interval}"'), target_fixture="tsctx")
def when_fetch_latest(tsctx, symbol, interval):
    adapter = _make_adapter(tsctx["mock_api"])
    tsctx["result"] = adapter.fetch(build_market_query(symbol=symbol, interval=interval, mode="latest"))
    return tsctx


@then(parsers.parse('返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(tsctx, cols):
    expected = [column.strip() for column in cols.split(",")]
    assert list(tsctx["result"].df.columns) == expected


@then("date 列类型为 datetime")
def then_date_dtype(tsctx):
    assert pd.api.types.is_datetime64_any_dtype(tsctx["result"].df["date"])


@then("数据按 date 升序排列")
def then_ascending(tsctx):
    dates = tsctx["result"].df["date"].tolist()
    assert dates == sorted(dates)


@then(parsers.parse('tushare stk_mins 收到 freq "{freq}"'))
def then_minute_freq(tsctx, freq):
    kwargs = tsctx["mock_api"].stk_mins.call_args.kwargs
    assert kwargs["freq"] == freq


@then(parsers.parse('tushare rt_min_daily 收到 freq "{freq}"'))
def then_latest_freq(tsctx, freq):
    kwargs = tsctx["mock_api"].rt_min_daily.call_args.kwargs
    assert kwargs["freq"] == freq


@then("返回 1 行数据")
def then_one_row(tsctx):
    assert len(tsctx["result"].df) == 1


@then(parsers.parse('返回错误包含 "{text}"'))
def then_error_contains(tsctx, text):
    assert text in str(tsctx["error"])


@then(parsers.parse('tushare daily 收到 ts_code "{symbol}"'))
def then_ts_code(tsctx, symbol):
    kwargs = tsctx["mock_api"].daily.call_args.kwargs
    assert kwargs["ts_code"] == symbol
