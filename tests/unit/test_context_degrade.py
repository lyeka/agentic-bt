"""
[INPUT]: pytest, unittest.mock, athenaclaw.llm.context
[OUTPUT]: compact_history 降级路径单测（LLM 压缩失败不丢历史）
[POS]: tests/ 单测层，验证 context.py 的确定性降级不会静默丢弃对话历史
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from unittest.mock import MagicMock

from athenaclaw.llm.context import compact_history


def _make_turn(user_text: str, assistant_text: str) -> list[dict]:
    return [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]


def test_compact_history_degrades_to_deterministic_summary_on_llm_failure():
    provider = MagicMock()
    provider.complete.side_effect = RuntimeError("provider unavailable")

    history: list[dict] = []
    for i in range(6):
        history.extend(_make_turn(f"用户消息{i}", f"助手回复{i}"))

    result = compact_history(provider=provider, model="test", history=history, recent_turns=2)

    assert result.degraded is True
    assert result.summary
    assert "用户消息0" in result.summary
    assert result.compressed_count > 0
    assert result.retained_count > 0
    assert len(result.retained) + result.compressed_count == len(history)


def test_compact_history_not_degraded_on_llm_success():
    provider = MagicMock()
    ok = MagicMock()
    ok.assistant_message = {"role": "assistant", "content": "摘要文本"}
    provider.complete.return_value = ok

    history: list[dict] = []
    for i in range(6):
        history.extend(_make_turn(f"用户消息{i}", f"助手回复{i}"))

    result = compact_history(provider=provider, model="test", history=history, recent_turns=2)

    assert result.degraded is False
    assert result.summary == "摘要文本"
