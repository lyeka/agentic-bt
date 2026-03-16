"""
[INPUT]: pytest, pathlib, unittest.mock, agent.providers
[OUTPUT]: provider 单测（图片编译/不支持媒体）
[POS]: tests/ 单测层，验证 provider 编解码行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from athenaclaw.llm.messages import AttachmentRef, TurnInput, build_user_message
from athenaclaw.llm.providers import OpenAIChatProvider, UnsupportedMediaError


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
