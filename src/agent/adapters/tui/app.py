"""
[INPUT]: textual, threading, agent.kernel, agent.runtime
[OUTPUT]: InvestmentApp — Textual TUI 投资助手主界面
[POS]: TUI 展示层适配器：布局/输入/消息渲染/进度/confirm 桥接/sidebar
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Header, Markdown, Static, TextArea

from agent.adapters.tui.commands import AppCommandProvider
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

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with VerticalScroll(id="chat"):
                pass
            with Vertical(id="sidebar"):
                yield Static("", id="sidebar-title", classes="sidebar-label")
                yield Static("", id="sidebar-model", classes="sidebar-section")
                yield Static("", id="sidebar-soul", classes="sidebar-section")
                yield Static("", id="sidebar-memory", classes="sidebar-section")
        yield ChatInput(id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.bundle.kernel.model
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

    # ── Input handling ────────────────────────────────────────────────────────

    def on_user_submitted(self, message: UserSubmitted) -> None:
        text = message.text
        chat = self.query_one("#chat")
        chat.mount(Static(text, classes="user-msg"))
        chat.scroll_end(animate=False)
        self._run_turn(text)

    @work(thread=True)
    def _run_turn(self, text: str) -> None:
        reply = self.bundle.kernel.turn(text, self.session)
        self.call_from_thread(self._on_reply, reply)

    def _on_reply(self, reply: str) -> None:
        self._clear_thinking()
        chat = self.query_one("#chat")
        chat.mount(Markdown(reply, classes="assistant-msg"))
        chat.scroll_end(animate=False)
        self.session.prune(keep_last_user_messages=max(1, self.keep_last))
        self.bundle.session_store.save(self.session)

    # ── Progress (kernel event wiring) ────────────────────────────────────────

    def _wire_events(self) -> None:
        k = self.bundle.kernel
        k.wire("llm.call.start", self._on_kernel_event)
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
        elif event == "tool.call.start":
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
        model_info = f"模型: {self.bundle.kernel.model}"
        history_count = len(self.session.history)
        msg_count = sum(1 for m in self.session.history if m.get("role") == "user")

        self.query_one("#sidebar-title", Static).update("工作区")
        self.query_one("#sidebar-model", Static).update(
            f"{model_info}\n消息: {msg_count} 轮 / {history_count} 条"
        )

        ws = self.bundle.workspace
        self.query_one("#sidebar-soul", Static).update(
            self._read_preview(ws / "soul.md", "soul.md", lines=3)
        )
        self.query_one("#sidebar-memory", Static).update(
            self._read_preview(ws / "memory.md", "memory.md", lines=5)
        )

    @staticmethod
    def _read_preview(path: Path, label: str, lines: int) -> str:
        if not path.exists():
            return f"[{label}] (空)"
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return f"[{label}] (空)"
        preview = "\n".join(text.splitlines()[:lines])
        return f"── {label} ──\n{preview}"

    def _on_workspace_change(self, event: str, data: object) -> None:
        self.call_from_thread(self._refresh_sidebar)

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display
