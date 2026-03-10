"""
[INPUT]: textual, threading, time, datetime, agent.kernel, agent.runtime, agent.adapters.tui.{widgets,sidebar,commands,screens}
[OUTPUT]: InvestmentApp — Textual TUI 投资助手主界面
[POS]: TUI 展示层适配器：布局/输入/流式渲染/进度/confirm 桥接/sidebar/会话管理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Header, Markdown, Static, TextArea

from agent.adapters.tui.commands import AppCommandProvider
from agent.adapters.tui.sidebar import SidebarPanel
from agent.adapters.tui.widgets import StreamingMarkdown
from agent.kernel import Session
from agent.runtime import KernelBundle


class UserSubmitted(Message):
    """内部消息：用户提交了一段文本。"""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ChatInput(TextArea):
    """Enter 发送，Shift+Enter 换行。"""

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            self.action_submit()

    def action_submit(self) -> None:
        text = self.text.strip()
        if not text:
            return
        self.clear()
        self.post_message(UserSubmitted(text))


class InvestmentApp(App):
    """投资助手 TUI 主界面。"""

    CSS_PATH = "app.tcss"

    COMMANDS = {AppCommandProvider}

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+p", "command_palette", "命令面板"),
        Binding("ctrl+b", "toggle_sidebar", "侧边栏"),
        Binding("ctrl+n", "new_session", "新会话"),
        Binding("escape", "focus_input", "输入", show=False),
    ]

    TITLE = "投资助手"

    def __init__(
        self,
        bundle: KernelBundle,
        session: Session,
        keep_last: int = 20,
    ) -> None:
        super().__init__()
        self.bundle = bundle
        self.session = session
        self.keep_last = keep_last
        self._thinking_widget: Static | None = None
        self._streaming_widget: StreamingMarkdown | None = None
        self._turn_start: float = 0
        self._turn_tokens: int = 0

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with VerticalScroll(id="chat"):
                pass
            yield SidebarPanel(self.bundle.workspace, id="sidebar")
        yield ChatInput(id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.bundle.kernel.model
        self.bundle.kernel.stream = True
        self._wire_events()
        self.bundle.kernel.on_confirm(self._make_confirm())
        self._render_history()
        self._refresh_sidebar()
        self.query_one("#input").focus()

    # ── History ───────────────────────────────────────────────────────────────

    def _render_history(self) -> None:
        chat = self.query_one("#chat")
        for msg in self.session.history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                chat.mount(Static(content, classes="user-msg"))
            elif role == "assistant" and content:
                chat.mount(Markdown(content, classes="assistant-msg"))
        if self.session.history:
            self.call_after_refresh(chat.scroll_end, animate=False)

    # ── Input handling ────────────────────────────────────────────────────────

    def on_user_submitted(self, message: UserSubmitted) -> None:
        text = message.text
        chat = self.query_one("#chat")
        ts = datetime.now().strftime("%H:%M")
        chat.mount(Static(f"[{ts}]  {text}", classes="user-msg"))
        chat.scroll_end(animate=False)
        self._turn_start = time.monotonic()
        self._turn_tokens = 0
        self._run_turn(text)

    @work(thread=True)
    def _run_turn(self, text: str) -> None:
        reply = self.bundle.kernel.turn(text, self.session)
        self.call_from_thread(self._on_reply, reply)

    def _on_reply(self, reply: str) -> None:
        self._clear_thinking()
        elapsed_ms = int((time.monotonic() - self._turn_start) * 1000)

        if self._streaming_widget:
            self._streaming_widget.finalize()
            self._streaming_widget = None
        else:
            self.query_one("#chat").mount(
                Markdown(reply, classes="assistant-msg"),
            )

        meta: list[str] = []
        if self._turn_tokens:
            meta.append(f"{self._turn_tokens:,} tokens")
        meta.append(f"{elapsed_ms / 1000:.1f}s")
        chat = self.query_one("#chat")
        chat.mount(Static(" · ".join(meta), classes="msg-meta"))
        chat.scroll_end(animate=False)

        self.session.prune(keep_last_user_messages=max(1, self.keep_last))
        self.bundle.session_store.save(self.session)

    # ── Progress / streaming ──────────────────────────────────────────────────

    def _wire_events(self) -> None:
        k = self.bundle.kernel
        k.wire("llm.call.start", self._on_kernel_event)
        k.wire("llm.chunk", self._on_kernel_event)
        k.wire("llm.call.done", self._on_kernel_event)
        k.wire("tool.call.start", self._on_kernel_event)
        k.wire("tool.call.done", self._on_kernel_event)
        k.wire("turn.done", self._on_kernel_event)
        k.wire("tool:*", self._on_workspace_change)

    def _on_kernel_event(self, event: str, data: object) -> None:
        self.call_from_thread(self._update_progress, event, data)

    def _update_progress(self, event: str, data: object) -> None:
        chat = self.query_one("#chat")
        d = data if isinstance(data, dict) else {}

        if event == "llm.call.start":
            self._show_thinking()

        elif event == "llm.chunk":
            self._clear_thinking()
            content = d.get("content", "")
            if self._streaming_widget is None:
                self._streaming_widget = StreamingMarkdown(classes="assistant-msg")
                chat.mount(self._streaming_widget)
            self._streaming_widget.append(content)
            chat.scroll_end(animate=False)

        elif event == "llm.call.done":
            tokens = d.get("total_tokens", 0)
            if tokens:
                self._turn_tokens = tokens

        elif event == "tool.call.start":
            self._clear_thinking()
            name = d.get("name", "?")
            chat.mount(Static(f"⚙ {name} ...", classes="tool-status"))
            chat.scroll_end(animate=False)

        elif event == "tool.call.done":
            name = d.get("name", "?")
            chat.mount(Static(f"✓ {name}", classes="tool-status"))
            chat.scroll_end(animate=False)

        elif event == "turn.done":
            self._clear_thinking()

    def _show_thinking(self) -> None:
        if self._thinking_widget is None:
            self._thinking_widget = Static("⏳ 思考中...", classes="thinking")
            self.query_one("#chat").mount(self._thinking_widget)
            self.query_one("#chat").scroll_end(animate=False)

    def _clear_thinking(self) -> None:
        if self._thinking_widget is not None:
            self._thinking_widget.remove()
            self._thinking_widget = None

    # ── Confirm bridge ────────────────────────────────────────────────────────

    def _make_confirm(self) -> Callable[[str], bool]:
        from agent.adapters.tui.screens import ConfirmScreen

        app = self

        def _confirm(path: str) -> bool:
            event = threading.Event()
            result: list[bool] = [False]

            def _on_result(confirmed: bool) -> None:
                result[0] = confirmed
                event.set()

            def _push() -> None:
                app.push_screen(ConfirmScreen(path), callback=_on_result)

            app.call_from_thread(_push)
            event.wait(timeout=60)
            return result[0]

        return _confirm

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _refresh_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", SidebarPanel)
        sidebar.refresh_profile(self.bundle.kernel.model, self.session.history)

    def _on_workspace_change(self, event: str, data: object) -> None:
        self.call_from_thread(self._refresh_sidebar)

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    # ── Session management ────────────────────────────────────────────────────

    def action_new_session(self) -> None:
        if self.session.history:
            archive = self.bundle.state / "sessions" / "archive"
            archive.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session.save(archive / f"{ts}.json")
        self.session = Session(session_id=self.session.id)
        self.query_one("#chat").remove_children()
        self.bundle.session_store.save(self.session)
        self._refresh_sidebar()
        self.notify("已创建新会话")

    # ── Focus ─────────────────────────────────────────────────────────────────

    def action_focus_input(self) -> None:
        self.query_one("#input").focus()
