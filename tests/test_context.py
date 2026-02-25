"""
[INPUT]: pytest-bdd, agenticbt.context, agenticbt.engine, agenticbt.memory, agenticbt.models
[OUTPUT]: context.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 ContextManager 上下文组装与格式化行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.context import ContextManager
from agenticbt.engine import Engine
from agenticbt.memory import Memory, Workspace
from agenticbt.models import ContextConfig, Decision, Position, RiskConfig, ToolCall


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/context.feature", "Agent 看到近期价格走势")
def test_recent_bars(): pass

@scenario("features/context.feature", "回测初期走势不足窗口时展示所有可用的")
def test_recent_bars_early(): pass

@scenario("features/context.feature", "Agent 看到自己的挂单")
def test_pending_orders(): pass

@scenario("features/context.feature", "无挂单时不展示挂单区域")
def test_no_pending_orders(): pass

@scenario("features/context.feature", "Agent 看到近期决策历史")
def test_recent_decisions(): pass

@scenario("features/context.feature", "无历史决策时不展示近期决策区域")
def test_no_decisions(): pass

@scenario("features/context.feature", "成交事件显示成交详情")
def test_fill_event(): pass

@scenario("features/context.feature", "过期事件不因缺少字段而报错")
def test_expired_event(): pass

@scenario("features/context.feature", "取消事件正确展示")
def test_cancelled_event(): pass

@scenario("features/context.feature", "持仓备注按 symbol 逐行展示")
def test_position_notes(): pass

@scenario("features/context.feature", "Playbook 注入系统提示词")
def test_playbook(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine(n: int = 30) -> Engine:
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0.5, 2, n),
        "low": close - rng.uniform(0.5, 2, n),
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, n).astype(float),
    })
    return Engine(data=df, symbol="AAPL", initial_cash=100_000.0,
                  risk=RiskConfig(max_position_pct=1.0))


def _make_decision(bar_index: int, action: str = "hold", reasoning: str = "test") -> Decision:
    return Decision(
        datetime=datetime(2024, 1, 1),
        bar_index=bar_index,
        action=action, symbol=None, quantity=None,
        reasoning=reasoning,
        market_snapshot={}, account_snapshot={},
        indicators_used={}, tool_calls=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse("初始资金 100000 和 {n:d} 根 bar 的引擎"), target_fixture="cctx")
def given_engine_n_bars(n):
    eng = _make_engine(n)
    ws = Workspace()
    mem = Memory(ws)
    ctx_mgr = ContextManager()
    return {
        "engine": eng,
        "memory": mem,
        "ctx_mgr": ctx_mgr,
        "events": [],
        "decisions": [],
        "context": None,
    }


@given(parsers.parse('提交了一个限价买入 AAPL 100 股 @ {price:f}'), target_fixture="cctx")
def given_limit_order(cctx, price):
    # 先推进到 bar 0 才能提交订单
    if cctx["engine"]._bar_index < 0:
        cctx["engine"].advance()
    cctx["engine"].submit_order("AAPL", "buy", 100, order_type="limit", limit_price=price)
    return cctx


@given(parsers.parse("已有 {n:d} 条历史决策"), target_fixture="cctx")
def given_n_decisions(cctx, n):
    cctx["decisions"] = [_make_decision(i, "hold", f"decision {i}") for i in range(n)]
    return cctx


@given("本轮有买入成交事件", target_fixture="cctx")
def given_fill_event(cctx):
    cctx["events"] = [
        {"type": "fill", "order_id": "abc123", "symbol": "AAPL",
         "side": "buy", "quantity": 100, "price": 100.5}
    ]
    return cctx


@given("本轮有订单过期事件", target_fixture="cctx")
def given_expired_event(cctx):
    cctx["events"] = [
        {"type": "expired", "order_id": "xyz456", "symbol": "AAPL"}
    ]
    return cctx


@given("本轮有订单取消事件", target_fixture="cctx")
def given_cancelled_event(cctx):
    cctx["events"] = [
        {"type": "cancelled", "order_id": "def789", "symbol": "AAPL"}
    ]
    return cctx


@given("持有 AAPL 和 MSFT 各 100 股", target_fixture="cctx")
def given_two_positions(cctx):
    eng = cctx["engine"]
    eng._positions["AAPL"] = Position(symbol="AAPL", size=100, avg_price=100.0)
    eng._positions["MSFT"] = Position(symbol="MSFT", size=100, avg_price=50.0)
    return cctx


@given(parsers.parse('AAPL 持仓备注为 "{note}"'), target_fixture="cctx")
def given_aapl_note(cctx, note):
    cctx["memory"].note("position_AAPL", note)
    return cctx


@given(parsers.parse('MSFT 持仓备注为 "{note}"'), target_fixture="cctx")
def given_msft_note(cctx, note):
    cctx["memory"].note("position_MSFT", note)
    return cctx


@given(parsers.parse('playbook 为 "{text}"'), target_fixture="cctx")
def given_playbook(cctx, text):
    cctx["memory"].init_playbook(text)
    return cctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse("推进到第 {n:d} 根 bar 并组装上下文"), target_fixture="cctx")
def when_advance_and_assemble(cctx, n):
    eng = cctx["engine"]
    while eng._bar_index < n:
        eng.advance()
    cctx["context"] = cctx["ctx_mgr"].assemble(
        eng, cctx["memory"], eng._bar_index, cctx["events"], cctx["decisions"]
    )
    return cctx


@when("组装上下文", target_fixture="cctx")
def when_assemble(cctx):
    eng = cctx["engine"]
    if eng._bar_index < 0:
        eng.advance()
    cctx["context"] = cctx["ctx_mgr"].assemble(
        eng, cctx["memory"], eng._bar_index, cctx["events"], cctx["decisions"]
    )
    return cctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse("上下文应包含最近 {n:d} 根 K 线的收盘价"))
def then_has_n_recent_bars(cctx, n):
    ctx = cctx["context"]
    assert len(ctx.recent_bars) == n, f"expected {n}, got {len(ctx.recent_bars)}"


@then(parsers.parse("上下文应包含 {n:d} 根 K 线的收盘价"))
def then_has_exactly_n_bars(cctx, n):
    ctx = cctx["context"]
    assert len(ctx.recent_bars) == n, f"expected {n}, got {len(ctx.recent_bars)}"


@then("上下文文本应包含挂单信息")
def then_text_has_pending(cctx):
    assert "挂单" in cctx["context"].formatted_text


@then(parsers.parse('挂单信息应包含 "{a}" 和 "{b}"'))
def then_pending_contains(cctx, a, b):
    text = cctx["context"].formatted_text
    assert a in text, f"'{a}' not in formatted_text"
    assert b in text, f"'{b}' not in formatted_text"


@then(parsers.parse('上下文文本不应包含 "{text}"'))
def then_text_not_contains(cctx, text):
    assert text not in cctx["context"].formatted_text


@then(parsers.parse("上下文应包含最近 {n:d} 条决策摘要"))
def then_has_n_recent_decisions(cctx, n):
    ctx = cctx["context"]
    assert len(ctx.recent_decisions) == n, f"expected {n}, got {len(ctx.recent_decisions)}"


@then(parsers.parse('上下文文本应包含 "{text}"'))
def then_text_contains(cctx, text):
    assert text in cctx["context"].formatted_text, (
        f"'{text}' not found in:\n{cctx['context'].formatted_text}"
    )


@then(parsers.parse('context.playbook 应为 "{text}"'))
def then_playbook(cctx, text):
    assert cctx["context"].playbook == text
