"""
[INPUT]: textual, pathlib
[OUTPUT]: SidebarPanel — 增强侧边栏（概况 / 持仓 / 行情 多 Tab）
[POS]: TUI 侧边栏组件，被 app.py 组合到主布局
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane


class SidebarPanel(Vertical):
    """侧边栏：概况 / 持仓 / 行情 三 Tab 面板。"""

    def __init__(self, workspace: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace = workspace

    def compose(self) -> ComposeResult:
        with TabbedContent(id="sidebar-tabs"):
            with TabPane("概况", id="tab-profile"):
                yield Static("", id="sb-model", classes="sb-section")
                yield Static("", id="sb-soul", classes="sb-section")
                yield Static("", id="sb-memory", classes="sb-section")
            with TabPane("持仓", id="tab-portfolio"):
                yield Static("暂无持仓数据", id="sb-portfolio", classes="sb-section")
            with TabPane("行情", id="tab-market"):
                yield Static("暂无行情数据", id="sb-market", classes="sb-section")

    def refresh_profile(self, model: str, history: list[dict]) -> None:
        count = len(history)
        user_count = sum(1 for m in history if m.get("role") == "user")
        self.query_one("#sb-model", Static).update(
            f"模型: {model}\n消息: {user_count} 轮 / {count} 条"
        )
        self.query_one("#sb-soul", Static).update(
            self._preview(self.workspace / "soul.md", "soul.md", 3)
        )
        self.query_one("#sb-memory", Static).update(
            self._preview(self.workspace / "memory.md", "memory.md", 5)
        )

    def refresh_portfolio(self, text: str) -> None:
        self.query_one("#sb-portfolio", Static).update(text or "暂无持仓数据")

    def refresh_market(self, text: str) -> None:
        self.query_one("#sb-market", Static).update(text or "暂无行情数据")

    @staticmethod
    def _preview(path: Path, label: str, lines: int) -> str:
        if not path.exists():
            return f"[{label}] (空)"
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return f"[{label}] (空)"
        preview = "\n".join(text.splitlines()[:lines])
        return f"── {label} ──\n{preview}"
