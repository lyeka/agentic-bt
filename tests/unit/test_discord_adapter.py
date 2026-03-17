"""
[INPUT]: athenaclaw.interfaces.discord helpers
[OUTPUT]: Discord adapter helper tests（配置/附件/backend）
[POS]: tests/ 单测层，验证 Discord 渲染与消息映射基础逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from athenaclaw.interfaces.discord import (
    DiscordBackend,
    _collect_attachments,
    _handle_command_interaction,
    _parse_allowed_user_ids,
    _parse_bool,
    _reply_to_message_id,
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


def test_reply_to_message_id_reads_reference_message_id():
    message = SimpleNamespace(reference=SimpleNamespace(message_id=42))
    assert _reply_to_message_id(message) == "42"


def test_collect_image_attachments_downloads_to_state_dir(tmp_path: Path):
    class FakeAttachment:
        id = 7
        filename = "chart.png"
        content_type = "image/png"
        size = 123
        width = 640
        height = 480

        async def save(self, target_path: Path) -> None:
            Path(target_path).write_bytes(b"img")

    message = SimpleNamespace(attachments=[FakeAttachment()])

    async def _run():
        return await _collect_attachments(
            message=message,
            media_root=tmp_path,
            conversation_id="dm-1",
            message_id="msg-1",
        )

    attachments, error = asyncio.run(_run())
    assert error is None
    assert len(attachments) == 1
    assert attachments[0].kind == "image"
    assert attachments[0].path.endswith("chart.png")
    assert Path(attachments[0].path).exists()


def test_collect_audio_attachment_returns_explicit_error(tmp_path: Path):
    message = SimpleNamespace(
        attachments=[
            SimpleNamespace(
                id=8,
                filename="voice.ogg",
                content_type="audio/ogg",
                size=88,
            )
        ]
    )

    async def _run():
        return await _collect_attachments(
            message=message,
            media_root=tmp_path,
            conversation_id="dm-1",
            message_id="msg-1",
        )

    attachments, error = asyncio.run(_run())
    assert attachments == ()
    assert "音频" in error


def test_discord_backend_send_edit_and_typing():
    class FakeMessage:
        def __init__(self, message_id: int, content: str) -> None:
            self.id = message_id
            self.content = content
            self.edits: list[str] = []

        async def edit(self, *, content: str, view=None) -> None:
            self.content = content
            self.edits.append(content)

    class FakeChannel:
        def __init__(self) -> None:
            self.sent: list[tuple[str, object | None]] = []
            self.messages: dict[int, FakeMessage] = {}
            self.typing_calls = 0

        async def send(self, content: str, view=None):
            message = FakeMessage(len(self.messages) + 1, content)
            self.messages[message.id] = message
            self.sent.append((content, view))
            return message

        async def fetch_message(self, message_id: int):
            return self.messages[message_id]

        async def typing(self) -> None:
            self.typing_calls += 1

    class FakeClient:
        def __init__(self, channel: FakeChannel) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int):
            assert channel_id == 1001
            return self._channel

    channel = FakeChannel()
    backend = DiscordBackend(client=FakeClient(channel))

    async def _run():
        ref = await backend.send_text("1001", "hello")
        await backend.edit_text(ref, "updated")
        await backend.send_typing("1001")
        return ref

    ref = asyncio.run(_run())
    assert ref.message_id == "1"
    assert channel.messages[1].edits == ["updated"]
    assert channel.typing_calls == 1


def test_discord_backend_ask_confirm_uses_injected_view_factory():
    class FakeMessage:
        def __init__(self) -> None:
            self.id = 9

    class FakeChannel:
        def __init__(self) -> None:
            self.views: list[object] = []

        async def send(self, content: str, view=None):
            assert "确认操作" in content
            self.views.append(view)
            return FakeMessage()

    class FakeClient:
        def __init__(self, channel: FakeChannel) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int):
            assert channel_id == 1001
            return self._channel

    class FakeView:
        def __init__(self, future: asyncio.Future) -> None:
            self.future = future
            self.message = None
            self.stopped = False

        def bind_message(self, message) -> None:
            self.message = message
            self.future.set_result(True)

        def stop(self) -> None:
            self.stopped = True

    async def _run() -> bool:
        channel = FakeChannel()
        backend = DiscordBackend(
            client=FakeClient(channel),
            view_factory=lambda future, _timeout: FakeView(future),
        )
        return await backend.ask_confirm("1001", "确认操作 soul.md?", timeout_sec=3)

    assert asyncio.run(_run()) is True


def test_discord_backend_send_text_uses_bound_interaction_followup():
    class FakeMessage:
        def __init__(self, message_id: int) -> None:
            self.id = message_id

    class FakeChannel:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, content: str, view=None):
            self.sent.append(content)
            return FakeMessage(1)

    class FakeClient:
        def __init__(self, channel: FakeChannel) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int):
            assert channel_id == 1001
            return self._channel

    class FakeFollowup:
        def __init__(self) -> None:
            self.sent: list[tuple[str, bool]] = []

        async def send(self, content: str, *, wait: bool = False, ephemeral: bool = False):
            self.sent.append((content, wait))
            assert ephemeral is False
            return FakeMessage(9)

    channel = FakeChannel()
    backend = DiscordBackend(client=FakeClient(channel))
    interaction = SimpleNamespace(
        id=77,
        channel_id=1001,
        response=SimpleNamespace(is_done=lambda: True),
        followup=FakeFollowup(),
    )

    async def _run():
        with backend.bind_interaction_response(interaction):
            return await backend.send_text("1001", "slash-ok")

    ref = asyncio.run(_run())
    assert channel.sent == []
    assert interaction.followup.sent == [("slash-ok", True)]
    assert ref.message_id == "9"


def test_handle_command_interaction_defers_and_routes_through_backend():
    class FakeMessage:
        def __init__(self, message_id: int) -> None:
            self.id = message_id

    class FakeChannel:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, content: str, view=None):
            self.sent.append(content)
            return FakeMessage(1)

    class FakeClient:
        def __init__(self, channel: FakeChannel) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int):
            assert channel_id == 1001
            return self._channel

    class FakeResponse:
        def __init__(self) -> None:
            self.deferred = False

        def is_done(self) -> bool:
            return self.deferred

        async def defer(self, *, thinking: bool = False) -> None:
            self.deferred = True
            assert thinking is True

        async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
            raise AssertionError("deferred interaction should answer through followup")

    class FakeFollowup:
        def __init__(self) -> None:
            self.sent: list[tuple[str, bool, bool]] = []

        async def send(self, content: str, *, wait: bool = False, ephemeral: bool = False):
            self.sent.append((content, wait, ephemeral))
            return FakeMessage(22)

    class FakeDriver:
        def __init__(self, backend: DiscordBackend) -> None:
            self.backend = backend
            self.calls = []

        async def handle(self, msg) -> None:
            self.calls.append(msg)
            await self.backend.send_text(msg.conversation_id, "已开始新会话。")

    channel = FakeChannel()
    backend = DiscordBackend(client=FakeClient(channel))
    driver = FakeDriver(backend)
    interaction = SimpleNamespace(
        id=88,
        type=SimpleNamespace(name="application_command"),
        data={"name": "new"},
        channel_id=1001,
        guild=None,
        user=SimpleNamespace(id=42),
        created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        response=FakeResponse(),
        followup=FakeFollowup(),
    )

    async def _run():
        return await _handle_command_interaction(
            interaction=interaction,
            driver=driver,  # type: ignore[arg-type]
            backend=backend,
            allowed_user_ids={"42"},
        )

    handled = asyncio.run(_run())
    assert handled is True
    assert interaction.response.deferred is True
    assert len(driver.calls) == 1
    assert driver.calls[0].text == "/new"
    assert driver.calls[0].conversation_id == "1001"
    assert interaction.followup.sent == [("已开始新会话。", True, False)]
    assert channel.sent == []


def test_handle_command_interaction_warns_when_allowlist_missing():
    class FakeChannel:
        async def send(self, content: str, view=None):
            raise AssertionError("missing allowlist should not send directly to channel")

    class FakeClient:
        def __init__(self, channel: FakeChannel) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int):
            return self._channel

    class FakeResponse:
        def __init__(self) -> None:
            self.sent: list[tuple[str, bool]] = []

        def is_done(self) -> bool:
            return False

        async def defer(self, *, thinking: bool = False) -> None:
            raise AssertionError("missing allowlist should answer immediately")

        async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
            self.sent.append((content, ephemeral))

    class FakeDriver:
        async def handle(self, msg) -> None:
            raise AssertionError("missing allowlist should not reach driver")

    backend = DiscordBackend(client=FakeClient(FakeChannel()))
    interaction = SimpleNamespace(
        id=99,
        type=SimpleNamespace(name="application_command"),
        data={"name": "new"},
        channel_id=1001,
        guild=None,
        user=SimpleNamespace(id=1234),
        created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        response=FakeResponse(),
        followup=SimpleNamespace(send=None),
    )

    async def _run():
        return await _handle_command_interaction(
            interaction=interaction,
            driver=FakeDriver(),  # type: ignore[arg-type]
            backend=backend,
            allowed_user_ids=set(),
        )

    handled = asyncio.run(_run())
    assert handled is True
    assert len(interaction.response.sent) == 1
    assert "DISCORD_ALLOWED_USER_IDS" in interaction.response.sent[0][0]
    assert interaction.response.sent[0][1] is True
