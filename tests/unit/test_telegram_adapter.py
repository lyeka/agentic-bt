"""
[INPUT]: athenaclaw.interfaces.telegram helpers
[OUTPUT]: Telegram adapter helper tests（渲染/配置解析）
[POS]: tests/ 单测层，验证 Telegram 渲染与 env 解析基础逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from athenaclaw.interfaces.telegram import (
    TelegramBackend,
    _collect_attachments,
    _handle_confirm_callback,
    _markdown_to_html,
    _message_text,
    _normalize_render_mode,
    _parse_confirm_callback,
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


def test_parse_confirm_callback():
    assert _parse_confirm_callback("confirm:123:456:y") == ("123:456", True)
    assert _parse_confirm_callback("confirm:123:n") == ("123", False)
    assert _parse_confirm_callback("other") is None


def test_telegram_backend_ask_confirm_unblocks_on_waiter_result():
    class FakeBot:
        async def send_message(self, chat_id: int, text: str, reply_markup=None):
            assert chat_id == 1001
            assert "确认操作" in text
            assert reply_markup is not None
            return SimpleNamespace(message_id=9)

    async def _run():
        waiters: dict[str, asyncio.Future] = {}
        backend = TelegramBackend(bot=FakeBot(), _confirm_waiters=waiters)
        task = asyncio.create_task(backend.ask_confirm("1001", "确认操作 soul.md?", timeout_sec=3))
        await asyncio.sleep(0)
        assert len(waiters) == 1
        fut = next(iter(waiters.values()))
        fut.set_result(True)
        return await task

    assert asyncio.run(_run()) is True


def test_handle_confirm_callback_resolves_waiter_and_updates_message():
    class FakeQuery:
        def __init__(self) -> None:
            self.data = "confirm:chat1:42:y"
            self.message = SimpleNamespace(text="确认操作 soul.md?")
            self.answers: list[str] = []
            self.edits: list[str] = []

        async def answer(self, text: str | None = None):
            self.answers.append(text or "")

        async def edit_message_text(self, text: str):
            self.edits.append(text)

    async def _run():
        query = FakeQuery()
        fut = asyncio.get_running_loop().create_future()
        waiters = {"chat1:42": fut}
        handled = await _handle_confirm_callback(query, waiters)
        return handled, fut.result(), query

    handled, approved, query = asyncio.run(_run())
    assert handled is True
    assert approved is True
    assert query.answers[-1] == "已批准"
    assert "已批准" in query.edits[-1]


def test_handle_confirm_callback_for_expired_waiter_reports_expired():
    class FakeQuery:
        def __init__(self) -> None:
            self.data = "confirm:missing:n"
            self.answers: list[str] = []

        async def answer(self, text: str | None = None):
            self.answers.append(text or "")

    async def _run():
        query = FakeQuery()
        handled = await _handle_confirm_callback(query, {})
        return handled, query.answers

    handled, answers = asyncio.run(_run())
    assert handled is True
    assert answers[-1] == "该确认已失效"
