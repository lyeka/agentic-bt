"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.tushare
[OUTPUT]: tushare_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 TushareAdapter 列名标准化/排序/日期范围
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/tushare_adapter.feature"


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

def _raw_tushare_df(ascending: bool = False) -> pd.DataFrame:
    """模拟 tushare pro.daily 返回的原始 DataFrame"""
    dates = ["20240105", "20240104", "20240103"]
    if ascending:
        dates = list(reversed(dates))
    return pd.DataFrame({
        "ts_code": ["000001.SZ"] * 3,
        "trade_date": dates,
        "open": [10.0, 11.0, 12.0],
        "high": [11.0, 12.0, 13.0],
        "low": [9.5, 10.5, 11.5],
        "close": [10.5, 11.5, 12.5],
        "vol": [1000.0, 1100.0, 1200.0],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 mock tushare 环境", target_fixture="tsctx")
def given_mock_env():
    mock_api = MagicMock()
    mock_api.daily.return_value = _raw_tushare_df()
    return {"mock_api": mock_api, "calls": mock_api.daily}


@given("tushare 返回原始日线数据")
def given_raw_data(tsctx):
    tsctx["mock_api"].daily.return_value = _raw_tushare_df()


@given("tushare 返回倒序日线数据")
def given_reverse_data(tsctx):
    tsctx["mock_api"].daily.return_value = _raw_tushare_df(ascending=False)


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

def _make_adapter(mock_api: MagicMock) -> object:
    """构造 TushareAdapter，注入 mock API 绕过真实 token"""
    from agent.adapters.market.tushare import TushareAdapter
    with patch("tushare.pro_api", return_value=mock_api):
        return TushareAdapter(token="mock_token")


@when(parsers.parse('调用 fetch "{symbol}"'), target_fixture="tsctx")
def when_fetch(tsctx, symbol):
    adapter = _make_adapter(tsctx["mock_api"])
    tsctx["result"] = adapter.fetch(symbol)
    return tsctx


@when(parsers.parse('调用 fetch "{symbol}" 从 "{start}" 到 "{end}"'), target_fixture="tsctx")
def when_fetch_range(tsctx, symbol, start, end):
    adapter = _make_adapter(tsctx["mock_api"])
    tsctx["result"] = adapter.fetch(symbol, start=start, end=end)
    return tsctx


@when(parsers.parse('调用 fetch "{symbol}" 不指定日期'), target_fixture="tsctx")
def when_fetch_default(tsctx, symbol):
    adapter = _make_adapter(tsctx["mock_api"])
    tsctx["result"] = adapter.fetch(symbol)
    return tsctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(tsctx, cols):
    expected = [c.strip() for c in cols.split(",")]
    assert list(tsctx["result"].columns) == expected


@then("date 列类型为 datetime")
def then_date_dtype(tsctx):
    assert pd.api.types.is_datetime64_any_dtype(tsctx["result"]["date"])


@then("数据按 date 升序排列")
def then_ascending(tsctx):
    dates = tsctx["result"]["date"].tolist()
    assert dates == sorted(dates)


@then(parsers.parse('tushare 收到 start_date "{start}" 和 end_date "{end}"'))
def then_passthrough(tsctx, start, end):
    _, kwargs = tsctx["calls"].call_args
    assert kwargs["start_date"] == start
    assert kwargs["end_date"] == end


@then("tushare 收到的 start_date 距今约 365 天")
def then_default_range(tsctx):
    _, kwargs = tsctx["calls"].call_args
    start_dt = datetime.strptime(kwargs["start_date"], "%Y%m%d")
    delta = datetime.now() - start_dt
    assert 360 <= delta.days <= 370
