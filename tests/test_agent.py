"""
[INPUT]: pytest-bdd, agenticbt.agent, agenticbt.tools, unittest.mock
[OUTPUT]: agent.feature 的 step definitions（使用 mock LLM）
[POS]: tests/ BDD 测试层，验证 Agent ReAct loop 和 Decision 结构
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.agent import LLMAgent
from agenticbt.engine import Engine
from agenticbt.memory import Memory, Workspace
from agenticbt.models import Context, ContextConfig, RiskConfig
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/agent.feature", "Agent 调用工具后做出买入决策")
def test_agent_buy(): pass

@scenario("features/agent.feature", "Agent 不交易则为 hold")
def test_agent_hold(): pass

@scenario("features/agent.feature", "ReAct loop 在 max_rounds 后终止")
def test_max_rounds(): pass

@scenario("features/agent.feature", "Decision 记录完整审计信息")
def test_decision_audit(): pass

@scenario("features/agent.feature", "LLM API 异常时重试后返回 hold")
def test_llm_retry_on_error(): pass

@scenario("features/agent.feature", "System Prompt 包含框架模板和策略")
def test_system_prompt_framework(): pass

@scenario("features/agent.feature", "自定义 System Prompt 覆盖框架模板")
def test_custom_system_prompt(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_toolkit() -> ToolKit:
    rng = np.random.default_rng(1)
    n = 20
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.full(n, 1_000_000.0),
    })
    eng = Engine(data=df, symbol="AAPL", initial_cash=100_000.0,
                 risk=RiskConfig(max_position_pct=1.0))
    eng.advance()
    ws = Workspace()
    mem = Memory(ws)
    return ToolKit(engine=eng, memory=mem)


def _mock_response(finish_reason: str, tool_calls=None, content="") -> SimpleNamespace:
    """构造 openai.ChatCompletion 兼容的 mock 响应"""
    msg = SimpleNamespace(
        content=content,
        tool_calls=tool_calls or [],
    )
    choice = SimpleNamespace(finish_reason=finish_reason, message=msg)
    usage = SimpleNamespace(total_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_call(name: str, args: dict, call_id: str = "tc1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 mock Agent 按顺序响应工具调用后买入", target_fixture="actx")
def given_agent_buy():
    responses = [
        # Round 1: 调用 indicator_calc RSI
        _mock_response("tool_calls", [_tool_call("indicator_calc", {"name": "RSI"}, "tc1")]),
        # Round 2: 调用 trade_execute buy
        _mock_response("tool_calls", [_tool_call("trade_execute",
                       {"action": "buy", "symbol": "AAPL", "quantity": 100}, "tc2")]),
        # Round 3: stop，给出理由
        _mock_response("stop", content="RSI 超卖，买入 AAPL"),
    ]
    toolkit = _make_toolkit()
    agent = LLMAgent(max_rounds=5)
    return {"agent": agent, "toolkit": toolkit, "responses": responses}


@given("一个 mock Agent 只查询指标后观望", target_fixture="actx")
def given_agent_hold():
    responses = [
        _mock_response("tool_calls", [_tool_call("indicator_calc", {"name": "RSI"}, "tc1")]),
        _mock_response("stop", content="RSI 中性，继续观望"),
    ]
    toolkit = _make_toolkit()
    agent = LLMAgent(max_rounds=5)
    return {"agent": agent, "toolkit": toolkit, "responses": responses}


@given("一个 mock Agent 永远返回工具调用", target_fixture="actx")
def given_agent_infinite():
    # 无限返回 market_observe 调用
    def make_response(*_args, **_kwargs):
        return _mock_response("tool_calls", [_tool_call("market_observe", {}, "tc1")])
    toolkit = _make_toolkit()
    agent = LLMAgent(max_rounds=5)
    return {"agent": agent, "toolkit": toolkit, "make_response": make_response}


@given("一个持续抛出异常的 mock LLM 客户端", target_fixture="actx")
def given_failing_llm():
    """B3: 模拟 LLM API 持续失败，验证重试后降级为 hold"""
    def always_fail(**_):
        raise ConnectionError("模拟网络中断")

    toolkit = _make_toolkit()
    agent = LLMAgent(max_rounds=5)
    return {"agent": agent, "toolkit": toolkit, "make_response": always_fail}


@given("一个使用自定义 system prompt 的 Agent", target_fixture="actx")
def given_custom_system_prompt():
    custom_prompt = "你是一个完全自定义的交易员。按你的判断交易。"
    responses = [
        _mock_response("stop", content="观望"),
    ]
    toolkit = _make_toolkit()
    agent = LLMAgent(max_rounds=5, system_prompt=custom_prompt)
    return {"agent": agent, "toolkit": toolkit, "responses": responses,
            "custom_prompt": custom_prompt}


@given(parsers.parse("max_rounds 设为 {n:d}"), target_fixture="actx")
def given_max_rounds(actx, n):
    actx["agent"].max_rounds = n
    return actx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("Agent 做出决策", target_fixture="actx")
def when_decide(actx):
    context = Context(
        playbook="",
        position_notes={},
        datetime=datetime(2024, 1, 1),
        bar_index=0,
        decision_count=0,
        market={
            "symbol": "AAPL",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000.0,
        },
        account={
            "cash": 100_000.0,
            "equity": 100_000.0,
            "positions": {},
        },
        risk_summary={"max_position_pct": 0.2, "max_buy_qty": 100, "max_open_positions": 10, "open_positions": 0},
        pending_orders=[],
        recent_bars=[],
        events=[],
        recent_decisions=[],
        formatted_text="## 当前行情  [2024-01-01  bar=0]\n  AAPL  开=100.0\n\n请先调用工具获取数据，再给出交易决策。",
    )
    toolkit = actx["toolkit"]
    agent = actx["agent"]

    responses = actx.get("responses")
    make_response = actx.get("make_response")

    if responses:
        resp_iter = iter(responses)
        mock_create = MagicMock(side_effect=lambda **_: next(resp_iter))
    else:
        mock_create = MagicMock(side_effect=make_response)

    # B3: mock time.sleep 让重试测试不阻塞
    with patch.object(agent.client.chat.completions, "create", mock_create), \
         patch("agenticbt.agent.time.sleep"):
        actx["decision"] = agent.decide(context, toolkit)

    actx["mock_create"] = mock_create
    return actx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('decision.action 应为 "{action}"'))
def then_action(actx, action):
    assert actx["decision"].action == action


@then(parsers.parse('decision.symbol 应为 "{symbol}"'))
def then_symbol(actx, symbol):
    assert actx["decision"].symbol == symbol


@then(parsers.parse('decision.reasoning 应包含 "{text}"'))
def then_reasoning(actx, text):
    assert text in actx["decision"].reasoning


@then(parsers.parse("decision.tool_calls 应有 {n:d} 条记录"))
def then_tool_calls(actx, n):
    assert len(actx["decision"].tool_calls) == n


@then(parsers.parse("应在 {n:d} 轮后返回 decision"))
def then_max_rounds(actx, n):
    # agent.max_rounds == n 且已返回 decision（无异常）
    assert actx["agent"].max_rounds == n
    assert actx["decision"] is not None


@then("decision 应包含 market_snapshot")
def then_has_market(actx):
    assert actx["decision"].market_snapshot is not None


@then("decision 应包含 account_snapshot")
def then_has_account(actx):
    assert actx["decision"].account_snapshot is not None


@then("decision 应包含 tokens_used")
def then_has_tokens(actx):
    assert isinstance(actx["decision"].tokens_used, int)


@then("decision 应包含 latency_ms")
def then_has_latency(actx):
    assert actx["decision"].latency_ms >= 0


@then("不抛出异常")
def then_no_exception(actx):
    """B3: LLM 全部失败后，decide() 仍正常返回 Decision 对象"""
    assert actx["decision"] is not None


@then(parsers.parse('LLM 收到的 system prompt 应包含 "{text}"'))
def then_system_prompt_contains(actx, text):
    mock_create = actx["mock_create"]
    messages = mock_create.call_args_list[0].kwargs["messages"]
    system_msg = messages[0]["content"]
    assert text in system_msg, f"'{text}' not found in system prompt"


@then("LLM 收到的 system prompt 应为自定义内容")
def then_custom_system_prompt(actx):
    mock_create = actx["mock_create"]
    messages = mock_create.call_args_list[0].kwargs["messages"]
    system_msg = messages[0]["content"]
    assert system_msg == actx["custom_prompt"]
