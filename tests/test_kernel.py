"""
[INPUT]: pytest-bdd, agent.kernel, agent.providers (message_to_dict), unittest.mock
[OUTPUT]: kernel.feature step definitions（Mock LLM）
[POS]: tests/ BDD 测试层，验证 Kernel ReAct loop / wire·emit / Session / boot / soul 刷新
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agent.kernel import Kernel, Session, WORKSPACE_GUIDE
from agent.providers import message_to_dict


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

@scenario("features/kernel.feature", "boot 只有 soul 和 workspace 指南")
def test_boot_soul_only(): pass

@scenario("features/kernel.feature", "soul 变更后 system prompt 自动刷新")
def test_soul_refresh(): pass

@scenario("features/kernel.feature", "system prompt 包含 workspace 使用指南")
def test_workspace_guide(): pass

@scenario("features/kernel.feature", "system prompt 不包含 memory 文件内容")
def test_memory_not_in_prompt(): pass

@scenario("features/kernel.feature", "turn 在 user 消息中注入当前日期")
def test_turn_date_injection(): pass

@scenario("features/kernel.feature", "token 超限时自动压缩")
def test_auto_compact(): pass

@scenario("features/kernel.feature", "finish_reason 为 length 时压缩重试")
def test_overflow_compact(): pass

@scenario("features/kernel.feature", "Session 持久化包含 summary")
def test_session_summary_persist(): pass


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


def test_msg_to_dict_preserves_reasoning_content():
    msg = SimpleNamespace(
        role="assistant",
        content=None,
        tool_calls=[_tool_call("echo", {"text": "hi"})],
        reasoning_content="internal reasoning",
        model_extra=None,
    )

    result = message_to_dict(msg)

    assert result["reasoning_content"] == "internal reasoning"


def test_kernel_emits_llm_call_error_on_provider_exception():
    kernel = Kernel()
    session = Session()
    seen: list[dict] = []
    kernel.wire("llm.call.error", lambda _e, data: seen.append(data))
    kernel.provider = MagicMock()
    kernel.provider.complete.side_effect = RuntimeError("provider 400")

    with pytest.raises(RuntimeError, match="provider 400"):
        kernel.turn("hello", session)

    assert seen
    assert seen[0]["error_type"] == "RuntimeError"
    assert "provider 400" in seen[0]["error"]


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


# ─────────────────────────────────────────────────────────────────────────────
# Boot 上下文注入
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse('工作区含 soul.md 内容 "{content}"'), target_fixture="kctx")
def given_workspace_soul(kctx, content, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "soul.md").write_text(content, encoding="utf-8")
    kctx["workspace"] = ws
    kctx["kernel"] = Kernel()
    return kctx


@given(parsers.parse('工作区含 memory.md 内容 "{content}"'), target_fixture="kctx")
def given_workspace_memory(kctx, content):
    mem = kctx["workspace"] / "memory.md"
    mem.write_text(content, encoding="utf-8")
    return kctx


@when("Kernel boot", target_fixture="kctx")
def when_kernel_boot(kctx):
    kctx["kernel"].boot(kctx["workspace"], skill_roots=[])
    return kctx


@when(parsers.parse('修改 soul.md 为 "{content}"'), target_fixture="kctx")
def when_update_soul(kctx, content):
    (kctx["workspace"] / "soul.md").write_text(content, encoding="utf-8")
    return kctx


@when("重新组装 system prompt", target_fixture="kctx")
def when_reassemble_prompt(kctx):
    kctx["kernel"]._assemble_system_prompt()
    return kctx


@then(parsers.parse('system prompt 包含 "{text}"'))
def then_system_prompt_contains(kctx, text):
    assert text in kctx["kernel"]._system_prompt


@then(parsers.parse('system prompt 不包含 "{text}"'))
def then_system_prompt_not_contains(kctx, text):
    assert text not in kctx["kernel"]._system_prompt


@then("Session 历史中用户消息包含日期前缀")
def then_user_message_has_date(kctx):
    import re
    user_msg = kctx["session"].history[0]["content"]
    assert re.match(r"\[\d{4}-\d{2}-\d{2}\]\n", user_msg)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-compact / Overflow / Session summary
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 context_window 极小的 Kernel", target_fixture="kctx")
def given_tiny_context_kernel(kctx):
    kernel = Kernel(context_window=200, compact_recent_turns=1)
    kctx["kernel"] = kernel
    kctx["session"] = Session()
    kctx["events"] = []
    kernel.wire("context.*", lambda e, d: kctx["events"].append((e, d)))
    # compact_history 调用 LLM 做压缩（1次） + turn 本身的 LLM 调用（1次）
    kctx["responses"] = [
        _mock_response("stop", content="压缩摘要"),  # compact LLM
        _mock_response("stop", content="ok"),          # turn LLM
    ]
    return kctx


@given("已有大量历史消息", target_fixture="kctx")
def given_large_history(kctx):
    for i in range(20):
        kctx["session"].history.append({"role": "user", "content": f"msg{i} " * 50})
        kctx["session"].history.append({"role": "assistant", "content": f"reply{i} " * 50})
    kctx["history_count_before"] = len(kctx["session"].history)
    return kctx


@then("触发 auto compact 事件")
def then_auto_compact_event(kctx):
    events = kctx.get("events", [])
    assert any(e == "context.compacted" and d.get("trigger") == "auto" for e, d in events)


@then("Session 历史消息数少于压缩前")
def then_session_smaller(kctx):
    assert len(kctx["session"].history) < kctx["history_count_before"]


@given("LLM 先返回 length 再返回正常回复", target_fixture="kctx")
def given_llm_length_then_stop(kctx):
    kctx["kernel"] = Kernel()
    kctx["session"] = Session()
    kctx["events"] = []
    kctx["kernel"].wire("context.*", lambda e, d: kctx["events"].append((e, d)))
    # 先填充一些历史
    for i in range(5):
        kctx["session"].history.append({"role": "user", "content": f"history{i}"})
        kctx["session"].history.append({"role": "assistant", "content": f"reply{i}"})
    kctx["responses"] = [
        _mock_response("length", content="截断..."),   # turn round 1 → overflow
        _mock_response("stop", content="压缩摘要"),     # compact LLM
        _mock_response("stop", content="重试成功"),     # turn round 2 → stop
    ]
    return kctx


@then("触发 overflow compact 事件")
def then_overflow_compact_event(kctx):
    events = kctx.get("events", [])
    assert any(e == "context.compacted" and d.get("trigger") == "overflow" for e, d in events)


@when("设置 summary 并保存 Session", target_fixture="kctx")
def when_set_summary_and_save(kctx, tmp_path):
    session = kctx["session"]
    session.summary = "## 会话意图\n测试持久化"
    path = tmp_path / "session.json"
    session.save(path)
    kctx["session_path"] = path
    return kctx


@then("加载的 Session 包含 summary")
def then_loaded_session_has_summary(kctx):
    loaded = Session.load(kctx["session_path"])
    assert loaded.summary == "## 会话意图\n测试持久化"
