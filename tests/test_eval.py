"""
[INPUT]: pytest-bdd, agenticbt.eval, agenticbt.models
[OUTPUT]: eval.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 Evaluator 绩效与遵循度计算
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from datetime import datetime

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.eval import Evaluator
from agenticbt.models import Decision


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/eval.feature", "盈利回测的绩效指标")
def test_profitable(): pass

@scenario("features/eval.feature", "无交易的绩效")
def test_no_trade(): pass

@scenario("features/eval.feature", "遵循度报告统计")
def test_compliance(): pass

@scenario("features/eval.feature", "Sortino 比率计算")
def test_sortino(): pass

@scenario("features/eval.feature", "最大回撤持续时间")
def test_max_dd_duration(): pass

@scenario("features/eval.feature", "交易统计指标")
def test_trade_stats(): pass

@scenario("features/eval.feature", "年化波动率")
def test_volatility(): pass

@scenario("features/eval.feature", "CAGR 年化收益")
def test_cagr(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("权益曲线 [100000, 102000, 101000, 105000]", target_fixture="ectx")
def given_equity_curve():
    return {"equity": [100000.0, 102000.0, 101000.0, 105000.0], "trade_log": []}


@given("权益曲线 [100000, 100000, 100000]", target_fixture="ectx")
def given_flat_equity():
    return {"equity": [100000.0, 100000.0, 100000.0], "trade_log": []}


@given("权益曲线 [100000, 102000, 99000, 101000, 105000]", target_fixture="ectx")
def given_volatile_equity():
    return {"equity": [100000.0, 102000.0, 99000.0, 101000.0, 105000.0], "trade_log": []}


@given("权益曲线 [100000, 95000, 93000, 96000, 100000, 102000]", target_fixture="ectx")
def given_drawdown_equity():
    return {"equity": [100000.0, 95000.0, 93000.0, 96000.0, 100000.0, 102000.0], "trade_log": []}


@given("交易记录 [{\"pnl\": 2000}, {\"pnl\": -1000}, {\"pnl\": 4000}]", target_fixture="ectx")
def given_trades(ectx):
    ectx["trade_log"] = [{"pnl": 2000.0}, {"pnl": -1000.0}, {"pnl": 4000.0}]
    return ectx


@given("空交易记录", target_fixture="ectx")
def given_no_trades(ectx):
    return ectx


@given("决策记录包含买入卖出和持仓", target_fixture="ectx")
def given_decisions():
    def _d(action, indicators=None):
        return Decision(
            datetime=datetime(2024, 1, 1),
            bar_index=0,
            action=action,
            symbol=None, quantity=None, reasoning="",
            market_snapshot={}, account_snapshot={},
            indicators_used=indicators or {},
            tool_calls=[],
        )
    return {
        "decisions": [
            _d("buy",  {"RSI": 28}),
            _d("hold"),
            _d("hold", {"RSI": 55}),
            _d("sell", {"RSI": 72}),
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("计算绩效指标", target_fixture="ectx")
def when_calc_perf(ectx):
    evaluator = Evaluator()
    ectx["perf"] = evaluator.calc_performance(ectx["equity"], ectx.get("trade_log", []))
    return ectx


@when("计算遵循度", target_fixture="ectx")
def when_calc_compliance(ectx):
    evaluator = Evaluator()
    ectx["compliance"] = evaluator.calc_compliance(ectx["decisions"])
    return ectx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("total_return 应为 0.05")
def then_total_return(ectx):
    assert ectx["perf"].total_return == pytest.approx(0.05, rel=1e-4)


@then("max_drawdown 应大于 0")
def then_max_drawdown(ectx):
    assert ectx["perf"].max_drawdown > 0


@then("sharpe_ratio 应大于 0")
def then_sharpe(ectx):
    assert ectx["perf"].sharpe_ratio > 0


@then("win_rate 应为 0.667")
def then_win_rate(ectx):
    assert ectx["perf"].win_rate == pytest.approx(0.667, abs=0.001)


@then("profit_factor 应为 6.0")
def then_profit_factor(ectx):
    assert ectx["perf"].profit_factor == pytest.approx(6.0, rel=0.01)


@then("total_return 应为 0.0")
def then_zero_return(ectx):
    assert ectx["perf"].total_return == pytest.approx(0.0)


@then("total_trades 应为 0")
def then_zero_trades(ectx):
    assert ectx["perf"].total_trades == 0


@then("action_distribution.buy 应为 1")
def then_dist_buy(ectx):
    assert ectx["compliance"].action_distribution.get("buy") == 1


@then("action_distribution.sell 应为 1")
def then_dist_sell(ectx):
    assert ectx["compliance"].action_distribution.get("sell") == 1


@then("action_distribution.hold 应为 2")
def then_dist_hold(ectx):
    assert ectx["compliance"].action_distribution.get("hold") == 2


@then("decisions_with_indicators 应为 3")
def then_with_indicators(ectx):
    assert ectx["compliance"].decisions_with_indicators == 3


# ─────────────────────────────────────────────────────────────────────────────
# Then — 新增绩效指标
# ─────────────────────────────────────────────────────────────────────────────

@then("sortino_ratio 应大于 0")
def then_sortino_positive(ectx):
    assert ectx["perf"].sortino_ratio > 0


@then(parsers.parse("max_dd_duration 应为 {n:d}"))
def then_max_dd_duration(ectx, n):
    assert ectx["perf"].max_dd_duration == n


@then(parsers.parse("avg_trade_return 应约为 {val:f}"))
def then_avg_trade_return(ectx, val):
    assert ectx["perf"].avg_trade_return == pytest.approx(val, rel=0.01)


@then(parsers.parse("best_trade 应为 {val:f}"))
def then_best_trade(ectx, val):
    assert ectx["perf"].best_trade == pytest.approx(val)


@then(parsers.parse("worst_trade 应为 {val:f}"))
def then_worst_trade(ectx, val):
    assert ectx["perf"].worst_trade == pytest.approx(val)


@then("volatility 应大于 0")
def then_volatility_positive(ectx):
    assert ectx["perf"].volatility > 0


@then("cagr 应大于 0")
def then_cagr_positive(ectx):
    assert ectx["perf"].cagr > 0
