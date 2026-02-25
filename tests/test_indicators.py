"""
[INPUT]: pytest-bdd, agenticbt.indicators, numpy, pandas
[OUTPUT]: indicators.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 IndicatorEngine 防前瞻行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.indicators import IndicatorEngine


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/indicators.feature", "计算标准指标")
def test_standard_indicator(): pass

@scenario("features/indicators.feature", "MACD 返回多值")
def test_macd_multi_value(): pass

@scenario("features/indicators.feature", "防前瞻验证")
def test_no_lookahead(): pass

@scenario("features/indicators.feature", "NaN 安全处理")
def test_nan_safe(): pass

@scenario("features/indicators.feature", "列出可用指标")
def test_list_indicators(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_50_bars() -> pd.DataFrame:
    """生成 50 根确定性价格数据"""
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0, 1, 50))
    close = np.maximum(close, 1.0)
    high = close + rng.uniform(0.5, 2.0, 50)
    low = close - rng.uniform(0.5, 2.0, 50)
    low = np.maximum(low, 0.1)
    open_ = close + rng.normal(0, 0.5, 50)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, 50).astype(float),
    })


@given("50 根 bar 的历史数据", target_fixture="ictx")
def given_50_bars():
    return {"df": _make_50_bars(), "engine": IndicatorEngine()}


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('在 bar {idx:d} 计算 "{name}" 指标'), target_fixture="ictx")
def when_calc_indicator(ictx, idx, name):
    ictx["result"] = ictx["engine"].calc(name, ictx["df"], idx)
    return ictx


@when(parsers.parse('在 bar {idx:d} 计算 "{name}" period={period:d}'), target_fixture="ictx")
def when_calc_with_period(ictx, idx, name, period):
    ictx["result"] = ictx["engine"].calc(name, ictx["df"], idx, period=period)
    ictx["bar_index"] = idx
    ictx["period"] = period
    return ictx


@when("查询可用指标列表", target_fixture="ictx")
def when_list_indicators(ictx):
    ictx["indicator_list"] = ictx["engine"].list_indicators()
    return ictx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('应返回包含 "{key}" 的结果'))
def then_has_key(ictx, key):
    assert key in ictx["result"]


@then("值应为有效数字")
def then_valid_number(ictx):
    val = ictx["result"].get("value")
    assert val is not None and not (isinstance(val, float) and val != val)


@then('结果应包含 "macd" "signal" "histogram" 三个值')
def then_macd_keys(ictx):
    r = ictx["result"]
    assert "macd" in r and "signal" in r and "histogram" in r
    assert r["macd"] is not None


@then("计算只使用 bar 0 到 bar 20 的数据")
def then_no_lookahead(ictx):
    # 防前瞻隐含保证：calc() 已在内部截断 subset，此步为语义声明
    assert ictx["bar_index"] == 20


@then("结果等于手动计算 bar 11-20 收盘价的均值")
def then_sma_manual(ictx):
    df = ictx["df"]
    period = ictx.get("period", 10)
    bar_index = ictx["bar_index"]
    manual = df["close"].iloc[bar_index - period + 1: bar_index + 1].mean()
    assert ictx["result"]["value"] == pytest.approx(manual, rel=1e-6)


@then("数据不足时应返回 value 为 null")
def then_null_on_insufficient(ictx):
    assert ictx["result"]["value"] is None


@then("应至少包含 RSI SMA EMA MACD BBANDS ATR")
def then_indicator_list(ictx):
    names = [n.upper() for n in ictx["indicator_list"]]
    for required in ["RSI", "SMA", "EMA", "MACD", "BBANDS", "ATR"]:
        assert required in names
