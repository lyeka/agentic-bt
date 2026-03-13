"""
[INPUT]: dotenv, asyncio, agent.runtime, agent.adapters.im.*
[OUTPUT]: main — Telegram Bot 入口（polling）
[POS]: Telegram 适配器（薄层）：仅负责平台 SDK 交互与把消息转给 IMDriver
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import html
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.messages import AttachmentRef
from agent.adapters.im.backend import InboundMessage, OutboundRef
from agent.adapters.im.driver import IMDriver
from agent.runtime import AgentConfig


def _parse_allowed_user_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    v = raw.strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _normalize_render_mode(raw: str | None) -> str:
    if raw is None:
        return "html"
    v = raw.strip().lower()
    if not v:
        return "html"
    if v in ("none", "plain", "text"):
        return "none"
    if v in ("md", "markdown"):
        return "markdown"
    return "html"


_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _inline_markdown_to_html(text: str) -> str:
    """最小可用的行内 markdown -> HTML（Telegram 支持标签子集）。"""
    placeholders: list[str] = []

    def _code_repl(match: re.Match[str]) -> str:
        placeholders.append(html.escape(match.group(1)))
        return f"@@CODE{len(placeholders) - 1}@@"

    work = _INLINE_CODE_RE.sub(_code_repl, text)
    work = html.escape(work)
    work = _BOLD_RE.sub(r"<b>\1</b>", work)
    work = _ITALIC_RE.sub(r"<i>\1</i>", work)

    for i, code in enumerate(placeholders):
        work = work.replace(f"@@CODE{i}@@", f"<code>{code}</code>")
    return work


def _markdown_to_html(text: str) -> str:
    """
    最小 markdown 渲染器（面向 Telegram HTML parse_mode）。

    支持：标题、列表、粗体/斜体、行内代码、fenced code block。
    """
    lines = text.splitlines()
    out: list[str] = []
    in_code = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                out.append("<pre><code>")
            else:
                in_code = False
                out.append("</code></pre>")
            continue

        if in_code:
            out.append(html.escape(line))
            continue

        if not line.strip():
            out.append("")
            continue

        heading = re.match(r"^\s*#{1,6}\s+(.+)$", line)
        if heading:
            out.append(f"<b>{_inline_markdown_to_html(heading.group(1).strip())}</b>")
            continue

        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            out.append(f"• {_inline_markdown_to_html(bullet.group(1).strip())}")
            continue

        ordered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if ordered:
            out.append(f"{ordered.group(1)}. {_inline_markdown_to_html(ordered.group(2).strip())}")
            continue

        out.append(_inline_markdown_to_html(line))

    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _is_parse_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "can't parse entities" in msg
        or "cannot parse entities" in msg
        or "unsupported start tag" in msg
        or "entity" in msg
    )


def _message_text(message: Any) -> str:
    return str(getattr(message, "text", None) or getattr(message, "caption", None) or "")


def _parse_confirm_callback(data: str) -> tuple[str, bool] | None:
    if not str(data or "").startswith("confirm:"):
        return None
    try:
        _, rest = str(data).split("confirm:", 1)
        confirm_id, flag = rest.rsplit(":", 1)
    except ValueError:
        return None
    if flag not in {"y", "n"}:
        return None
    return confirm_id, flag == "y"


async def _handle_confirm_callback(query: Any, confirm_waiters: dict[str, asyncio.Future]) -> bool:
    parsed = _parse_confirm_callback(str(getattr(query, "data", "") or ""))
    if parsed is None:
        return False

    confirm_id, approved = parsed
    fut = confirm_waiters.get(confirm_id)
    if fut is None or fut.done():
        try:
            await query.answer("该确认已失效")
        except Exception:
            pass
        return True

    fut.set_result(approved)

    decision_text = "已批准" if approved else "已拒绝"
    message = getattr(query, "message", None)
    if message is not None:
        original = _message_text(message).strip()
        updated = f"{original}\n\n{decision_text}" if original else decision_text
        try:
            await query.edit_message_text(updated)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass

    try:
        await query.answer(decision_text)
    except Exception:
        pass
    return True


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


async def _download_attachment(bot: Any, *, file_id: str, target_path: Path) -> int | None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tg_file = await bot.get_file(file_id)
    await tg_file.download_to_drive(custom_path=str(target_path))
    try:
        return target_path.stat().st_size
    except OSError:
        return None


async def _collect_attachments(
    *,
    bot: Any,
    message: Any,
    media_root: Path,
    conversation_id: str,
    message_id: str,
) -> tuple[tuple[AttachmentRef, ...], str | None]:
    photos = list(getattr(message, "photo", None) or [])
    if photos:
        picked = max(
            photos,
            key=lambda item: (
                int(getattr(item, "width", 0) or 0) * int(getattr(item, "height", 0) or 0),
                int(getattr(item, "file_size", 0) or 0),
            ),
        )
        source_id = str(getattr(picked, "file_unique_id", None) or getattr(picked, "file_id", "photo"))
        target_name = f"image-{source_id}.jpg"
        target_path = _media_dir(media_root, conversation_id, message_id) / target_name
        size_bytes = await _download_attachment(bot, file_id=str(picked.file_id), target_path=target_path)
        return (
            AttachmentRef(
                kind="image",
                path=str(target_path),
                mime_type="image/jpeg",
                size_bytes=size_bytes or getattr(picked, "file_size", None),
                source_id=source_id,
                width=getattr(picked, "width", None),
                height=getattr(picked, "height", None),
                original_name=target_name,
            ),
        ), None

    document = getattr(message, "document", None)
    if document is not None:
        mime_type = str(getattr(document, "mime_type", "") or "")
        if mime_type.startswith("image/"):
            suffix = _suffix_for_mime(mime_type, fallback=".img")
            original_name = _safe_file_name(
                getattr(document, "file_name", None),
                fallback=f"image{suffix}",
            )
            source_id = str(getattr(document, "file_unique_id", None) or getattr(document, "file_id", "document"))
            target_path = _media_dir(media_root, conversation_id, message_id) / original_name
            size_bytes = await _download_attachment(bot, file_id=str(document.file_id), target_path=target_path)
            return (
                AttachmentRef(
                    kind="image",
                    path=str(target_path),
                    mime_type=mime_type,
                    size_bytes=size_bytes or getattr(document, "file_size", None),
                    source_id=source_id,
                    original_name=original_name,
                ),
            ), None
        return (), "暂不支持文件输入；本期仅支持图片。"

    if getattr(message, "voice", None) is not None or getattr(message, "audio", None) is not None:
        return (), "暂不支持音频输入；本期仅支持图片。"

    return (), None


@dataclass
class TelegramBackend:
    """
    python-telegram-bot backend。

    依赖在运行时导入，未安装时会在启动时报错提示安装 extra。
    """

    bot: Any
    _confirm_waiters: dict[str, asyncio.Future]  # confirm_id -> Future[bool]
    render_mode: str = "html"  # none | markdown | html
    max_text_len: int = 3900

    def _prepare_text(self, text: str) -> tuple[str, str | None]:
        if self.render_mode == "none":
            return text, None
        if self.render_mode == "markdown":
            return text, "Markdown"
        return _markdown_to_html(text), "HTML"

    async def send_text(self, conversation_id: str, text: str) -> OutboundRef:
        chat_id = int(conversation_id)
        payload, parse_mode = self._prepare_text(text)
        if parse_mode:
            try:
                msg = await self.bot.send_message(chat_id=chat_id, text=payload, parse_mode=parse_mode)
            except Exception as exc:
                if not _is_parse_error(exc):
                    raise
                msg = await self.bot.send_message(chat_id=chat_id, text=text)
        else:
            msg = await self.bot.send_message(chat_id=chat_id, text=text)
        return OutboundRef(conversation_id=conversation_id, message_id=str(msg.message_id))

    async def edit_text(self, ref: OutboundRef, text: str) -> None:
        chat_id = int(ref.conversation_id)
        message_id = int(ref.message_id)
        payload, parse_mode = self._prepare_text(text)
        if parse_mode:
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=payload,
                    parse_mode=parse_mode,
                )
                return
            except Exception as exc:
                if not _is_parse_error(exc):
                    raise
        await self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)

    async def send_typing(self, conversation_id: str) -> None:
        chat_id = int(conversation_id)
        # action="typing"
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")

    async def ask_confirm(
        self,
        conversation_id: str,
        prompt: str,
        *,
        timeout_sec: int,
    ) -> bool:
        # 运行时导入，避免未安装依赖时影响包的其他入口
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        confirm_id = f"{conversation_id}:{int(datetime.now(tz=timezone.utc).timestamp() * 1000)}"
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._confirm_waiters[confirm_id] = fut

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data=f"confirm:{confirm_id}:y"),
                    InlineKeyboardButton("Deny", callback_data=f"confirm:{confirm_id}:n"),
                ]
            ]
        )
        chat_id = int(conversation_id)
        await self.bot.send_message(chat_id=chat_id, text=prompt, reply_markup=keyboard)

        try:
            return bool(await asyncio.wait_for(fut, timeout=timeout_sec))
        except asyncio.TimeoutError:
            return False
        finally:
            self._confirm_waiters.pop(confirm_id, None)


def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("错误: 未设置 TELEGRAM_BOT_TOKEN")

    # 安全默认拒绝：allowlist 未配置则不启动 driver（只回显 user_id）
    allowed = _parse_allowed_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS"))

    config = AgentConfig.from_env()
    if not config.api_key:
        raise SystemExit("错误: 未设置 API_KEY（用于 LLM 调用）")

    status_throttle = float(os.getenv("TELEGRAM_STATUS_EDIT_THROTTLE_SEC", "1.0"))
    confirm_timeout = int(os.getenv("TELEGRAM_CONFIRM_TIMEOUT_SEC", "60"))
    drop_pending = os.getenv("TELEGRAM_DROP_PENDING_UPDATES", "true").strip().lower() in ("1", "true", "yes", "y")
    show_process_messages = _parse_bool(
        os.getenv("TELEGRAM_SHOW_PROCESS_MESSAGES"),
        default=False,
    )
    render_mode = _normalize_render_mode(os.getenv("TELEGRAM_RENDER_MODE"))
    media_root = config.state_dir.expanduser() / "media" / "telegram"

    # 运行时导入，避免未安装依赖时报错影响其他模块
    try:
        from telegram import Update
        from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters
    except ModuleNotFoundError:
        raise SystemExit("缺少依赖: python-telegram-bot。请安装 `pip install -e '.[telegram]'`")

    confirm_waiters: dict[str, asyncio.Future] = {}

    async def on_callback_query(update: Update, context: Any) -> None:
        query = update.callback_query
        if query is None:
            return
        await _handle_confirm_callback(query, confirm_waiters)

    async def on_message(update: Update, context: Any) -> None:
        if update.effective_chat is None or update.effective_user is None:
            return
        if update.message is None:
            return

        chat = update.effective_chat
        user = update.effective_user

        # allowlist 未配置：只回显 user_id，防止误暴露能力
        if not allowed:
            if chat.type == "private":
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"未配置 TELEGRAM_ALLOWED_USER_IDS，已拒绝执行。\n"
                        f"你的 Telegram user_id 是: {user.id}\n"
                        "请在 .env 中配置 TELEGRAM_ALLOWED_USER_IDS 后重启。"
                    ),
                )
            return

        attachments, media_error = await _collect_attachments(
            bot=context.bot,
            message=update.message,
            media_root=media_root,
            conversation_id=str(chat.id),
            message_id=str(update.message.message_id),
        )
        if media_error:
            await context.bot.send_message(chat_id=chat.id, text=media_error)
            return

        text = _message_text(update.message)
        if not text and not attachments:
            return

        msg = InboundMessage(
            adapter="telegram",
            conversation_id=str(chat.id),
            user_id=str(user.id),
            is_private=(chat.type == "private"),
            text=text,
            message_id=str(update.message.message_id),
            reply_to_message_id=(
                str(update.message.reply_to_message.message_id)
                if getattr(update.message, "reply_to_message", None) is not None
                else None
            ),
            ts=update.message.date,
            attachments=attachments,
        )
        await driver.handle(msg)

    app = Application.builder().token(token).build()
    backend = TelegramBackend(
        bot=app.bot,
        _confirm_waiters=confirm_waiters,
        render_mode=render_mode,
    )
    driver = IMDriver(
        backend=backend,
        adapter_name="telegram",
        config=config,
        allowed_user_ids=allowed,
        confirm_timeout_sec=confirm_timeout,
        status_edit_throttle_sec=status_throttle,
        show_process_messages=show_process_messages,
    )
    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(MessageHandler(filters.ALL, on_message))

    # polling
    # drop_pending_updates 等价于 deleteWebhook(drop_pending_updates=...)
    app.run_polling(drop_pending_updates=drop_pending, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
