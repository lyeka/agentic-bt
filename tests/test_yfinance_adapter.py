"""
[INPUT]: pytest-bdd, unittest.mock, agent.adapters.market.yfinance
[OUTPUT]: yfinance_adapter.feature step definitions
[POS]: tests/ BDD 测试层，验证 YFinanceAdapter 列名标准化/排序/日期范围
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/yfinance_adapter.feature"


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

def _raw_yfinance_df(ascending: bool = True) -> pd.DataFrame:
    """模拟 yfinance.download 返回的原始 DataFrame（大写列名 + DatetimeIndex）"""
    dates = pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05"])
    if not ascending:
        dates = dates[::-1]
    df = pd.DataFrame({
        "Open": [150.0, 151.0, 152.0],
        "High": [155.0, 156.0, 157.0],
        "Low": [149.0, 150.0, 151.0],
        "Close": [153.0, 154.0, 155.0],
        "Volume": [1000000, 1100000, 1200000],
    }, index=dates)
    df.index.name = "Date"
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 mock yfinance 环境", target_fixture="yfctx")
def given_mock_env():
    return {"download_mock": MagicMock(return_value=_raw_yfinance_df())}


@given("yfinance 返回原始日线数据")
def given_raw_data(yfctx):
    yfctx["download_mock"].return_value = _raw_yfinance_df()


@given("yfinance 返回倒序日线数据")
def given_reverse_data(yfctx):
    yfctx["download_mock"].return_value = _raw_yfinance_df(ascending=False)


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

def _make_adapter(download_mock: MagicMock):
    """构造 YFinanceAdapter，注入 mock download"""
    from agent.adapters.market.yfinance import YFinanceAdapter
    with patch("yfinance.download", download_mock):
        adapter = YFinanceAdapter()
    return adapter


@when(parsers.parse('调用 yfinance fetch "{symbol}"'), target_fixture="yfctx")
def when_fetch(yfctx, symbol):
    adapter = _make_adapter(yfctx["download_mock"])
    with patch("yfinance.download", yfctx["download_mock"]):
        yfctx["result"] = adapter.fetch(symbol)
    return yfctx


@when(parsers.parse('调用 yfinance fetch "{symbol}" 从 "{start}" 到 "{end}"'), target_fixture="yfctx")
def when_fetch_range(yfctx, symbol, start, end):
    adapter = _make_adapter(yfctx["download_mock"])
    with patch("yfinance.download", yfctx["download_mock"]):
        yfctx["result"] = adapter.fetch(symbol, start=start, end=end)
    return yfctx


@when(parsers.parse('调用 yfinance fetch "{symbol}" 不指定日期'), target_fixture="yfctx")
def when_fetch_default(yfctx, symbol):
    adapter = _make_adapter(yfctx["download_mock"])
    with patch("yfinance.download", yfctx["download_mock"]):
        yfctx["result"] = adapter.fetch(symbol)
    return yfctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('yfinance 返回 DataFrame 包含标准列 "{cols}"'))
def then_standard_columns(yfctx, cols):
    expected = [c.strip() for c in cols.split(",")]
    assert list(yfctx["result"].columns) == expected


@then("yfinance date 列类型为 datetime")
def then_date_dtype(yfctx):
    assert pd.api.types.is_datetime64_any_dtype(yfctx["result"]["date"])


@then("yfinance 数据按 date 升序排列")
def then_ascending(yfctx):
    dates = yfctx["result"]["date"].tolist()
    assert dates == sorted(dates)


@then(parsers.parse('yfinance.download 收到 start "{start}" 和 end "{end}"'))
def then_passthrough(yfctx, start, end):
    _, kwargs = yfctx["download_mock"].call_args
    assert kwargs["start"] == start
    assert kwargs["end"] == end


@then("yfinance.download 收到的 start 距今约 365 天")
def then_default_range(yfctx):
    _, kwargs = yfctx["download_mock"].call_args
    start_dt = datetime.strptime(kwargs["start"], "%Y-%m-%d")
    delta = datetime.now() - start_dt
    assert 360 <= delta.days <= 370
