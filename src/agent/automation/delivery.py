"""
[INPUT]: json, urllib, typing, agent.automation.models
[OUTPUT]: DeliveryChannel, TelegramDeliveryChannel, WebhookDeliveryChannel
[POS]: 自动化任务主动投递层
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib import request

from agent.automation.models import DeliveryReceipt


class DeliveryChannel(Protocol):
    def send(
        self,
        *,
        target: str,
        text: str,
        task_id: str,
        run_id: str,
        kind: str,
    ) -> DeliveryReceipt: ...


class TelegramDeliveryChannel:
    def __init__(
        self,
        *,
        bot_token: str,
        sender: Callable[[str, str], str] | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._sender = sender or self._send_via_http

    def send(
        self,
        *,
        target: str,
        text: str,
        task_id: str,
        run_id: str,
        kind: str,
    ) -> DeliveryReceipt:
        message_id = self._sender(target, text)
        return DeliveryReceipt(
            channel="telegram",
            target=target,
            outbound_message_id=message_id,
            task_id=task_id,
            run_id=run_id,
            kind=kind,
        )

    def _send_via_http(self, target: str, text: str) -> str:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = json.dumps({"chat_id": int(target), "text": text}).encode("utf-8")
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=15) as resp:  # pragma: no cover - integration path
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("result", {}).get("message_id", "unknown"))


class WebhookDeliveryChannel:
    def __init__(
        self,
        *,
        sender: Callable[[str, dict[str, Any]], str] | None = None,
    ) -> None:
        self._sender = sender or self._send_via_http

    def send(
        self,
        *,
        target: str,
        text: str,
        task_id: str,
        run_id: str,
        kind: str,
    ) -> DeliveryReceipt:
        message_id = self._sender(
            target,
            {
                "task_id": task_id,
                "run_id": run_id,
                "kind": kind,
                "text": text,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return DeliveryReceipt(
            channel="webhook",
            target=target,
            outbound_message_id=message_id,
            task_id=task_id,
            run_id=run_id,
            kind=kind,
        )

    def _send_via_http(self, target: str, payload: dict[str, Any]) -> str:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(target, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=15) as resp:  # pragma: no cover - integration path
            resp.read()
        return "webhook"
