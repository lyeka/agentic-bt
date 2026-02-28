"""
[INPUT]: pytest-bdd, agent.kernel, unittest.mock
[OUTPUT]: kernel.feature step definitions（Mock LLM）
[POS]: tests/ BDD 测试层，验证 Kernel ReAct loop / wire·emit / Session
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pytest_bdd import given, parsers, scenario, then, when

from agent.kernel import Kernel, Session


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/kernel.feature", "基础对话")
def test_basic_chat(): pass

@scenario("features/kernel.feature", "多轮对话历史保持")
def test_multi_turn_history(): pass

@scenario("features/kernel.feature", "ReAct loop 执行工具")
def test_react_tool(): pass

@scenario("features/kernel.feature", "声明式管道触发")
def test_wire_emit(): pass

@scenario("features/kernel.feature", "最大轮次保护")
def test_max_rounds(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_response(finish_reason, tool_calls=None, content=""):
    """构造 openai.ChatCompletion 兼容的 mock 响应"""
    msg = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls or [],
    )
    choice = SimpleNamespace(finish_reason=finish_reason, message=msg)
    usage = SimpleNamespace(total_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_call(name, args, call_id="tc1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Background
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 Mock LLM 客户端", target_fixture="kctx")
def given_mock_llm():
    return {"responses": [], "echo_calls": 0, "pipe_calls": 0}


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 Kernel", target_fixture="kctx")
def given_kernel(kctx):
    kctx["kernel"] = Kernel()
    kctx["session"] = Session()
    kctx["responses"] = [_mock_response("stop", content="你好！我是投资助手。")]
    return kctx


@given("一个注册了 echo 工具的 Kernel", target_fixture="kctx")
def given_kernel_with_echo(kctx):
    kernel = Kernel()

    def echo_handler(args):
        kctx["echo_calls"] = kctx.get("echo_calls", 0) + 1
        return {"echo": args.get("text", "")}

    kernel.tool(
        name="echo",
        description="回声测试",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": [],
        },
        handler=echo_handler,
    )
    kctx["kernel"] = kernel
    kctx["session"] = Session()
    return kctx


@given("LLM 先调用 echo 工具再结束", target_fixture="kctx")
def given_llm_echo_then_stop(kctx):
    kctx["responses"] = [
        _mock_response("tool_calls", [_tool_call("echo", {"text": "hello"})]),
        _mock_response("stop", content="echo 完成"),
    ]
    return kctx


@given(parsers.parse('注册了 "{event}" 管道'), target_fixture="kctx")
def given_wire_handler(kctx, event):
    def handler(_evt, _data):
        kctx["pipe_calls"] = kctx.get("pipe_calls", 0) + 1
    kctx["kernel"].wire(event, handler)
    return kctx


@given("LLM 永远返回工具调用", target_fixture="kctx")
def given_llm_infinite_tools(kctx):
    kctx["make_response"] = lambda **_: _mock_response(
        "tool_calls", [_tool_call("echo", {"text": "loop"})],
    )
    return kctx


@given(parsers.parse("max_rounds 设为 {n:d}"), target_fixture="kctx")
def given_max_rounds(kctx, n):
    kctx["kernel"].max_rounds = n
    return kctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('用户说 "{text}"'), target_fixture="kctx")
def when_user_says(kctx, text):
    kernel = kctx["kernel"]
    session = kctx["session"]

    responses = kctx.get("responses")
    make_response = kctx.get("make_response")

    if responses:
        resp_iter = iter(responses)
        mock_create = MagicMock(side_effect=lambda **_: next(resp_iter))
    else:
        mock_create = MagicMock(side_effect=make_response)

    with patch.object(kernel.client.chat.completions, "create", mock_create):
        kctx["reply"] = kernel.turn(text, session)

    return kctx


@when(parsers.parse('用户依次说 "{text1}" 和 "{text2}"'), target_fixture="kctx")
def when_user_says_twice(kctx, text1, text2):
    kernel = kctx["kernel"]
    session = kctx["session"]

    responses = [
        _mock_response("stop", content="回复1"),
        _mock_response("stop", content="回复2"),
    ]
    resp_iter = iter(responses)
    mock_create = MagicMock(side_effect=lambda **_: next(resp_iter))

    with patch.object(kernel.client.chat.completions, "create", mock_create):
        kernel.turn(text1, session)
        kctx["reply"] = kernel.turn(text2, session)

    return kctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("返回非空回复")
def then_non_empty_reply(kctx):
    assert kctx["reply"]
    assert len(kctx["reply"]) > 0


@then(parsers.parse("Session 包含 {n:d} 条消息"))
def then_session_has_n_messages(kctx, n):
    assert len(kctx["session"].history) == n


@then(parsers.parse("echo 工具被调用 {n:d} 次"))
def then_echo_called(kctx, n):
    assert kctx.get("echo_calls", 0) == n


@then(parsers.parse("管道被触发 {n:d} 次"))
def then_pipe_triggered(kctx, n):
    assert kctx.get("pipe_calls", 0) == n
