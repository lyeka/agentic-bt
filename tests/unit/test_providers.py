"""
[INPUT]: pytest, pathlib, unittest.mock, agent.providers
[OUTPUT]: provider 单测（图片编译/不支持媒体/stream/AnthropicProvider 编解码）
[POS]: tests/ 单测层，验证 provider 编解码行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from athenaclaw.llm.messages import AttachmentRef, TurnInput, build_user_message
from athenaclaw.llm.providers import AnthropicProvider, OpenAIChatProvider, UnsupportedMediaError


def test_openai_provider_compiles_image_ref_to_data_url(tmp_path: Path):
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image")
    provider = OpenAIChatProvider(client=MagicMock())

    message = build_user_message(
        TurnInput(
            text="请看这张图",
            attachments=(
                AttachmentRef(
                    kind="image",
                    path=str(image_path),
                    mime_type="image/jpeg",
                    width=100,
                    height=50,
                ),
            ),
        ),
        date_str="2026-03-11",
    )

    compiled = provider.compile_messages([message])

    assert compiled[0]["role"] == "user"
    assert compiled[0]["content"][0]["type"] == "text"
    assert compiled[0]["content"][1]["type"] == "image_url"
    assert compiled[0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert compiled[0]["content"][1]["image_url"]["detail"] == "low"


def test_openai_provider_rejects_unimplemented_media(tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"fake-audio")
    provider = OpenAIChatProvider(client=MagicMock())

    message = build_user_message(
        TurnInput(
            attachments=(
                AttachmentRef(
                    kind="audio",
                    path=str(audio_path),
                    mime_type="audio/mpeg",
                ),
            ),
        ),
        date_str="2026-03-11",
    )

    with pytest.raises(UnsupportedMediaError):
        provider.compile_messages([message])


def test_openai_provider_preserves_reasoning_content_on_assistant_tool_call():
    provider = OpenAIChatProvider(client=MagicMock())

    compiled = provider.compile_messages([
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "先读 memory",
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {
                        "name": "read",
                        "arguments": "{\"path\":\"memory.md\"}",
                    },
                }
            ],
        }
    ])

    assert compiled[0]["role"] == "assistant"
    assert compiled[0]["reasoning_content"] == "先读 memory"
    assert compiled[0]["tool_calls"][0]["function"]["name"] == "read"


def test_openai_provider_backfills_empty_reasoning_content_for_tool_calls():
    provider = OpenAIChatProvider(client=MagicMock())

    compiled = provider.compile_messages([
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {
                        "name": "portfolio",
                        "arguments": "{\"action\":\"get\"}",
                    },
                }
            ],
        }
    ])

    assert compiled[0]["role"] == "assistant"
    assert compiled[0]["reasoning_content"] == ""
    assert compiled[0]["tool_calls"][0]["function"]["name"] == "portfolio"


# ─────────────────────────────────────────────────────────────────────────────
# OpenAIChatProvider.stream
# ─────────────────────────────────────────────────────────────────────────────

def _make_delta(*, content=None, tool_calls=None, reasoning_content=None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    delta.reasoning_content = reasoning_content
    delta.model_extra = None
    return delta


def _make_chunk(*, delta=None, finish_reason=None, usage_total_tokens=None):
    chunk = MagicMock()
    if delta is not None:
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason
        chunk.choices = [choice]
    else:
        chunk.choices = []
    if usage_total_tokens is not None:
        usage = MagicMock()
        usage.total_tokens = usage_total_tokens
        chunk.usage = usage
    else:
        chunk.usage = None
    return chunk


def test_openai_provider_stream_calls_on_chunk_and_aggregates_content():
    client = MagicMock()
    client.chat.completions.create.return_value = [
        _make_chunk(delta=_make_delta(content="先看")),
        _make_chunk(delta=_make_delta(content="持仓")),
        _make_chunk(delta=_make_delta(), finish_reason="stop", usage_total_tokens=123),
    ]
    provider = OpenAIChatProvider(client=client)

    received: list[str] = []
    result = provider.stream(
        model="test-model",
        messages=[{"role": "user", "content": "帮我看下持仓"}],
        on_chunk=received.append,
    )

    assert received == ["先看", "持仓"]
    assert result.assistant_message["content"] == "先看持仓"
    assert result.finish_reason == "stop"
    assert result.usage_total_tokens == 123

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}


def test_openai_provider_stream_aggregates_tool_calls():
    client = MagicMock()
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "tc1"
    tc_delta.function = MagicMock()
    tc_delta.function.name = "portfolio"
    tc_delta.function.arguments = '{"action":'

    tc_delta2 = MagicMock()
    tc_delta2.index = 0
    tc_delta2.id = None
    tc_delta2.function = MagicMock()
    tc_delta2.function.name = None
    tc_delta2.function.arguments = '"get"}'

    client.chat.completions.create.return_value = [
        _make_chunk(delta=_make_delta(tool_calls=[tc_delta])),
        _make_chunk(delta=_make_delta(tool_calls=[tc_delta2]), finish_reason="tool_calls"),
    ]
    provider = OpenAIChatProvider(client=client)

    result = provider.stream(
        model="test-model",
        messages=[{"role": "user", "content": "查一下持仓"}],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "portfolio"
    assert result.tool_calls[0].arguments == '{"action":"get"}'
    assert result.assistant_message["tool_calls"][0]["function"]["name"] == "portfolio"


# ─────────────────────────────────────────────────────────────────────────────
# AnthropicProvider
# ─────────────────────────────────────────────────────────────────────────────

def _anthropic_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _anthropic_tool_use_block(*, id: str, name: str, input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input
    return block


def _anthropic_response(*, blocks, stop_reason="end_turn", input_tokens=10, output_tokens=5):
    response = MagicMock()
    response.content = blocks
    response.stop_reason = stop_reason
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response.usage = usage
    return response


def test_anthropic_provider_complete_maps_text_response_to_openai_shape():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response(
        blocks=[_anthropic_text_block("你好")],
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=5,
    )
    provider = AnthropicProvider(client=client)

    result = provider.complete(
        model="claude-test",
        messages=[
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好吗"},
        ],
    )

    assert result.assistant_message == {"role": "assistant", "content": "你好"}
    assert result.finish_reason == "stop"
    assert result.tool_calls == []
    assert result.usage_total_tokens == 15

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "你是助手"
    assert kwargs["messages"][0]["role"] == "user"


def test_anthropic_provider_complete_maps_tool_use_to_openai_shape():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response(
        blocks=[_anthropic_tool_use_block(id="tu1", name="portfolio", input={"action": "get"})],
        stop_reason="tool_use",
    )
    provider = AnthropicProvider(client=client)

    result = provider.complete(
        model="claude-test",
        messages=[{"role": "user", "content": "查一下持仓"}],
        tools=[{
            "type": "function",
            "function": {
                "name": "portfolio",
                "description": "查询持仓",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "tu1"
    assert result.tool_calls[0].name == "portfolio"
    assert json.loads(result.tool_calls[0].arguments) == {"action": "get"}
    assert result.assistant_message["tool_calls"][0]["function"]["name"] == "portfolio"

    sent_tools = client.messages.create.call_args.kwargs["tools"]
    assert sent_tools[0]["name"] == "portfolio"
    assert sent_tools[0]["input_schema"] == {"type": "object", "properties": {}}


def test_anthropic_provider_encodes_tool_result_message_as_user_tool_result_block():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response(blocks=[_anthropic_text_block("ok")])
    provider = AnthropicProvider(client=client)

    provider.complete(
        model="claude-test",
        messages=[
            {"role": "user", "content": "查一下持仓"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tu1",
                        "type": "function",
                        "function": {"name": "portfolio", "arguments": '{"action":"get"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tu1", "content": '{"cash": 100}'},
        ],
    )

    sent_messages = client.messages.create.call_args.kwargs["messages"]
    assert sent_messages[1]["role"] == "assistant"
    assert sent_messages[1]["content"][0]["type"] == "tool_use"
    assert sent_messages[2]["role"] == "user"
    assert sent_messages[2]["content"][0]["type"] == "tool_result"
    assert sent_messages[2]["content"][0]["tool_use_id"] == "tu1"
    assert sent_messages[2]["content"][0]["content"] == '{"cash": 100}'


def test_anthropic_provider_encodes_image_ref_as_base64_block(tmp_path: Path):
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image")
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response(blocks=[_anthropic_text_block("ok")])
    provider = AnthropicProvider(client=client)

    message = build_user_message(
        TurnInput(
            text="请看这张图",
            attachments=(
                AttachmentRef(kind="image", path=str(image_path), mime_type="image/jpeg", width=1, height=1),
            ),
        ),
        date_str="2026-03-11",
    )

    provider.complete(model="claude-test", messages=[message])

    sent_messages = client.messages.create.call_args.kwargs["messages"]
    blocks = sent_messages[0]["content"]
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "image"
    assert blocks[1]["source"]["type"] == "base64"
    assert blocks[1]["source"]["media_type"] == "image/jpeg"


def test_anthropic_provider_stream_calls_on_chunk_and_returns_final_usage():
    client = MagicMock()
    stream_ctx = MagicMock()
    stream_ctx.text_stream = ["先看", "持仓"]
    stream_ctx.get_final_message.return_value = _anthropic_response(
        blocks=[_anthropic_text_block("先看持仓")],
        input_tokens=7,
        output_tokens=3,
    )
    stream_cm = MagicMock()
    stream_cm.__enter__.return_value = stream_ctx
    stream_cm.__exit__.return_value = False
    client.messages.stream.return_value = stream_cm
    provider = AnthropicProvider(client=client)

    received: list[str] = []
    result = provider.stream(
        model="claude-test",
        messages=[{"role": "user", "content": "帮我看下持仓"}],
        on_chunk=received.append,
    )

    assert received == ["先看", "持仓"]
    assert result.assistant_message["content"] == "先看持仓"
    assert result.usage_total_tokens == 10


def test_anthropic_provider_requires_sdk_when_no_client_and_import_fails(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no anthropic")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        AnthropicProvider(api_key="test")
