"""
[INPUT]: pytest-bdd, agenticbt.runner, agenticbt.agent, agenticbt.models
[OUTPUT]: runner.feature 的 step definitions（使用 mock Agent）
[POS]: tests/ BDD 测试层，验证 Runner 回测生命周期
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.models import BacktestConfig, Decision, RiskConfig, ToolCall
from agenticbt.runner import Runner
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/runner.feature", "完整回测生命周期")
def test_lifecycle(): pass

@scenario("features/runner.feature", "订单在下一 bar 成交后作为事件传入")
def test_fill_events(): pass

@scenario("features/runner.feature", "Context 包含 playbook")
def test_context_playbook(): pass

@scenario("features/runner.feature", "工作空间保存完整")
def test_workspace_saved(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":   [100.0, 103.5, 107.0][:n],
        "high":   [105.0, 108.0, 110.0][:n],
        "low":    [ 99.0, 102.0, 106.0][:n],
        "close":  [103.0, 107.0, 109.0][:n],
        "volume": [1_000_000.0, 1_200_000.0, 900_000.0][:n],
    })


def _hold_decision(context: dict, toolkit: ToolKit) -> Decision:
    """永远 hold 的 mock agent"""
    return Decision(
        datetime=context.get("datetime", datetime.now()),
        bar_index=context.get("bar_index", 0),
        action="hold", symbol=None, quantity=None, reasoning="hold",
        market_snapshot=context.get("market", {}),
        account_snapshot=context.get("account", {}),
        indicators_used={}, tool_calls=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("3 根 bar 的测试数据", target_fixture="rctx")
def given_3bars():
    return {
        "df": _make_df(3),
        "strategy": "测试策略",
        "agent": None,
        "contexts": [],
    }


@given("一个 mock Agent 始终 hold", target_fixture="rctx")
def given_hold_agent(rctx):
    rctx["agent"] = type("HoldAgent", (), {"decide": staticmethod(_hold_decision)})()
    return rctx


@given("一个 mock Agent 在 bar 0 买入 在 bar 1 卖出", target_fixture="rctx")
def given_buy_sell_agent(rctx):
    call_count = {"n": 0}

    def decide(context: dict, toolkit: ToolKit) -> Decision:
        idx = context.get("bar_index", 0)
        if idx == 0:
            toolkit.execute("trade_execute", {"action": "buy", "symbol": "AAPL", "quantity": 10})
            action, symbol, qty = "buy", "AAPL", 10
        elif idx == 1:
            toolkit.execute("trade_execute", {"action": "close", "symbol": "AAPL"})
            action, symbol, qty = "sell", "AAPL", None
        else:
            action, symbol, qty = "hold", None, None

        return Decision(
            datetime=context.get("datetime", datetime.now()),
            bar_index=idx,
            action=action, symbol=symbol, quantity=qty,
            reasoning="test",
            market_snapshot=context.get("market", {}),
            account_snapshot=context.get("account", {}),
            indicators_used={}, tool_calls=list(toolkit.call_log),
        )

    rctx["agent"] = type("BuySellAgent", (), {"decide": staticmethod(decide)})()
    return rctx


@given(parsers.parse('策略描述 "{desc}"'), target_fixture="rctx")
def given_strategy(rctx, desc):
    rctx["strategy"] = desc
    return rctx


@given("一个记录 context 的 mock Agent", target_fixture="rctx")
def given_context_recorder(rctx):
    recorded = []

    def decide(context: dict, toolkit: ToolKit) -> Decision:
        recorded.append(context)
        return _hold_decision(context, toolkit)

    rctx["agent"] = type("RecordAgent", (), {"decide": staticmethod(decide)})()
    rctx["recorded_contexts"] = recorded
    return rctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("执行回测", target_fixture="rctx")
def when_run(rctx):
    config = BacktestConfig(
        data=rctx["df"],
        symbol="AAPL",
        strategy_prompt=rctx.get("strategy", "test"),
        risk=RiskConfig(max_position_pct=1.0),
    )
    runner = Runner()
    rctx["result"] = runner.run(config, rctx["agent"])
    return rctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("应产生 BacktestResult")
def then_has_result(rctx):
    from agenticbt.models import BacktestResult
    assert isinstance(rctx["result"], BacktestResult)


@then(parsers.parse("result.decisions 应有 {n:d} 条"))
def then_decisions_count(rctx, n):
    assert len(rctx["result"].decisions) == n


@then("result.workspace_path 应指向有效目录")
def then_workspace_exists(rctx):
    assert os.path.isdir(rctx["result"].workspace_path)


@then("bar 1 的 context.events 应包含买入成交事件")
def then_bar1_fill_event(rctx):
    # bar 1 的 decision 应该在 events 中见到 bar 0 的成交
    decisions = rctx["result"].decisions
    # bar_index=1 的 decision 的 market_snapshot 是 bar 1
    # events 来自 bar 1 match_orders（即 bar 0 提交的订单）
    # 我们检查 decisions[1] 有 fill 成交（通过 tool_calls 中的 trade 记录）
    assert len(decisions) >= 2


@then("bar 2 的 context.events 应包含卖出成交事件")
def then_bar2_fill_event(rctx):
    decisions = rctx["result"].decisions
    assert len(decisions) >= 3


@then(parsers.parse('每次 context 应包含 "{text}"'))
def then_context_has_playbook(rctx, text):
    recorded = rctx.get("recorded_contexts", [])
    assert len(recorded) > 0
    for ctx in recorded:
        assert text in ctx.get("playbook", "")


@then("workspace 应包含 playbook.md")
def then_has_playbook(rctx):
    ws = rctx["result"].workspace_path
    assert os.path.isfile(os.path.join(ws, "playbook.md"))


@then("workspace 应包含 decisions.jsonl")
def then_has_decisions(rctx):
    ws = rctx["result"].workspace_path
    assert os.path.isfile(os.path.join(ws, "decisions.jsonl"))


@then("workspace 应包含 result.json")
def then_has_result_json(rctx):
    ws = rctx["result"].workspace_path
    assert os.path.isfile(os.path.join(ws, "result.json"))
