"""
[INPUT]: asyncio, time, dataclasses, typing, athenaclaw.runtime, athenaclaw.kernel, athenaclaw.interfaces.im.*
[OUTPUT]: IMDriver
[POS]: IM 通用驱动层：鉴权、路由、并发、进度/状态消息、confirm 桥接、session 落盘
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from athenaclaw.interfaces.im.backend import IMBackend, InboundMessage, OutboundRef
from athenaclaw.interfaces.im.confirm_bridge import make_sync_confirm
from athenaclaw.interfaces.im.progress import ProgressBuffer
from athenaclaw.interfaces.im.text import chunk_text
from athenaclaw.kernel import Session
from athenaclaw.llm.messages import ContextRef, TurnInput
from athenaclaw.automation.store import AutomationStore
from athenaclaw.runtime import AgentConfig, KernelBundle, build_kernel_bundle


@dataclass
class _StatusUpdater:
    backend: IMBackend
    ref: OutboundRef
    throttle_sec: float
    render: Callable[[], str]

    _dirty: bool = False
    _task: asyncio.Task | None = None
    _last_flush_ts: float = 0.0

    def request_flush(self) -> None:
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        while self._dirty:
            self._dirty = False
            wait = max(0.0, self.throttle_sec - (time.monotonic() - self._last_flush_ts))
            if wait:
                await asyncio.sleep(wait)
            try:
                await self.backend.edit_text(self.ref, self.render())
            except Exception:
                # 进度更新失败不应影响主流程
                pass
            self._last_flush_ts = time.monotonic()


@dataclass
class ChatState:
    conversation_id: str
    bundle: KernelBundle
    session: Session
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    progress: ProgressBuffer = field(default_factory=lambda: ProgressBuffer(max_lines=10))
    status_ref: OutboundRef | None = None
    status_updater: _StatusUpdater | None = None


class IMDriver:
    def __init__(
        self,
        *,
        backend: IMBackend,
        adapter_name: str,
        config: AgentConfig,
        allowed_user_ids: set[str],
        confirm_timeout_sec: int = 60,
        status_edit_throttle_sec: float = 1.0,
        show_process_messages: bool = False,
        bundle_factory: Callable[[str, Path], KernelBundle] | None = None,
    ) -> None:
        self._backend = backend
        self._adapter_name = adapter_name
        self._config = config
        self._allowed_user_ids = allowed_user_ids
        self._confirm_timeout_sec = confirm_timeout_sec
        self._status_edit_throttle_sec = status_edit_throttle_sec
        self._show_process_messages = show_process_messages
        self._bundle_factory = bundle_factory
        self._chats: dict[str, ChatState] = {}

    def _make_bundle(self, *, conversation_id: str, cwd: Path) -> KernelBundle:
        if self._bundle_factory is not None:
            return self._bundle_factory(conversation_id, cwd)
        return build_kernel_bundle(
            config=self._config,
            adapter_name=self._adapter_name,
            conversation_id=conversation_id,
            cwd=cwd,
        )

    async def handle(self, msg: InboundMessage) -> None:
        # 基础过滤
        text = (msg.text or "").strip()
        has_attachments = bool(msg.attachments)
        if not text and not has_attachments:
            return

        if not msg.is_private:
            await self._backend.send_text(msg.conversation_id, "请私聊使用。")
            return

        if self._allowed_user_ids and msg.user_id not in self._allowed_user_ids:
            await self._backend.send_text(msg.conversation_id, "未授权用户，已拒绝。")
            return

        chat = await self._get_or_create_chat(msg.conversation_id)
        async with chat.lock:
            # commands
            if not has_attachments and text.startswith("/"):
                await self._handle_command(chat, text)
                return

            typing_task: asyncio.Task | None = None
            if self._show_process_messages:
                chat.progress.reset()
                status = await self._backend.send_text(msg.conversation_id, "思考中...")
                chat.status_ref = status

                def _render_status() -> str:
                    body = chat.progress.render()
                    if body:
                        return "思考中...\n\n" + body
                    return "思考中..."

                chat.status_updater = _StatusUpdater(
                    backend=self._backend,
                    ref=status,
                    throttle_sec=self._status_edit_throttle_sec,
                    render=_render_status,
                )
                # typing heartbeat
                typing_task = asyncio.create_task(self._typing_heartbeat(msg.conversation_id))
            else:
                chat.status_ref = None
                chat.status_updater = None

            turn_input: str | TurnInput = text
            if has_attachments:
                turn_input = TurnInput(text=text, attachments=msg.attachments)
            refs = self._reply_refs(chat, msg)
            if refs:
                base = turn_input if isinstance(turn_input, TurnInput) else TurnInput(text=str(turn_input))
                turn_input = TurnInput(text=base.text, attachments=base.attachments, refs=refs)
            try:
                reply = await asyncio.to_thread(chat.bundle.kernel.turn, turn_input, chat.session)
            except Exception as exc:
                await self._backend.send_text(msg.conversation_id, f"发生错误: {type(exc).__name__}: {exc}")
                return
            finally:
                if typing_task is not None:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

            # session persist
            chat.bundle.session_store.save(chat.session)

            # harness 更新重启
            kernel_data = getattr(chat.bundle.kernel, "data", None)
            if kernel_data is not None and callable(getattr(kernel_data, "get", None)) and kernel_data.get("_restart_requested"):
                await self._backend.send_text(msg.conversation_id, "正在更新重启...")
                os._exit(42)

            # finalize status
            if chat.status_ref and chat.status_updater:
                chat.progress.append("done")
                chat.status_updater.request_flush()

            for chunk in chunk_text(reply, max_len=self._backend.max_text_len):
                if chunk:
                    await self._backend.send_text(msg.conversation_id, chunk)

    async def _typing_heartbeat(self, conversation_id: str) -> None:
        while True:
            try:
                await self._backend.send_typing(conversation_id)
            except Exception:
                pass
            await asyncio.sleep(4.0)

    async def _handle_command(self, chat: ChatState, text: str) -> None:
        cmd = text.strip().split()[0].lower()

        if cmd in ("/start", "/help"):
            await self._backend.send_text(
                chat.conversation_id,
                (
                    "投资助手已接入 IM。\n"
                    "可用命令: /start /help /new /reset /compact /context /status\n"
                    "直接发送文本开始对话。"
                ),
            )
            return

        if cmd in ("/new", "/reset"):
            chat.session = Session(session_id=chat.session.id)
            chat.bundle.session_store.save(chat.session)
            await self._backend.send_text(chat.conversation_id, "已开始新会话。")
            return

        if cmd == "/compact":
            from athenaclaw.llm.context import compact_history, estimate_tokens

            before_tokens = estimate_tokens(chat.session.history)
            result = compact_history(
                provider=getattr(chat.bundle.kernel, "provider", None),
                client=getattr(chat.bundle.kernel, "client", None),
                model=self._config.model,
                history=chat.session.history,
            )
            chat.session.history = result.retained
            if result.summary:
                chat.session.summary = (
                    f"{chat.session.summary}\n\n{result.summary}"
                    if chat.session.summary else result.summary
                )
            after_tokens = estimate_tokens(chat.session.history)
            chat.bundle.session_store.save(chat.session)
            chat.bundle.kernel.emit("context.compacted", {
                "trigger": "manual",
                "messages_compressed": result.compressed_count,
                "messages_retained": result.retained_count,
                "tokens_before": before_tokens,
                "tokens_after": after_tokens,
                "summary": result.summary,
            })
            await self._backend.send_text(
                chat.conversation_id,
                f"已压缩上下文。\n"
                f"消息: {result.compressed_count + result.retained_count} → {result.retained_count}\n"
                f"Token 估算: ~{before_tokens} → ~{after_tokens}",
            )
            return

        if cmd == "/context":
            from athenaclaw.llm.context import context_info

            info = context_info(chat.session.history, self._config.context_window)
            await self._backend.send_text(
                chat.conversation_id,
                (
                    f"消息数: {info.message_count}（user: {info.user_message_count}）\n"
                    f"估算 Token: ~{info.estimated_tokens}\n"
                    f"Context Window: {info.context_window}\n"
                    f"使用率: {info.usage_pct}%"
                ),
            )
            return

        if cmd == "/status":
            await self._backend.send_text(
                chat.conversation_id,
                (
                    f"model={self._config.model}\n"
                    f"base_url={self._config.base_url or '(default)'}\n"
                    f"workspace={chat.bundle.workspace}\n"
                    f"state={chat.bundle.state}\n"
                    f"trace={chat.bundle.trace_path}\n"
                    f"history={len(chat.session.history)}"
                ),
            )
            return

        await self._backend.send_text(
            chat.conversation_id,
            "未知命令。可用: /start /help /new /reset /compact /context /status",
        )

    async def _get_or_create_chat(self, conversation_id: str) -> ChatState:
        existing = self._chats.get(conversation_id)
        if existing is not None:
            return existing

        cwd = self._config.workspace_dir.expanduser()
        bundle = self._make_bundle(conversation_id=conversation_id, cwd=cwd)
        session = bundle.session_store.load()
        session.id = f"{self._adapter_name}:{conversation_id}"

        loop = asyncio.get_running_loop()
        bundle.kernel.on_confirm(
            make_sync_confirm(
                backend=self._backend,
                loop=loop,
                conversation_id=conversation_id,
                timeout_sec=self._confirm_timeout_sec,
            ),
        )

        chat = ChatState(conversation_id=conversation_id, bundle=bundle, session=session)

        # wire events to progress (thread -> loop)
        if self._show_process_messages:
            def _on_event(event: str, data: object) -> None:
                loop.call_soon_threadsafe(self._handle_kernel_event, chat, event, data)

            bundle.kernel.wire("turn.round", _on_event)
            bundle.kernel.wire("llm.call.*", _on_event)
            bundle.kernel.wire("tool.call.*", _on_event)
            bundle.kernel.wire("tool:*", _on_event)
            bundle.kernel.wire("memory.compressed", _on_event)

        self._chats[conversation_id] = chat
        return chat

    def _reply_refs(self, chat: ChatState, msg: InboundMessage) -> tuple[ContextRef, ...]:
        if not msg.reply_to_message_id:
            return ()
        store = AutomationStore(workspace=chat.bundle.workspace, state=chat.bundle.state)
        receipt = store.find_receipt(
            channel=self._adapter_name,
            target=chat.conversation_id,
            outbound_message_id=msg.reply_to_message_id,
        )
        if receipt is None:
            return ()
        return (
            ContextRef(kind="automation_task", value=receipt.task_id),
            ContextRef(kind="automation_run", value=receipt.run_id),
        )

    def _handle_kernel_event(self, chat: ChatState, event: str, data: object) -> None:
        if event == "turn.round":
            try:
                d = data or {}
                r = d.get("round")
                m = d.get("max")
                if r and m:
                    chat.progress.append(f"Round {r}/{m}")
            except Exception:
                pass
        elif event.startswith("tool.call.start"):
            try:
                d = data or {}
                name = str(d.get("name", "")).strip()
                if name:
                    chat.progress.append(f"tool {name} ...")
            except Exception:
                pass
        elif event.startswith("tool:"):
            # tool:xxx 事件 payload: {args, result}
            name = event.split(":", 1)[1]
            chat.progress.append(f"tool {name} ok")
        elif event == "memory.compressed":
            chat.progress.append("memory compressed")

        if chat.status_updater is not None:
            chat.status_updater.request_flush()
