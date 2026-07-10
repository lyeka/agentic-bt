"""
[INPUT]: pytest, unittest.mock, athenaclaw.llm.retry, athenaclaw.llm.providers
[OUTPUT]: call_with_retry 单测（重试成功/耗尽/temperature 降级）
[POS]: tests/ 单测层，验证 llm/retry.py 的共享退避策略
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from athenaclaw.llm.providers import LLMResult
from athenaclaw.llm.retry import call_with_retry


def test_call_with_retry_succeeds_after_transient_errors(monkeypatch):
    monkeypatch.setattr("athenaclaw.llm.retry.time.sleep", lambda _s: None)
    provider = MagicMock()
    ok_result = LLMResult(assistant_message={"role": "assistant", "content": "ok"}, finish_reason="stop")
    provider.complete.side_effect = [RuntimeError("boom"), RuntimeError("boom"), ok_result]

    result = call_with_retry(
        provider=provider, model="m", messages=[], tools=None, attempts=3, base_delay=0.01,
    )

    assert result is ok_result
    assert provider.complete.call_count == 3


def test_call_with_retry_reraises_after_exhaustion(monkeypatch):
    monkeypatch.setattr("athenaclaw.llm.retry.time.sleep", lambda _s: None)
    provider = MagicMock()
    provider.complete.side_effect = RuntimeError("persistent failure")
    events: list[tuple[str, dict]] = []

    with pytest.raises(RuntimeError, match="persistent failure"):
        call_with_retry(
            provider=provider, model="m", messages=[], tools=None, attempts=3, base_delay=0.01,
            emit_fn=lambda e, d: events.append((e, d)), emit_prefix="llm",
            reraise_on_exhaustion=True,
        )

    assert provider.complete.call_count == 3
    error_events = [d for e, d in events if e == "llm.call.error"]
    assert len(error_events) == 3


def test_call_with_retry_returns_none_after_exhaustion_when_not_reraising(monkeypatch):
    monkeypatch.setattr("athenaclaw.llm.retry.time.sleep", lambda _s: None)
    provider = MagicMock()
    provider.complete.side_effect = RuntimeError("persistent failure")

    result = call_with_retry(
        provider=provider, model="m", messages=[], tools=None, attempts=2, base_delay=0.01,
        reraise_on_exhaustion=False,
    )

    assert result is None
    assert provider.complete.call_count == 2


def test_call_with_retry_downgrades_temperature_without_delay(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("athenaclaw.llm.retry.time.sleep", lambda s: sleeps.append(s))
    provider = MagicMock()
    ok_result = LLMResult(assistant_message={"role": "assistant", "content": "ok"}, finish_reason="stop")

    calls: list[dict] = []

    def _complete(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("invalid temperature: only 1 is allowed")
        return ok_result

    provider.complete.side_effect = _complete
    events: list[tuple[str, dict]] = []

    result = call_with_retry(
        provider=provider, model="m", messages=[], tools=None, temperature=0.5,
        attempts=3, base_delay=0.01,
        emit_fn=lambda e, d: events.append((e, d)), emit_prefix="llm",
    )

    assert result is ok_result
    assert calls[0]["temperature"] == 0.5
    assert calls[1]["temperature"] is None
    assert sleeps == []
    retry_events = [d for e, d in events if e == "llm.call.retry"]
    assert len(retry_events) == 1
    assert retry_events[0]["reason"] == "temperature_incompatible"


def test_call_with_retry_passes_timeout_only_when_set():
    provider = MagicMock()
    ok_result = LLMResult(assistant_message={"role": "assistant", "content": "ok"}, finish_reason="stop")
    provider.complete.return_value = ok_result

    call_with_retry(provider=provider, model="m", messages=[], tools=None, timeout=None)
    assert "timeout" not in provider.complete.call_args.kwargs

    call_with_retry(provider=provider, model="m", messages=[], tools=None, timeout=30.0)
    assert provider.complete.call_args.kwargs["timeout"] == 30.0
