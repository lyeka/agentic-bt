"""
[INPUT]: dataclasses, datetime, typing, agent.messages
[OUTPUT]: InboundMessage, OutboundRef, IMBackend Protocol
[POS]: IM backend 抽象层，隔离 Telegram/Discord 等平台差异
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent.messages import AttachmentRef


@dataclass(frozen=True)
class InboundMessage:
    adapter: str
    conversation_id: str
    user_id: str
    is_private: bool
    text: str
    message_id: str
    ts: datetime
    reply_to_message_id: str | None = None
    attachments: tuple[AttachmentRef, ...] = ()


@dataclass(frozen=True)
class OutboundRef:
    conversation_id: str
    message_id: str


class IMBackend(Protocol):
    """平台后端需要实现的最小能力集合。"""

    async def send_text(self, conversation_id: str, text: str) -> OutboundRef: ...

    async def edit_text(self, ref: OutboundRef, text: str) -> None: ...

    async def send_typing(self, conversation_id: str) -> None: ...

    async def ask_confirm(
        self,
        conversation_id: str,
        prompt: str,
        *,
        timeout_sec: int,
    ) -> bool: ...
