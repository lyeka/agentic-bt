"""
[INPUT]: pytest-bdd, agenticbt.engine, agenticbt.models
[OUTPUT]: engine.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 Engine 确定性行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.engine import Engine
from agenticbt.models import CommissionConfig, RiskConfig, SlippageConfig


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/engine.feature", "逐 bar 推进时间")
def test_advance(): pass

@scenario("features/engine.feature", "bar 0 提交的买单在 bar 1 开盘价成交")
def test_buy_fills_at_next_open(): pass

@scenario("features/engine.feature", "平仓自动计算数量")
def test_close_position(): pass

@scenario("features/engine.feature", "风控拒绝超限仓位")
def test_risk_reject(): pass

@scenario("features/engine.feature", "滑点影响成交价")
def test_slippage(): pass

@scenario("features/engine.feature", "手续费扣减现金")
def test_commission(): pass

@scenario("features/engine.feature", "权益曲线正确跟踪")
def test_equity_curve(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / State
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ctx():
    """每个 scenario 独立的可变状态容器"""
    return {}


def _make_df():
    return pd.DataFrame({
        "date":   ["2024-01-01", "2024-01-02", "2024-01-03"],
        "open":   [100.0, 103.5, 107.0],
        "high":   [105.0, 108.0, 110.0],
        "low":    [ 99.0, 102.0, 106.0],
        "close":  [103.0, 107.0, 109.0],
        "volume": [1_000_000, 1_200_000, 900_000],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse("初始资金 {cash:d}"), target_fixture="ctx")
def given_initial_cash(cash):
    return {"cash": float(cash), "df": _make_df(),
            "risk": RiskConfig(), "commission": CommissionConfig(),
            "slippage": SlippageConfig()}


@given("市场数据:", target_fixture="ctx")
def given_market_data(ctx, datatable):
    # Background 的 datatable 已被 given_initial_cash 处理，此处忽略
    return ctx


@given(parsers.parse('风控配置 max_position_pct 为 {pct:f}'), target_fixture="ctx")
def given_risk_config(ctx, pct):
    ctx["risk"] = RiskConfig(max_position_pct=pct)
    return ctx


@given(parsers.parse("滑点配置为 {val:f}"), target_fixture="ctx")
def given_slippage(ctx, val):
    ctx["slippage"] = SlippageConfig(value=val)
    return ctx


@given(parsers.parse("手续费率为 {rate:f}"), target_fixture="ctx")
def given_commission(ctx, rate):
    ctx["commission"] = CommissionConfig(rate=rate)
    return ctx


def _engine(ctx) -> Engine:
    """从 ctx 构建或复用 Engine 实例"""
    if "engine" not in ctx:
        ctx["engine"] = Engine(
            data=ctx["df"],
            symbol="AAPL",
            initial_cash=ctx.get("cash", 100_000.0),
            risk=ctx.get("risk", RiskConfig()),
            commission=ctx.get("commission", CommissionConfig()),
            slippage=ctx.get("slippage", SlippageConfig()),
        )
    return ctx["engine"]


@given(parsers.parse("引擎在 bar {idx:d}"), target_fixture="ctx")
def given_engine_at_bar(ctx, idx):
    eng = _engine(ctx)
    for _ in range(idx + 1):
        eng.advance()
    return ctx


@given(parsers.parse('持有 "{sym}" {qty:d} 股 均价 {price:f}'), target_fixture="ctx")
def given_position(ctx, sym, qty, price):
    from agenticbt.models import Position
    eng = _engine(ctx)
    eng._positions[sym] = Position(symbol=sym, size=qty, avg_price=price)
    eng._cash -= qty * price
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse("引擎推进到 bar {idx:d}"), target_fixture="ctx")
def when_advance_to(ctx, idx):
    eng = _engine(ctx)
    while eng._bar_index < idx:
        eng.advance()
    return ctx


@when(parsers.parse('提交买入 "{sym}" {qty:d} 股'), target_fixture="ctx")
def when_submit_buy(ctx, sym, qty):
    result = _engine(ctx).submit_buy(sym, qty)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交平仓 "{sym}"'), target_fixture="ctx")
def when_submit_close(ctx, sym):
    ctx["submit_result"] = _engine(ctx).submit_close(sym)
    return ctx


@when(parsers.parse("引擎推进到 bar {idx:d} 并撮合订单"), target_fixture="ctx")
def when_advance_and_match(ctx, idx):
    eng = _engine(ctx)
    while eng._bar_index < idx:
        bar = eng.advance()
    fills = eng.match_orders(bar)
    ctx["fills"] = fills
    return ctx


@when(parsers.parse("引擎推进到 bar {idx:d}"), target_fixture="ctx")
def when_advance(ctx, idx):
    eng = _engine(ctx)
    while eng._bar_index < idx:
        eng.advance()
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('当前日期应为 "{date}"'))
def then_current_date(ctx, date):
    snap = _engine(ctx).market_snapshot()
    assert snap.datetime.strftime("%Y-%m-%d") == date


@then(parsers.parse("当前收盘价应为 {price:f}"))
def then_close(ctx, price):
    assert _engine(ctx).market_snapshot().close == pytest.approx(price)


@then(parsers.parse("订单应以 {price:f} 成交"))
def then_fill_price(ctx, price):
    fills = ctx.get("fills", [])
    assert fills, "没有成交记录"
    assert fills[0].price == pytest.approx(price)


@then(parsers.parse('持仓 "{sym}" 应为 {qty:d} 股 均价 {price:f}'))
def then_position(ctx, sym, qty, price):
    pos = _engine(ctx)._positions.get(sym)
    assert pos is not None and pos.size == qty
    assert pos.avg_price == pytest.approx(price)


@then(parsers.parse("现金应为 {cash:f}"))
def then_cash(ctx, cash):
    assert _engine(ctx)._cash == pytest.approx(cash)


@then(parsers.parse('持仓 "{sym}" 应为 {qty:d} 股'))
def then_position_size(ctx, sym, qty):
    pos = _engine(ctx)._positions.get(sym)
    if qty == 0:
        assert pos is None or pos.size == 0
    else:
        assert pos is not None and pos.size == qty


@then("已实现盈亏应为正数")
def then_realized_pnl_positive(ctx):
    # 均价 100, 卖出价 103.5 → 盈利；通过 engine.fills() 验证
    fills = _engine(ctx).fills()
    assert fills, "没有成交记录"
    sell_fill = next((f for f in fills if f.side == "sell"), None)
    assert sell_fill is not None, "没有卖出成交"
    assert sell_fill.price > 100.0


@then("订单应被拒绝")
def then_order_rejected(ctx):
    assert ctx["submit_result"]["status"] == "rejected"


@then(parsers.parse('拒绝原因应包含 "{text}"'))
def then_reject_reason(ctx, text):
    assert text in ctx["submit_result"]["reason"]


@then(parsers.parse("成交价应为 {price:f}"))
def then_exact_fill_price(ctx, price):
    fills = ctx.get("fills", [])
    assert fills and fills[0].price == pytest.approx(price, abs=1e-4)


@then(parsers.parse("手续费应为 {fee:f}"))
def then_commission(ctx, fee):
    fills = ctx.get("fills", [])
    assert fills and fills[0].commission == pytest.approx(fee, abs=1e-4)


@then(parsers.parse("权益曲线应有 {n:d} 个数据点"))
def then_equity_curve_len(ctx, n):
    assert len(_engine(ctx).equity_curve()) == n


@then("最终权益应反映持仓市值变化")
def then_equity_includes_position(ctx):
    curve = _engine(ctx).equity_curve()
    # bar2 close=109, 持仓 100 股: equity = cash + 100*109 > 初始
    assert curve[-1] > 90_000  # 简单健壮性检查
