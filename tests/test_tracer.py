"""
[INPUT]: pytest-bdd, agenticbt.tracer, agenticbt.models, json, tempfile
[OUTPUT]: tracer.feature 的 step definitions（fixture: trcx）
[POS]: tests/ BDD 测试层，验证 TraceWriter 和 decision_to_dict
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.models import (
    BacktestConfig,
    Context,
    Decision,
    RiskConfig,
    ToolCall,
)
from agenticbt.runner import Runner
from agenticbt.tools import ToolKit
from agenticbt.tracer import TraceWriter, decision_to_dict


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/tracer.feature", "TraceWriter 写入合法 JSONL")
def test_valid_jsonl(): pass

@scenario("features/tracer.feature", "TraceWriter 自动填充 bar_index")
def test_auto_bar_index(): pass

@scenario("features/tracer.feature", "trace.jsonl 记录 LLM 调用")
def test_llm_call(): pass

@scenario("features/tracer.feature", "trace.jsonl 记录工具调用")
def test_tool_call(): pass

@scenario("features/tracer.feature", "decision_to_dict 保留完整 Decision 字段")
def test_decision_to_dict(): pass

@scenario("features/tracer.feature", "Runner 回测产生 trace.jsonl")
def test_runner_trace(): pass

@scenario("features/tracer.feature", "decisions.jsonl 持久化完整 Decision 字段")
def test_decisions_full(): pass


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


def _hold_decision(context: Context, toolkit: ToolKit) -> Decision:
    return Decision(
        datetime=context.datetime,
        bar_index=context.bar_index,
        action="hold", symbol=None, quantity=None, reasoning="hold",
        market_snapshot=context.market,
        account_snapshot=context.account,
        indicators_used={}, tool_calls=[],
    )


def _read_jsonl(path: Path) -> list[dict]:
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个指向临时文件的 TraceWriter", target_fixture="trcx")
def given_trace_writer():
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    tmp.close()
    path = Path(tmp.name)
    return {"writer": TraceWriter(path), "path": path}


@given("一个包含所有字段的 Decision 对象", target_fixture="trcx")
def given_full_decision():
    decision = Decision(
        datetime=datetime(2024, 1, 1),
        bar_index=0,
        action="buy", symbol="AAPL", quantity=100,
        reasoning="RSI 超卖",
        market_snapshot={"close": 103.0},
        account_snapshot={"cash": 100000},
        indicators_used={"RSI": {"value": 35.2}},
        tool_calls=[ToolCall(tool="indicator_calc", input={"name": "RSI"}, output={"value": 35.2})],
        order_result={"status": "submitted", "order_id": "o1"},
        model="test-model",
        tokens_used=150,
        latency_ms=1200.0,
    )
    return {"decision": decision}


@given("3 根 bar 的测试数据", target_fixture="trcx")
def given_3bars_tracer():
    return {"df": _make_df(3), "strategy": "测试策略", "agent": None}


@given("一个 mock Agent 始终 hold", target_fixture="trcx")
def given_hold_agent_tracer(trcx):
    trcx["agent"] = type("HoldAgent", (), {"decide": staticmethod(_hold_decision)})()
    return trcx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("写入 3 条不同类型的事件", target_fixture="trcx")
def when_write_3_events(trcx):
    w = trcx["writer"]
    w.write({"type": "agent_step", "dt": "2024-01-01"})
    w.write({"type": "llm_call", "round": 1, "finish_reason": "stop"})
    w.write({"type": "tool_call", "tool": "indicator_calc"})
    return trcx


@when("设置 bar_index 为 5", target_fixture="trcx")
def when_set_bar(trcx):
    trcx["writer"].set_bar(5)
    return trcx


@when("写入一条不含 bar_index 的事件", target_fixture="trcx")
def when_write_no_bar(trcx):
    trcx["writer"].write({"type": "test"})
    return trcx


@when("写入一条 llm_call 事件", target_fixture="trcx")
def when_write_llm_call(trcx):
    trcx["writer"].write({
        "type": "llm_call",
        "round": 1,
        "model": "test-model",
        "input_messages": [{"role": "user", "content": "test"}],
        "output_content": "ok",
        "output_tool_calls": None,
        "finish_reason": "stop",
        "tokens": {"input": 10, "output": 5, "total": 15},
        "duration_ms": 100.0,
    })
    return trcx


@when("写入一条 tool_call 事件", target_fixture="trcx")
def when_write_tool_call(trcx):
    trcx["writer"].write({
        "type": "tool_call",
        "round": 1,
        "tool": "indicator_calc",
        "input": {"name": "RSI"},
        "output": {"value": 35.2},
        "duration_ms": 1.2,
    })
    return trcx


@when("调用 decision_to_dict", target_fixture="trcx")
def when_decision_to_dict(trcx):
    trcx["result"] = decision_to_dict(trcx["decision"])
    return trcx


@when("执行回测", target_fixture="trcx")
def when_run_backtest(trcx):
    config = BacktestConfig(
        data=trcx["df"],
        symbol="AAPL",
        strategy_prompt=trcx.get("strategy", "test"),
        risk=RiskConfig(max_position_pct=1.0),
    )
    runner = Runner()
    trcx["result"] = runner.run(config, trcx["agent"])
    return trcx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse("JSONL 文件应有 {n:d} 行"))
def then_line_count(trcx, n):
    lines = _read_jsonl(trcx["path"])
    assert len(lines) == n


@then("每行应为合法 JSON")
def then_valid_json(trcx):
    lines = _read_jsonl(trcx["path"])
    assert all(isinstance(line, dict) for line in lines)


@then('每行应包含 "type" 和 "ts" 字段')
def then_has_type_ts(trcx):
    for line in _read_jsonl(trcx["path"]):
        assert "type" in line
        assert "ts" in line


@then("该事件的 bar_index 应为 5")
def then_bar_index_5(trcx):
    lines = _read_jsonl(trcx["path"])
    assert lines[-1]["bar_index"] == 5


@then(parsers.parse('该事件应包含 "{field}" 字段'))
def then_event_has_field(trcx, field):
    lines = _read_jsonl(trcx["path"])
    assert field in lines[-1], f"Missing field '{field}' in {lines[-1]}"


@then(parsers.parse('结果应包含 "{field}" 字段'))
def then_result_has_field(trcx, field):
    assert field in trcx["result"], f"Missing field '{field}'"


@then("workspace 应包含 trace.jsonl")
def then_has_trace(trcx):
    ws = trcx["result"].workspace_path
    assert os.path.isfile(os.path.join(ws, "trace.jsonl"))


@then(parsers.parse('trace.jsonl 应包含 "{event_type}" 类型事件'))
def then_trace_has_type(trcx, event_type):
    ws = trcx["result"].workspace_path
    lines = _read_jsonl(Path(ws) / "trace.jsonl")
    types = {line["type"] for line in lines}
    assert event_type in types, f"Missing type '{event_type}', found: {types}"


@then(parsers.parse('decisions.jsonl 每行应包含 "{field}"'))
def then_decisions_has_field(trcx, field):
    ws = trcx["result"].workspace_path
    lines = _read_jsonl(Path(ws) / "decisions.jsonl")
    assert len(lines) > 0
    for line in lines:
        assert field in line, f"Missing field '{field}' in decision: {line.keys()}"
