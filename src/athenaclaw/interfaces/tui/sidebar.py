"""
[INPUT]: textual, pathlib
[OUTPUT]: SidebarPanel — 增强侧边栏（概况 / 持仓 / 行情 多 Tab）
[POS]: TUI 侧边栏组件，被 app.py 组合到主布局
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
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
        if not text:
            text = self._portfolio_preview()
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

    def _portfolio_preview(self) -> str:
        path = self.workspace / "portfolio.json"
        if not path.exists():
            return "暂无持仓数据"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "portfolio.json 格式错误"

        accounts = data.get("accounts")
        if not isinstance(accounts, list) or not accounts:
            return "暂无持仓数据"

        total_positions = sum(
            len(a.get("positions", []))
            for a in accounts
            if isinstance(a.get("positions"), list)
        )
        lines = [f"{len(accounts)} 账户 / {total_positions} 标的"]
        for account in accounts[:3]:
            broker = str(account.get("broker", "")).strip() or "unknown"
            label = str(account.get("label", "")).strip() or "default"
            positions = account.get("positions")
            items = positions if isinstance(positions, list) else []
            count = len(items)
            lines.append("")
            lines.append(f"{broker} / {label}")
            lines.append(f"{count} 标的 / 更新 {self._format_as_of(account.get('as_of'))}")
            for position in items[:5]:
                symbol = str(position.get("symbol", "")).strip() or "?"
                quantity = self._format_quantity(position.get("quantity"))
                lines.append(f"{symbol:<12}{quantity:>10}")
            if count > 5:
                lines.append(f"... 其余 {count - 5} 个标的")
        if len(accounts) > 3:
            lines.extend(["", f"... 其余 {len(accounts) - 3} 个账户"])
        return "\n".join(lines)

    @staticmethod
    def _format_quantity(value: object) -> str:
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            if value.is_integer():
                return f"{int(value):,}"
            text = f"{value:,.4f}".rstrip("0").rstrip(".")
            return text
        return str(value or "?")

    @staticmethod
    def _format_as_of(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return "-"
        candidate = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            return text
        return dt.strftime("%Y-%m-%d %H:%M")
