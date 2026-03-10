"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.finnhub
[OUTPUT]: finnhub_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 FinnhubAdapter 列名标准化/排序/日期范围/UNIX 转换
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/finnhub_adapter.feature"


@scenario(FEATURE, "列名标准化")
def test_column_normalize(): pass


@scenario(FEATURE, "date 列为 datetime 类型")
def test_date_dtype(): pass


@scenario(FEATURE, "数据按日期升序排列")
def test_date_ascending(): pass


@scenario(FEATURE, "指定日期范围透传")
def test_date_range_passthrough(): pass


@scenario(FEATURE, "默认拉取最近一年")
def test_default_date_range(): pass


# ─────────────────────────────────────────────────────────────────────────────
# 测试数据
# ─────────────────────────────────────────────────────────────────────────────

def _raw_finnhub_response(ascending: bool = True) -> dict:
    """模拟 finnhub stock_candles 返回的原始 dict"""
    timestamps = [1704240000, 1704326400, 1704412800]  # 2024-01-03, 04, 05 UTC
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


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

def _make_adapter(mock_client: MagicMock):
    """构造 FinnhubAdapter，注入 mock client 绕过真实 API Key"""
    with patch("finnhub.Client", return_value=mock_client):
        from agent.adapters.market.finnhub import FinnhubAdapter
        return FinnhubAdapter(api_key="mock_key")


@when(parsers.parse('调用 finnhub fetch "{symbol}"'), target_fixture="fhctx")
def when_fetch(fhctx, symbol):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(symbol)
    return fhctx


@when(parsers.parse('调用 finnhub fetch "{symbol}" 从 "{start}" 到 "{end}"'), target_fixture="fhctx")
def when_fetch_range(fhctx, symbol, start, end):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(symbol, start=start, end=end)
    return fhctx


@when(parsers.parse('调用 finnhub fetch "{symbol}" 不指定日期'), target_fixture="fhctx")
def when_fetch_default(fhctx, symbol):
    adapter = _make_adapter(fhctx["mock_client"])
    fhctx["result"] = adapter.fetch(symbol)
    return fhctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('finnhub 返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(fhctx, cols):
    expected = [c.strip() for c in cols.split(",")]
    assert list(fhctx["result"].columns) == expected


@then("finnhub date 列类型为 datetime")
def then_date_dtype(fhctx):
    assert pd.api.types.is_datetime64_any_dtype(fhctx["result"]["date"])


@then("finnhub 数据按 date 升序排列")
def then_ascending(fhctx):
    dates = fhctx["result"]["date"].tolist()
    assert dates == sorted(dates)


@then("finnhub client 收到正确的 UNIX 时间戳范围")
def then_passthrough(fhctx):
    args, _ = fhctx["mock_client"].stock_candles.call_args
    # stock_candles(symbol, resolution, from_, to_)
    from_ = args[2]
    to_ = args[3]
    # 2024-01-01 → 1704067200, 2024-06-01 → 1717200000
    expected_from = int(calendar.timegm(datetime(2024, 1, 1).timetuple()))
    expected_to = int(calendar.timegm(datetime(2024, 6, 1).timetuple()))
    assert from_ == expected_from
    assert to_ == expected_to


@then("finnhub client 收到的 from_ 距今约 365 天")
def then_default_range(fhctx):
    args, _ = fhctx["mock_client"].stock_candles.call_args
    from_ts = args[2]
    from_dt = datetime.fromtimestamp(from_ts, tz=None)
    delta = datetime.now() - from_dt
    assert 360 <= delta.days <= 370
