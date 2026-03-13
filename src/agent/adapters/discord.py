"""
[INPUT]: dotenv, asyncio, agent.runtime, agent.adapters.im.*
[OUTPUT]: main — Discord Bot 入口（DM-only）
[POS]: Discord 适配器（薄层）：仅负责平台 SDK 交互与把消息转给 IMDriver
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from agent.adapters.im.backend import InboundMessage, OutboundRef
from agent.adapters.im.driver import IMDriver
from agent.messages import AttachmentRef
from agent.runtime import AgentConfig


def _parse_allowed_user_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    out: set[str] = set()
    for part in raw.split(","):
        value = part.strip()
        if value:
            out.add(value)
    return out


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "y", "on")


def _safe_file_name(raw: str | None, *, fallback: str) -> str:
    name = (raw or "").strip()
    if not name:
        return fallback
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or fallback


def _suffix_for_mime(mime_type: str | None, *, fallback: str) -> str:
    guessed = mimetypes.guess_extension(mime_type or "")
    if guessed:
        return guessed
    return fallback


def _media_dir(base: Path, conversation_id: str, message_id: str) -> Path:
    return base / str(conversation_id) / str(message_id)


def _attachment_mime_type(attachment: Any) -> str:
    mime_type = str(getattr(attachment, "content_type", "") or "")
    if mime_type:
        return mime_type
    guessed, _ = mimetypes.guess_type(str(getattr(attachment, "filename", "") or ""))
    return guessed or "application/octet-stream"


def _is_private_message(message: Any) -> bool:
    return getattr(message, "guild", None) is None


def _reply_to_message_id(message: Any) -> str | None:
    reference = getattr(message, "reference", None)
    if reference is None:
        return None
    message_id = getattr(reference, "message_id", None)
    if message_id is None:
        return None
    return str(message_id)


def _append_decision(text: str, decision_text: str) -> str:
    base = (text or "").strip()
    return f"{base}\n\n{decision_text}" if base else decision_text


async def _save_attachment(attachment: Any, *, target_path: Path) -> int | None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    await attachment.save(target_path)
    try:
        return target_path.stat().st_size
    except OSError:
        return None


async def _collect_attachments(
    *,
    message: Any,
    media_root: Path,
    conversation_id: str,
    message_id: str,
) -> tuple[tuple[AttachmentRef, ...], str | None]:
    items = list(getattr(message, "attachments", None) or [])
    if not items:
        return (), None

    attachments: list[AttachmentRef] = []
    for item in items:
        mime_type = _attachment_mime_type(item)
        if mime_type.startswith("audio/"):
            return (), "暂不支持音频输入；本期仅支持图片。"
        if not mime_type.startswith("image/"):
            return (), "暂不支持文件输入；本期仅支持图片。"

        suffix = _suffix_for_mime(mime_type, fallback=".img")
        original_name = _safe_file_name(
            getattr(item, "filename", None),
            fallback=f"image{suffix}",
        )
        source_id = str(getattr(item, "id", "") or original_name)
        target_path = _media_dir(media_root, conversation_id, message_id) / original_name
        size_bytes = await _save_attachment(item, target_path=target_path)
        attachments.append(
            AttachmentRef(
                kind="image",
                path=str(target_path),
                mime_type=mime_type,
                size_bytes=size_bytes or getattr(item, "size", None),
                source_id=source_id,
                width=getattr(item, "width", None),
                height=getattr(item, "height", None),
                original_name=original_name,
            )
        )
    return tuple(attachments), None


def _make_default_confirm_view(future: asyncio.Future, timeout_sec: int):
    try:
        import discord
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("缺少依赖: discord.py。请安装 `pip install -e '.[discord]'`") from exc

    class _ConfirmView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=timeout_sec)
            self._future = future
            self.message = None

        async def _decide(self, interaction: Any, approved: bool) -> None:
            if self._future.done():
                await _send_interaction_notice(interaction, "该确认已失效")
                return

            self._future.set_result(approved)
            for child in self.children:
                child.disabled = True
            decision_text = "已批准" if approved else "已拒绝"
            updated = _append_decision(getattr(interaction.message, "content", ""), decision_text)
            try:
                await interaction.response.edit_message(content=updated, view=self)
            except Exception:
                try:
                    await interaction.message.edit(content=updated, view=self)
                except Exception:
                    pass
            self.stop()

        async def on_timeout(self) -> None:
            if not self._future.done():
                self._future.cancel()
            for child in self.children:
                child.disabled = True
            if self.message is not None:
                try:
                    updated = _append_decision(getattr(self.message, "content", ""), "已过期")
                    await self.message.edit(content=updated, view=self)
                except Exception:
                    pass
            self.stop()

        @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
        async def approve(self, interaction: Any, _button: Any) -> None:
            await self._decide(interaction, True)

        @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
        async def deny(self, interaction: Any, _button: Any) -> None:
            await self._decide(interaction, False)

    return _ConfirmView()


async def _send_interaction_notice(interaction: Any, text: str) -> None:
    try:
        response = getattr(interaction, "response", None)
        if response is not None:
            if hasattr(response, "is_done") and response.is_done():
                followup = getattr(interaction, "followup", None)
                if followup is not None:
                    await followup.send(text, ephemeral=True)
                    return
            await response.send_message(text, ephemeral=True)
            return
    except Exception:
        pass


@dataclass
class DiscordBackend:
    client: Any
    view_factory: Callable[[asyncio.Future, int], Any] | None = None
    max_text_len: int = 1900

    async def _fetch_channel(self, conversation_id: str) -> Any:
        channel_id = int(conversation_id)
        getter = getattr(self.client, "get_channel", None)
        if getter is not None:
            channel = getter(channel_id)
            if channel is not None:
                return channel
        fetcher = getattr(self.client, "fetch_channel", None)
        if fetcher is None:
            raise RuntimeError(f"无法获取 Discord channel: {conversation_id}")
        return await fetcher(channel_id)

    async def _fetch_message(self, ref: OutboundRef) -> Any:
        channel = await self._fetch_channel(ref.conversation_id)
        fetcher = getattr(channel, "fetch_message", None)
        if fetcher is not None:
            return await fetcher(int(ref.message_id))
        partial = getattr(channel, "get_partial_message", None)
        if partial is not None:
            return partial(int(ref.message_id))
        raise RuntimeError(f"无法获取 Discord message: {ref.message_id}")

    async def send_text(self, conversation_id: str, text: str) -> OutboundRef:
        channel = await self._fetch_channel(conversation_id)
        message = await channel.send(text)
        return OutboundRef(conversation_id=conversation_id, message_id=str(message.id))

    async def edit_text(self, ref: OutboundRef, text: str) -> None:
        message = await self._fetch_message(ref)
        await message.edit(content=text)

    async def send_typing(self, conversation_id: str) -> None:
        channel = await self._fetch_channel(conversation_id)
        await channel.typing()

    async def ask_confirm(
        self,
        conversation_id: str,
        prompt: str,
        *,
        timeout_sec: int,
    ) -> bool:
        channel = await self._fetch_channel(conversation_id)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        factory = self.view_factory or _make_default_confirm_view
        view = factory(future, timeout_sec)
        message = await channel.send(prompt, view=view)
        if hasattr(view, "message"):
            view.message = message
        if hasattr(view, "bind_message"):
            view.bind_message(message)
        try:
            return bool(await asyncio.wait_for(asyncio.shield(future), timeout=timeout_sec))
        except asyncio.TimeoutError:
            if not future.done():
                future.cancel()
            return False
        finally:
            stopper = getattr(view, "stop", None)
            if callable(stopper):
                stopper()


def main() -> None:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("错误: 未设置 DISCORD_BOT_TOKEN")

    allowed = _parse_allowed_user_ids(os.getenv("DISCORD_ALLOWED_USER_IDS"))

    config = AgentConfig.from_env()
    if not config.api_key:
        raise SystemExit("错误: 未设置 API_KEY（用于 LLM 调用）")

    status_throttle = float(os.getenv("DISCORD_STATUS_EDIT_THROTTLE_SEC", "1.0"))
    confirm_timeout = int(os.getenv("DISCORD_CONFIRM_TIMEOUT_SEC", "60"))
    show_process_messages = _parse_bool(
        os.getenv("DISCORD_SHOW_PROCESS_MESSAGES"),
        default=False,
    )
    media_root = config.state_dir.expanduser() / "media" / "discord"

    try:
        import discord
    except ModuleNotFoundError:
        raise SystemExit("缺少依赖: discord.py。请安装 `pip install -e '.[discord]'`")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    class AgentDiscordClient(discord.Client):
        def __init__(self) -> None:
            super().__init__(intents=intents)
            backend = DiscordBackend(client=self)
            self._backend = backend
            self._driver = IMDriver(
                backend=backend,
                adapter_name="discord",
                config=config,
                allowed_user_ids=allowed,
                confirm_timeout_sec=confirm_timeout,
                status_edit_throttle_sec=status_throttle,
                show_process_messages=show_process_messages,
            )

        async def on_message(self, message: Any) -> None:
            author = getattr(message, "author", None)
            if author is None:
                return
            if getattr(author, "bot", False):
                return
            if self.user is not None and getattr(author, "id", None) == self.user.id:
                return

            is_private = _is_private_message(message)

            if not allowed:
                if is_private:
                    await message.channel.send(
                        "未配置 DISCORD_ALLOWED_USER_IDS，已拒绝执行。\n"
                        f"你的 Discord user_id 是: {author.id}\n"
                        "请在 .env 中配置 DISCORD_ALLOWED_USER_IDS 后重启。"
                    )
                return

            attachments, media_error = await _collect_attachments(
                message=message,
                media_root=media_root,
                conversation_id=str(message.channel.id),
                message_id=str(message.id),
            )
            if media_error:
                await message.channel.send(media_error)
                return

            text = str(getattr(message, "content", "") or "")
            if not text and not attachments:
                return

            inbound = InboundMessage(
                adapter="discord",
                conversation_id=str(message.channel.id),
                user_id=str(author.id),
                is_private=is_private,
                text=text,
                message_id=str(message.id),
                reply_to_message_id=_reply_to_message_id(message),
                ts=getattr(message, "created_at", datetime.now(timezone.utc)),
                attachments=attachments,
            )
            await self._driver.handle(inbound)

    AgentDiscordClient().run(token)


if __name__ == "__main__":
    main()
