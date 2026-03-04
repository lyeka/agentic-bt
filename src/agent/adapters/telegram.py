"""
[INPUT]: dotenv, asyncio, agent.runtime, agent.adapters.im.*
[OUTPUT]: main — Telegram Bot 入口（polling）
[POS]: Telegram 适配器（薄层）：仅负责平台 SDK 交互与把消息转给 IMDriver
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

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


@dataclass
class TelegramBackend:
    """
    python-telegram-bot backend。

    依赖在运行时导入，未安装时会在启动时报错提示安装 extra。
    """

    bot: Any
    _confirm_waiters: dict[str, asyncio.Future]  # confirm_id -> Future[bool]

    async def send_text(self, conversation_id: str, text: str) -> OutboundRef:
        chat_id = int(conversation_id)
        msg = await self.bot.send_message(chat_id=chat_id, text=text)
        return OutboundRef(conversation_id=conversation_id, message_id=str(msg.message_id))

    async def edit_text(self, ref: OutboundRef, text: str) -> None:
        chat_id = int(ref.conversation_id)
        message_id = int(ref.message_id)
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

    # 运行时导入，避免未安装依赖时报错影响其他模块
    try:
        from telegram import Update
        from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters
    except ModuleNotFoundError:
        raise SystemExit("缺少依赖: python-telegram-bot。请安装 `pip install -e '.[telegram]'`")

    confirm_waiters: dict[str, asyncio.Future] = {}

    async def on_callback_query(update: Update, context: Any) -> None:
        query = update.callback_query
        if query is None or not query.data:
            return
        data = str(query.data)
        if not data.startswith("confirm:"):
            return
        # confirm:{confirm_id}:{y|n}
        try:
            _, rest = data.split("confirm:", 1)
            confirm_id, flag = rest.rsplit(":", 1)
        except ValueError:
            return
        fut = confirm_waiters.get(confirm_id)
        if fut is not None and not fut.done():
            fut.set_result(flag == "y")
        try:
            await query.answer()
        except Exception:
            pass

    async def on_message(update: Update, context: Any) -> None:
        if update.effective_chat is None or update.effective_user is None:
            return
        if update.message is None or update.message.text is None:
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

        msg = InboundMessage(
            adapter="telegram",
            conversation_id=str(chat.id),
            user_id=str(user.id),
            is_private=(chat.type == "private"),
            text=update.message.text,
            message_id=str(update.message.message_id),
            ts=update.message.date,
        )
        await driver.handle(msg)

    app = Application.builder().token(token).build()
    backend = TelegramBackend(bot=app.bot, _confirm_waiters=confirm_waiters)
    driver = IMDriver(
        backend=backend,
        adapter_name="telegram",
        config=config,
        allowed_user_ids=allowed,
        confirm_timeout_sec=confirm_timeout,
        status_edit_throttle_sec=status_throttle,
    )
    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(MessageHandler(filters.TEXT, on_message))

    # polling
    # drop_pending_updates 等价于 deleteWebhook(drop_pending_updates=...)
    app.run_polling(drop_pending_updates=drop_pending, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
