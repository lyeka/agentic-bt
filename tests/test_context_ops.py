"""
[INPUT]: pytest-bdd, agent.context_ops, types.SimpleNamespace
[OUTPUT]: context_ops.feature step definitions（fixture: coctx）
[POS]: tests/ BDD 测试层，验证上下文管理纯函数：token 估算/上下文统计/对话压缩
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from types import SimpleNamespace

from pytest_bdd import given, parsers, scenario, then, when

from agent.context_ops import (
    CompactResult,
    ContextInfo,
    compact_history,
    context_info,
    estimate_tokens,
)


FEATURE = "features/context_ops.feature"


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario(FEATURE, "空历史的 token 估算为零")
def test_empty_tokens(): pass

@scenario(FEATURE, "有消息历史的 token 估算大于零")
def test_nonempty_tokens(): pass

@scenario(FEATURE, "上下文统计包含正确的消息计数和使用率")
def test_context_info(): pass

@scenario(FEATURE, "太短的历史不压缩")
def test_short_no_compress(): pass

@scenario(FEATURE, "压缩对话历史返回摘要和最近消息")
def test_compress_returns_summary(): pass

@scenario(FEATURE, "压缩后最近消息保持原样")
def test_retained_unchanged(): pass

@scenario(FEATURE, "摘要包含结构化内容")
def test_summary_structured(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_client(summary_text: str = "## 会话意图\n测试摘要") -> object:
    """构造 mock LLM client，返回固定摘要"""
    msg = SimpleNamespace(content=summary_text)
    choice = SimpleNamespace(message=msg)
    response = SimpleNamespace(choices=[choice])
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: response,
            ),
        ),
    )
    return client


def _make_turn(user_text: str, assistant_text: str) -> list[dict]:
    """构造一个完整 user turn（user + assistant）"""
    return [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Background
# ─────────────────────────────────────────────────────────────────────────────

@given("一个空上下文环境", target_fixture="coctx")
def given_empty_ctx():
    return {"history": [], "client": _mock_client()}


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given(parsers.parse('一条 user 消息 "{text}"'), target_fixture="coctx")
def given_user_message(coctx, text):
    coctx["history"].append({"role": "user", "content": text})
    return coctx


@given(parsers.parse('一条 assistant 消息 "{text}"'), target_fixture="coctx")
def given_assistant_message(coctx, text):
    coctx["history"].append({"role": "assistant", "content": text})
    return coctx


@given(parsers.parse("{n:d} 轮完整对话"), target_fixture="coctx")
def given_n_turns(coctx, n):
    for i in range(n):
        coctx["history"].extend(_make_turn(f"用户消息{i+1}", f"助手回复{i+1}"))
    return coctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("估算空历史的 token", target_fixture="coctx")
def when_estimate_empty(coctx):
    coctx["tokens"] = estimate_tokens([])
    return coctx


@when("估算历史的 token", target_fixture="coctx")
def when_estimate_tokens(coctx):
    coctx["tokens"] = estimate_tokens(coctx["history"])
    return coctx


@when(parsers.parse("获取上下文统计（context_window {window:d}）"), target_fixture="coctx")
def when_get_context_info(coctx, window):
    coctx["info"] = context_info(coctx["history"], window)
    return coctx


@when(parsers.parse("压缩历史（recent_turns {n:d}）"), target_fixture="coctx")
def when_compact(coctx, n):
    result = compact_history(
        client=coctx["client"],
        model="test",
        history=coctx["history"],
        recent_turns=n,
    )
    coctx["compact_result"] = result
    # 保存原始最后 N 轮消息用于后续断言
    user_idxs = [i for i, m in enumerate(coctx["history"]) if m.get("role") == "user"]
    if len(user_idxs) > n:
        cut = user_idxs[-n]
        coctx["original_retained"] = coctx["history"][cut:]
    else:
        coctx["original_retained"] = list(coctx["history"])
    return coctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse("token 估算结果为 {n:d}"))
def then_tokens_equal(coctx, n):
    assert coctx["tokens"] == n


@then("token 估算结果大于 0")
def then_tokens_positive(coctx):
    assert coctx["tokens"] > 0


@then(parsers.parse("统计消息总数为 {n:d}"))
def then_info_message_count(coctx, n):
    assert coctx["info"].message_count == n


@then(parsers.parse("统计 user 消息数为 {n:d}"))
def then_info_user_count(coctx, n):
    assert coctx["info"].user_message_count == n


@then("统计使用率大于 0")
def then_info_usage_positive(coctx):
    assert coctx["info"].usage_pct > 0


@then(parsers.parse("压缩的消息数为 {n:d}"))
def then_compressed_count(coctx, n):
    assert coctx["compact_result"].compressed_count == n


@then(parsers.parse("保留的消息数为 {n:d}"))
def then_retained_count(coctx, n):
    assert coctx["compact_result"].retained_count == n


@then("压缩的消息数大于 0")
def then_compressed_positive(coctx):
    assert coctx["compact_result"].compressed_count > 0


@then("保留的消息数大于 0")
def then_retained_positive(coctx):
    assert coctx["compact_result"].retained_count > 0


@then("摘要非空")
def then_summary_nonempty(coctx):
    assert coctx["compact_result"].summary


@then(parsers.parse("最近 {n:d} 轮消息内容不变"))
def then_retained_unchanged(coctx, n):
    result: CompactResult = coctx["compact_result"]
    original = coctx["original_retained"]
    assert result.retained == original
