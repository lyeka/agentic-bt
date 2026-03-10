"""
[INPUT]: textual
[OUTPUT]: ConfirmScreen — 保护文件操作确认对话框
[POS]: TUI 模态屏幕，桥接 Kernel 同步 confirm 回调与 TUI 异步界面
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """文件写入确认对话框。返回 True（确认）或 False（拒绝）。"""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #confirm-prompt {
        margin-bottom: 1;
    }
    #confirm-buttons {
        height: 3;
        align: center middle;
    }
    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("y", "approve", "确认", show=False),
        Binding("n", "deny", "拒绝", show=False),
        Binding("escape", "deny", "取消", show=False),
    ]

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"确认写入 [bold]{self.path}[/bold] ?", id="confirm-prompt")
            yield Button("确认 (y)", variant="primary", id="btn-yes")
            yield Button("取消 (n)", variant="default", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)
