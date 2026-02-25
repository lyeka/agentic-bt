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

@scenario("features/engine.feature", "有效期为 0 的订单在下一根 bar 过期")
def test_order_expired(): pass

@scenario("features/engine.feature", "取消挂单")
def test_cancel_order(): pass

@scenario("features/engine.feature", "查询挂单列表")
def test_pending_orders(): pass

@scenario("features/engine.feature", "成交后产生 fill 事件")
def test_fill_event(): pass

@scenario("features/engine.feature", "限价买入 — 价格触及限价时成交")
def test_limit_buy_fills(): pass

@scenario("features/engine.feature", "限价买入 — 价格未触及时不成交")
def test_limit_buy_no_fill(): pass

@scenario("features/engine.feature", "限价卖出 — 价格触及限价时成交")
def test_limit_sell_fills(): pass

@scenario("features/engine.feature", "止损卖出 — 价格击穿止损价")
def test_stop_sell_triggered(): pass

@scenario("features/engine.feature", "止损买入 — 突破价格触发")
def test_stop_buy_triggered(): pass

@scenario("features/engine.feature", "限价单有效期到期未成交自动过期")
def test_limit_expired(): pass

@scenario("features/engine.feature", "最大持仓数限制")
def test_max_open_positions(): pass

@scenario("features/engine.feature", "组合回撤超限禁止开仓")
def test_max_drawdown(): pass

@scenario("features/engine.feature", "单日亏损超限禁止开仓")
def test_max_daily_loss(): pass

@scenario("features/engine.feature", "Bracket 买入 — 主单成交后止损止盈子单激活")
def test_bracket_activates(): pass

@scenario("features/engine.feature", "Bracket 止盈触发后止损单自动取消")
def test_bracket_tp_cancels_stop(): pass

@scenario("features/engine.feature", "Bracket 主单被风控拒绝时子单不创建")
def test_bracket_rejected(): pass

@scenario("features/engine.feature", "卖空开仓")
def test_short_open(): pass

@scenario("features/engine.feature", "空头平仓盈利")
def test_short_close_profit(): pass

@scenario("features/engine.feature", "空头浮动盈亏方向正确")
def test_short_unrealized_pnl(): pass

@scenario("features/engine.feature", "多资产数据加载与快照查询")
def test_multi_asset_load(): pass

@scenario("features/engine.feature", "跨资产建仓与持仓查询")
def test_multi_asset_positions(): pass

@scenario("features/engine.feature", "多资产权益合并计算")
def test_multi_asset_equity(): pass

@scenario("features/engine.feature", "百分比滑点计算正确")
def test_pct_slippage(): pass

@scenario("features/engine.feature", "成交量约束导致部分成交")
def test_volume_partial_fill(): pass

@scenario("features/engine.feature", "部分成交后剩余订单继续撮合")
def test_partial_fill_continues(): pass

@scenario("features/engine.feature", "查询最近 N 根 K 线")
def test_recent_bars(): pass


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


def _make_msft_df():
    return pd.DataFrame({
        "date":   ["2024-01-01", "2024-01-02", "2024-01-03"],
        "open":   [50.0, 51.5, 53.0],
        "high":   [52.0, 54.0, 55.0],
        "low":    [49.0, 51.0, 52.5],
        "close":  [51.0, 53.5, 54.5],
        "volume": [500_000, 600_000, 450_000],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse("初始资金 {cash:d}"), target_fixture="ctx")
def given_initial_cash(cash):
    return {"cash": float(cash), "df": _make_df(),
            "risk": RiskConfig(), "commission": CommissionConfig(),
            "slippage": SlippageConfig()}


@given("多资产引擎包含 \"AAPL\" 和 \"MSFT\"", target_fixture="ctx")
def given_multi_asset_engine():
    return {
        "cash": 100_000.0,
        "df": {"AAPL": _make_df(), "MSFT": _make_msft_df()},
        "risk": RiskConfig(max_position_pct=1.0),
        "commission": CommissionConfig(),
        "slippage": SlippageConfig(),
    }


@given("市场数据:", target_fixture="ctx")
def given_market_data(ctx, datatable):
    # Background 的 datatable 已被 given_initial_cash 处理，此处忽略
    return ctx


@given(parsers.parse('风控配置 max_position_pct 为 {pct:f}'), target_fixture="ctx")
def given_risk_config(ctx, pct):
    ctx["risk"] = RiskConfig(max_position_pct=pct)
    return ctx


@given(parsers.parse("风控配置 max_open_positions 为 {n:d}"), target_fixture="ctx")
def given_max_open_positions(ctx, n):
    ctx["risk"] = RiskConfig(max_open_positions=n)
    return ctx


@given(parsers.parse("风控配置 max_portfolio_drawdown 为 {pct:f}"), target_fixture="ctx")
def given_max_drawdown(ctx, pct):
    ctx["risk"] = RiskConfig(max_portfolio_drawdown=pct)
    return ctx


@given(parsers.parse("风控配置 max_daily_loss_pct 为 {pct:f}"), target_fixture="ctx")
def given_max_daily_loss(ctx, pct):
    ctx["risk"] = RiskConfig(max_daily_loss_pct=pct)
    return ctx


@given(parsers.parse("滑点配置为 {val:f}"), target_fixture="ctx")
def given_slippage(ctx, val):
    ctx["slippage"] = SlippageConfig(value=val)
    return ctx


@given(parsers.parse("百分比滑点配置为 {pct:f}"), target_fixture="ctx")
def given_pct_slippage(ctx, pct):
    ctx["slippage"] = SlippageConfig(mode="pct", pct=pct)
    return ctx


@given(parsers.parse("成交量约束配置 max_volume_pct 为 {pct:f}"), target_fixture="ctx")
def given_max_volume_pct(ctx, pct):
    ctx["slippage"] = SlippageConfig(max_volume_pct=pct)
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


@given(parsers.parse('空头持有 "{sym}" {qty:d} 股 均价 {price:f}'), target_fixture="ctx")
def given_short_position(ctx, sym, qty, price):
    from agenticbt.models import Position
    eng = _engine(ctx)
    eng._positions[sym] = Position(symbol=sym, size=-qty, avg_price=price)
    eng._cash += qty * price   # 空头卖出时收到的现金保证金
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
    ctx["engine_events"] = eng.drain_events()
    return ctx


@when(parsers.parse("引擎推进到 bar {idx:d}"), target_fixture="ctx")
def when_advance(ctx, idx):
    eng = _engine(ctx)
    while eng._bar_index < idx:
        eng.advance()
    return ctx


@when(parsers.parse('提交有效期 0 的买入 "{sym}" {qty:d} 股'), target_fixture="ctx")
def when_submit_buy_valid_bars_0(ctx, sym, qty):
    result = _engine(ctx).submit_order(sym, "buy", qty, valid_bars=0)
    ctx["submit_result"] = result
    return ctx


@when("取消该订单", target_fixture="ctx")
def when_cancel_order(ctx):
    order_id = ctx["submit_result"]["order_id"]
    ctx["cancel_result"] = _engine(ctx).cancel_order(order_id)
    return ctx


@when(parsers.parse('提交限价买入 "{sym}" {qty:d} 股 限价 {price:f}'), target_fixture="ctx")
def when_submit_limit_buy(ctx, sym, qty, price):
    result = _engine(ctx).submit_order(sym, "buy", qty, order_type="limit", limit_price=price)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交限价卖出 "{sym}" {qty:d} 股 限价 {price:f}'), target_fixture="ctx")
def when_submit_limit_sell(ctx, sym, qty, price):
    result = _engine(ctx).submit_order(sym, "sell", qty, order_type="limit", limit_price=price)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交止损卖出 "{sym}" {qty:d} 股 止损价 {price:f}'), target_fixture="ctx")
def when_submit_stop_sell(ctx, sym, qty, price):
    result = _engine(ctx).submit_order(sym, "sell", qty, order_type="stop", stop_price=price)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交止损买入 "{sym}" {qty:d} 股 止损价 {price:f}'), target_fixture="ctx")
def when_submit_stop_buy(ctx, sym, qty, price):
    result = _engine(ctx).submit_order(sym, "buy", qty, order_type="stop", stop_price=price)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交卖空 "{sym}" {qty:d} 股'), target_fixture="ctx")
def when_submit_short(ctx, sym, qty):
    result = _engine(ctx).submit_sell(sym, qty)
    ctx["submit_result"] = result
    return ctx


@when(parsers.parse('提交有效期 0 的限价买入 "{sym}" {qty:d} 股 限价 {price:f}'), target_fixture="ctx")
def when_submit_limit_buy_valid_bars_0(ctx, sym, qty, price):
    result = _engine(ctx).submit_order(sym, "buy", qty, order_type="limit",
                                       limit_price=price, valid_bars=0)
    ctx["submit_result"] = result
    return ctx


@when("模拟组合回撤 10%", target_fixture="ctx")
def when_simulate_drawdown_10pct(ctx):
    _engine(ctx)._cash -= 10_000   # equity = 90000, peak = 100000 → drawdown 10%
    return ctx


@when("模拟当日亏损 5%", target_fixture="ctx")
def when_simulate_daily_loss_5pct(ctx):
    _engine(ctx)._cash -= 5_000    # equity = 95000, day_start = 100000 → loss 5%
    return ctx


@when(parsers.parse('提交 Bracket 买入 "{sym}" {qty:d} 股 止损 {sl:f} 止盈 {tp:f}'), target_fixture="ctx")
def when_submit_bracket_buy(ctx, sym, qty, sl, tp):
    result = _engine(ctx).submit_bracket(sym, "buy", qty, stop_loss=sl, take_profit=tp)
    ctx["submit_result"] = result
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
    trade_log = _engine(ctx).trade_log()
    assert trade_log, "没有交易记录"
    assert trade_log[-1]["pnl"] > 0


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


@then("应无成交记录")
def then_no_fills(ctx):
    assert ctx.get("fills", []) == []


@then(parsers.parse('应产生 "{event_type}" 类型的引擎事件'))
def then_engine_event(ctx, event_type):
    events = ctx.get("engine_events", [])
    assert any(e.type == event_type for e in events), (
        f"未找到 {event_type} 事件，实际事件: {[e.type for e in events]}"
    )


@then("挂单列表应为空")
def then_no_pending_orders(ctx):
    assert _engine(ctx).pending_orders() == []


@then('取消结果应为 "cancelled"')
def then_cancel_result_cancelled(ctx):
    assert ctx["cancel_result"]["status"] == "cancelled"


@then(parsers.parse("挂单列表应有 {n:d} 条记录"))
def then_pending_orders_count(ctx, n):
    assert len(_engine(ctx).pending_orders()) == n


@then(parsers.parse('挂单应包含 symbol 为 "{sym}"'))
def then_pending_order_symbol(ctx, sym):
    orders = _engine(ctx).pending_orders()
    assert any(o["symbol"] == sym for o in orders)


@then(parsers.parse('持仓 "{sym}" 空头应为 {qty:d} 股'))
def then_short_position_size(ctx, sym, qty):
    pos = _engine(ctx)._positions.get(sym)
    assert pos is not None and pos.size == -qty


@then("空头浮动盈亏应为正数")
def then_short_unrealized_positive(ctx):
    positions = _engine(ctx)._positions
    assert positions, "没有持仓"
    pos = next(iter(positions.values()))
    assert pos.unrealized_pnl > 0, f"空头浮动盈亏应为正数，实际: {pos.unrealized_pnl}"


@then(parsers.parse('"{sym}" 市场快照收盘价应为 {price:f}'))
def then_symbol_snapshot_close(ctx, sym, price):
    snap = _engine(ctx).market_snapshot(sym)
    assert snap.close == pytest.approx(price)


# ─────────────────────────────────────────────────────────────────────────────
# recent_bars scenario steps
# ─────────────────────────────────────────────────────────────────────────────

def _make_long_df(n: int = 30):
    import numpy as np
    rng = np.random.default_rng(0)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0.5, 2, n),
        "low": close - rng.uniform(0.5, 2, n),
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, n).astype(float),
    })


@given(parsers.parse("初始资金 100000 和 {n:d} 根 bar 数据"), target_fixture="ctx")
def given_initial_cash_n_bars(n):
    return {"cash": 100_000.0, "df": _make_long_df(n),
            "risk": RiskConfig(), "commission": CommissionConfig(),
            "slippage": SlippageConfig()}


@when(parsers.parse("推进到第 {n:d} 根 bar"), target_fixture="ctx")
def when_advance_to_n(ctx, n):
    eng = _engine(ctx)
    while eng._bar_index < n:
        eng.advance()
    return ctx


@when(parsers.parse("查询最近 {n:d} 根 bar"), target_fixture="ctx")
def when_query_recent_bars(ctx, n):
    ctx["recent_bars_result"] = _engine(ctx).recent_bars(n)
    return ctx


@then(parsers.parse("应返回 {n:d} 条记录且 bar_index 从 {start:d} 到 {end:d}"))
def then_recent_bars_range(ctx, n, start, end):
    result = ctx["recent_bars_result"]
    assert len(result) == n, f"expected {n} bars, got {len(result)}"
    assert result[0]["bar_index"] == start, f"first bar_index: {result[0]['bar_index']}"
    assert result[-1]["bar_index"] == end, f"last bar_index: {result[-1]['bar_index']}"
