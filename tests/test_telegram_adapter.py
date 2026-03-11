"""
[INPUT]: agent.adapters.telegram helpers
[OUTPUT]: Telegram adapter helper tests（渲染/配置解析）
[POS]: tests/ 单测层，验证 Telegram 渲染与 env 解析基础逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from agent.adapters.telegram import (
    _collect_attachments,
    _markdown_to_html,
    _message_text,
    _normalize_render_mode,
    _parse_allowed_user_ids,
    _parse_bool,
)


def test_parse_allowed_user_ids():
    assert _parse_allowed_user_ids("1, 2,3") == {"1", "2", "3"}
    assert _parse_allowed_user_ids("") == set()
    assert _parse_allowed_user_ids(None) == set()


def test_parse_bool_default():
    assert _parse_bool(None, default=False) is False
    assert _parse_bool(None, default=True) is True
    assert _parse_bool("true", default=False) is True
    assert _parse_bool("0", default=True) is False


def test_normalize_render_mode():
    assert _normalize_render_mode(None) == "html"
    assert _normalize_render_mode("markdown") == "markdown"
    assert _normalize_render_mode("plain") == "none"
    assert _normalize_render_mode("text") == "none"
    assert _normalize_render_mode("unknown") == "html"


def test_markdown_to_html_basic():
    text = (
        "## Title\n\n"
        "- item1\n"
        "- item2\n\n"
        "normal **bold** and *italic* and `code`\n\n"
        "```python\n"
        "print('x')\n"
        "```\n"
    )
    html = _markdown_to_html(text)
    assert "<b>Title</b>" in html
    assert "• item1" in html
    assert "<b>bold</b>" in html
    assert "<i>italic</i>" in html
    assert "<code>code</code>" in html
    assert "<pre><code>" in html and "</code></pre>" in html


def test_message_text_uses_caption_for_media_message():
    message = SimpleNamespace(text=None, caption="image caption")
    assert _message_text(message) == "image caption"


def test_collect_photo_attachment_downloads_to_state_dir(tmp_path: Path):
    class FakeTelegramFile:
        async def download_to_drive(self, custom_path: str) -> None:
            Path(custom_path).write_bytes(b"img")

    class FakeBot:
        async def get_file(self, file_id: str):
            assert file_id == "file-1"
            return FakeTelegramFile()

    message = SimpleNamespace(
        photo=[
            SimpleNamespace(file_id="file-1", file_unique_id="uniq-1", width=640, height=480, file_size=123),
        ],
        document=None,
        voice=None,
        audio=None,
    )

    async def _run():
        return await _collect_attachments(
            bot=FakeBot(),
            message=message,
            media_root=tmp_path,
            conversation_id="chat-1",
            message_id="msg-1",
        )

    attachments, error = asyncio.run(_run())
    assert error is None
    assert len(attachments) == 1
    assert attachments[0].kind == "image"
    assert attachments[0].path.endswith("image-uniq-1.jpg")
    assert Path(attachments[0].path).exists()


def test_collect_audio_attachment_returns_explicit_error(tmp_path: Path):
    message = SimpleNamespace(photo=None, document=None, voice=object(), audio=None)

    async def _run():
        return await _collect_attachments(
            bot=object(),
            message=message,
            media_root=tmp_path,
            conversation_id="chat-1",
            message_id="msg-1",
        )

    attachments, error = asyncio.run(_run())
    assert attachments == ()
    assert "音频" in error
