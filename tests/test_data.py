"""
[INPUT]: pytest-bdd, agenticbt.data
[OUTPUT]: data.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 make_sample_data 多行情模式
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.data import make_sample_data


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/data.feature", "默认 regime 与现有行为一致")
def test_default_regime(): pass

@scenario("features/data.feature", "trending 行情具有明显上升趋势")
def test_trending(): pass

@scenario("features/data.feature", "mean_reverting 行情零漂移高波动")
def test_mean_reverting(): pass

@scenario("features/data.feature", "volatile 行情极高波动")
def test_volatile(): pass

@scenario("features/data.feature", "bull_bear 行情前半段涨后半段跌")
def test_bull_bear(): pass

@scenario("features/data.feature", "未知 regime 抛出异常")
def test_unknown_regime(): pass

@scenario("features/data.feature", "regime 参数不影响 random 的向后兼容")
def test_backward_compat(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse('regime 为 "{regime}"'), target_fixture="dctx")
def given_regime(regime):
    return {"regime": regime}


@when("生成 60 根 bar 的模拟数据", target_fixture="dctx")
def when_gen_60(dctx):
    dctx["df"] = make_sample_data(periods=60, regime=dctx["regime"])
    return dctx


@when("生成 100 根 bar 的模拟数据", target_fixture="dctx")
def when_gen_100(dctx):
    dctx["df"] = make_sample_data(periods=100, regime=dctx["regime"])
    return dctx


@when("生成 252 根 bar 的模拟数据", target_fixture="dctx")
def when_gen_252(dctx):
    dctx["df"] = make_sample_data(periods=252, regime=dctx["regime"])
    return dctx


@when("尝试生成数据", target_fixture="dctx")
def when_try_gen(dctx):
    try:
        make_sample_data(regime=dctx["regime"])
        dctx["error"] = None
    except ValueError as e:
        dctx["error"] = e
    return dctx


@when("不传 regime 参数生成数据", target_fixture="dctx")
def when_no_regime():
    return {"df_default": make_sample_data(seed=42)}


@when("传 regime=\"random\" 生成数据", target_fixture="dctx")
def when_random_regime(dctx):
    dctx["df_explicit"] = make_sample_data(seed=42, regime="random")
    return dctx


# ── Then ─────────────────────────────────────────────────────────────────────

@then("应返回 60 行 OHLCV DataFrame")
def then_60_rows(dctx):
    assert len(dctx["df"]) == 60


@then("所有价格应为正数")
def then_positive_prices(dctx):
    df = dctx["df"]
    for col in ["open", "high", "low", "close"]:
        assert (df[col] > 0).all(), f"{col} 列存在非正数"


@then("最后 10 根 bar 的均价应高于前 10 根 bar 的均价")
def then_trending_up(dctx):
    df = dctx["df"]
    first_avg = df["close"].iloc[:10].mean()
    last_avg = df["close"].iloc[-10:].mean()
    assert last_avg > first_avg, f"last={last_avg:.2f} <= first={first_avg:.2f}"


@then("收盘价标准差应大于 trending 行情")
def then_higher_vol(dctx):
    df_mr = dctx["df"]
    df_trend = make_sample_data(periods=252, regime="trending", seed=42)
    std_mr = df_mr["close"].pct_change().dropna().std()
    std_trend = df_trend["close"].pct_change().dropna().std()
    assert std_mr > std_trend, f"mean_reverting std={std_mr:.4f} <= trending std={std_trend:.4f}"


@then("日收益率标准差应大于 0.02")
def then_volatile(dctx):
    returns = dctx["df"]["close"].pct_change().dropna()
    assert returns.std() > 0.02, f"std={returns.std():.4f}"


@then("前半段均价应低于中间价")
def then_bull_phase(dctx):
    df = dctx["df"]
    mid = len(df) // 2
    first_avg = df["close"].iloc[:mid // 2].mean()
    peak_avg = df["close"].iloc[mid - 5:mid + 5].mean()
    assert first_avg < peak_avg, f"first={first_avg:.2f} >= peak={peak_avg:.2f}"


@then("后半段均价应低于中间价")
def then_bear_phase(dctx):
    df = dctx["df"]
    mid = len(df) // 2
    last_avg = df["close"].iloc[-10:].mean()
    peak_avg = df["close"].iloc[mid - 5:mid + 5].mean()
    assert last_avg < peak_avg, f"last={last_avg:.2f} >= peak={peak_avg:.2f}"


@then("应抛出 ValueError")
def then_value_error(dctx):
    assert dctx["error"] is not None
    assert isinstance(dctx["error"], ValueError)


@then("两次结果应完全一致")
def then_identical(dctx):
    import pandas as pd
    pd.testing.assert_frame_equal(dctx["df_default"], dctx["df_explicit"])
