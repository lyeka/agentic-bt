"""
[INPUT]: pytest-bdd, agenticbt.tools, agenticbt.engine, agenticbt.memory
[OUTPUT]: tools.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 ToolKit 分发与调用追踪
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.engine import Engine
from agenticbt.memory import Memory, Workspace
from agenticbt.models import CommissionConfig, RiskConfig, SlippageConfig
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/tools.feature", "工具 schema 符合 OpenAI 格式")
def test_schema_format(): pass

@scenario("features/tools.feature", "分发 market_observe")
def test_market_observe(): pass

@scenario("features/tools.feature", "分发 indicator_calc")
def test_indicator_calc(): pass

@scenario("features/tools.feature", "分发 trade_execute")
def test_trade_execute(): pass

@scenario("features/tools.feature", "无交易 = hold")
def test_no_trade_hold(): pass

@scenario("features/tools.feature", "完整调用记录")
def test_full_call_log(): pass

@scenario("features/tools.feature", "分发 order_cancel")
def test_order_cancel(): pass

@scenario("features/tools.feature", "分发 order_query")
def test_order_query(): pass

@scenario("features/tools.feature", "trade_execute 提交限价买入")
def test_limit_buy_via_tool(): pass

@scenario("features/tools.feature", "trade_execute 提交 Bracket 买入")
def test_bracket_via_tool(): pass

@scenario("features/tools.feature", "Bracket 止损价为 0.0 时正确传入引擎")
def test_bracket_zero_stop_loss(): pass

@scenario("features/tools.feature", "工具内部异常时返回错误字典而不崩溃")
def test_tool_exception_returns_error(): pass

@scenario("features/tools.feature", "多资产引擎中指标计算正确绑定 symbol")
def test_multi_asset_indicator(): pass

@scenario("features/tools.feature", "通过 market_history 获取任意长度的历史 K 线")
def test_market_history(): pass

@scenario("features/tools.feature", "market_history 请求超出可用范围时返回所有可用的")
def test_market_history_truncated(): pass

@scenario("features/tools.feature", "工具描述包含返回值说明")
def test_tool_descriptions(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Background fixture
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine() -> Engine:
    import numpy as np
    rng = np.random.default_rng(0)
    n = 30
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0.5, 2, n),
        "low": close - rng.uniform(0.5, 2, n),
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, n).astype(float),
    })
    eng = Engine(data=df, symbol="AAPL", initial_cash=100_000.0,
                 risk=RiskConfig(max_position_pct=1.0))
    eng.advance()  # bar 0
    return eng


@given("一个已初始化的引擎和记忆系统", target_fixture="tctx")
def given_engine_memory():
    eng = _make_engine()
    ws = Workspace()
    mem = Memory(ws)
    toolkit = ToolKit(engine=eng, memory=mem)
    return {"eng": eng, "mem": mem, "kit": toolkit}


@given("多资产引擎和记忆系统", target_fixture="tctx")
def given_multi_asset_engine_memory():
    """B4: 多资产引擎 fixture，data 为 dict[str, DataFrame]"""
    rng = np.random.default_rng(0)
    n = 30

    def make_df():
        close = 100.0 + np.cumsum(rng.normal(0, 1, n))
        return pd.DataFrame({
            "date":   pd.date_range("2024-01-01", periods=n),
            "open":   close + rng.normal(0, 0.5, n),
            "high":   close + rng.uniform(0.5, 2, n),
            "low":    close - rng.uniform(0.5, 2, n),
            "close":  close,
            "volume": rng.integers(500_000, 2_000_000, n).astype(float),
        })

    data = {"AAPL": make_df(), "MSFT": make_df()}
    eng = Engine(data=data, symbol="AAPL", initial_cash=100_000.0,
                 risk=RiskConfig(max_position_pct=1.0))
    eng.advance()
    ws = Workspace()
    mem = Memory(ws)
    toolkit = ToolKit(engine=eng, memory=mem)
    return {"eng": eng, "mem": mem, "kit": toolkit}


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("获取工具 schema 列表", target_fixture="tctx")
def when_get_schemas(tctx):
    tctx["schemas"] = tctx["kit"].schemas
    return tctx


@when(parsers.parse('调用工具 "{tool}" 参数 {args_json}'), target_fixture="tctx")
def when_call_tool(tctx, tool, args_json):
    args = json.loads(args_json)
    tctx["result"] = tctx["kit"].execute(tool, args)
    return tctx


@when("只调用 market_observe 和 indicator_calc", target_fixture="tctx")
def when_call_observe_and_calc(tctx):
    tctx["kit"].execute("market_observe", {})
    tctx["kit"].execute("indicator_calc", {"name": "RSI"})
    return tctx


@when("依次调用 market_observe 和 indicator_calc RSI 和 trade_execute buy", target_fixture="tctx")
def when_call_all_three(tctx):
    tctx["kit"].execute("market_observe", {})
    tctx["kit"].execute("indicator_calc", {"name": "RSI"})
    tctx["kit"].execute("trade_execute", {"action": "buy", "symbol": "AAPL", "quantity": 10})
    return tctx


@when("调用 order_cancel 取消刚提交的订单", target_fixture="tctx")
def when_cancel_last_order(tctx):
    order_id = tctx["result"]["order_id"]
    tctx["result"] = tctx["kit"].execute("order_cancel", {"order_id": order_id})
    return tctx


@when("ToolKit 执行一个会抛出异常的工具调用", target_fixture="tctx")
def when_execute_failing_tool(tctx):
    """B2: 用 patch 让 _market_observe 抛出异常，验证 execute() 捕获"""
    with patch.object(tctx["kit"], "_market_observe", side_effect=RuntimeError("模拟崩溃")):
        tctx["result"] = tctx["kit"].execute("market_observe", {})
    return tctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then('每个 schema 应有 type 为 "function"')
def then_schema_type(tctx):
    for s in tctx["schemas"]:
        assert s["type"] == "function"


@then("每个 schema 应有 function.name 和 function.parameters")
def then_schema_fields(tctx):
    for s in tctx["schemas"]:
        assert "name" in s["function"]
        assert "parameters" in s["function"]


@then("应返回包含 open high low close volume 的 dict")
def then_market_fields(tctx):
    r = tctx["result"]
    for field in ["open", "high", "low", "close", "volume"]:
        assert field in r


@then("应返回包含 value 的指标结果")
def then_indicator_result(tctx):
    assert "value" in tctx["result"]


@then("indicator_queries 应记录此次查询")
def then_indicator_recorded(tctx):
    assert len(tctx["kit"].indicator_queries) > 0


@then("应返回包含 status 的结果")
def then_has_status(tctx):
    assert "status" in tctx["result"]


@then("trade_actions 应记录此次交易")
def then_trade_recorded(tctx):
    assert len(tctx["kit"].trade_actions) > 0


@then("trade_actions 应为空列表")
def then_no_trade(tctx):
    assert tctx["kit"].trade_actions == []


@then(parsers.parse("call_log 应有 {n:d} 条记录"))
def then_call_log_count(tctx, n):
    assert len(tctx["kit"].call_log) == n


@then("每条记录包含 tool input output")
def then_call_log_fields(tctx):
    for tc in tctx["kit"].call_log:
        assert tc.tool
        assert tc.input is not None
        assert tc.output is not None


@then('order_cancel 应返回 status 为 "cancelled"')
def then_cancel_status(tctx):
    assert tctx["result"]["status"] == "cancelled"


@then("应返回包含 pending_orders 的列表")
def then_pending_orders_in_result(tctx):
    assert "pending_orders" in tctx["result"]


# ─────────────────────────────────────────────────────────────────────────────
# 新增 Then（B1/B2/B4）
# ─────────────────────────────────────────────────────────────────────────────

@then("不因 stop_loss 为 0.0 而报错")
def then_no_error_for_zero_stop_loss(tctx):
    """B1: stop_loss=0.0 不应被 falsy 误判，结果应为 submitted"""
    assert "error" not in tctx["result"]


@then("应返回包含 error 字段的字典")
def then_has_error_field(tctx):
    """B2: 工具崩溃后 execute() 返回含 error 的 dict"""
    assert "error" in tctx["result"]


@then("call_log 记录本次失败调用")
def then_failed_call_in_log(tctx):
    """B2: 即使崩溃，call_log 也应追加记录"""
    assert len(tctx["kit"].call_log) > 0
    assert "error" in tctx["kit"].call_log[-1].output


@then("不因 symbol 错误而报错")
def then_no_symbol_error(tctx):
    """B4: 多资产引擎中，存在的 symbol 不应返回 error"""
    assert "error" not in tctx["result"]


# ─────────────────────────────────────────────────────────────────────────────
# market_history scenario steps
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine_n(n: int) -> Engine:
    import numpy as np
    rng = np.random.default_rng(0)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0.5, 2, n),
        "low": close - rng.uniform(0.5, 2, n),
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, n).astype(float),
    })
    from agenticbt.models import RiskConfig
    return Engine(data=df, symbol="AAPL", initial_cash=100_000.0,
                  risk=RiskConfig(max_position_pct=1.0))


@given(parsers.parse("初始资金 100000 和 {n:d} 根 bar 的引擎"), target_fixture="tctx")
def given_engine_n_bars_tools(n):
    eng = _make_engine_n(n)
    ws = Workspace()
    mem = Memory(ws)
    toolkit = ToolKit(engine=eng, memory=mem)
    return {"eng": eng, "mem": mem, "kit": toolkit}


@when(parsers.parse("推进到第 {n:d} 根 bar"), target_fixture="tctx")
def when_advance_to_n_tools(tctx, n):
    eng = tctx["eng"]
    while eng._bar_index < n:
        eng.advance()
    return tctx


@when(parsers.parse("调用 market_history 获取最近 {n:d} 根 bar"), target_fixture="tctx")
def when_call_market_history(tctx, n):
    tctx["result"] = tctx["kit"].execute("market_history", {"bars": n})
    return tctx


@then(parsers.parse("应返回 {n:d} 条完整 OHLCV 记录"))
def then_history_n_records(tctx, n):
    result = tctx["result"]
    assert "history" in result, f"result has no 'history': {result}"
    hist = result["history"]
    assert len(hist) == n, f"expected {n}, got {len(hist)}"
    # 验证 OHLCV 字段完整
    for rec in hist:
        for field in ["open", "high", "low", "close", "volume"]:
            assert field in rec, f"missing field '{field}'"


@then(parsers.parse("应返回 {n:d} 条记录"))
def then_history_exactly_n_records(tctx, n):
    result = tctx["result"]
    assert "history" in result, f"result has no 'history': {result}"
    assert len(result["history"]) == n, f"expected {n}, got {len(result['history'])}"


# ─────────────────────────────────────────────────────────────────────────────
# 工具描述质量验证
# ─────────────────────────────────────────────────────────────────────────────

def _get_tool_description(tctx, tool_name: str) -> str:
    schemas = tctx["kit"].schemas
    for s in schemas:
        if s["function"]["name"] == tool_name:
            return s["function"]["description"]
    raise AssertionError(f"tool {tool_name!r} not found in schemas")


@then(parsers.parse('{tool} 描述应包含 "{text}"'))
def then_tool_desc_contains(tctx, tool, text):
    desc = _get_tool_description(tctx, tool)
    assert text in desc, f"'{text}' not in {tool} description: {desc}"
