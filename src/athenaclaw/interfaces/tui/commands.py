"""
[INPUT]: textual.command, agent.kernel
[OUTPUT]: AppCommandProvider — 命令面板（会话/侧边栏/状态/主题/退出）
[POS]: TUI 命令面板扩展，被 app.py 注册为 COMMANDS
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from textual.command import Hit, Hits, Provider

from athenaclaw.kernel import Session


THEMES = [
    ("textual-dark", "暗色"),
    ("textual-light", "亮色"),
    ("monokai", "Monokai"),
    ("dracula", "Dracula"),
    ("nord", "Nord"),
    ("tokyo-night", "Tokyo Night"),
]


class AppCommandProvider(Provider):
    """Ctrl+P 命令面板：投资助手操作集合。"""

    async def search(self, query: str) -> Hits:
        commands = [
            ("新建会话", "归档当前对话并开始新会话", self._new_session),
            ("重置会话", "清空当前对话历史", self._reset_session),
            ("切换侧边栏", "显示或隐藏右侧工作区面板", self._toggle_sidebar),
            ("查看状态", "显示模型、trace 路径等信息", self._show_status),
            ("退出", "关闭投资助手", self._quit),
        ]
        for name, display_name in THEMES:
            commands.append((
                f"主题: {display_name}",
                f"切换到 {display_name} 主题",
                lambda n=name: self._switch_theme(n),
            ))

        matcher = self.matcher(query)
        for cmd_name, help_text, callback in commands:
            match = matcher.match(cmd_name)
            if match > 0:
                yield Hit(match, matcher.highlight(cmd_name), callback, help=help_text)

    def _new_session(self) -> None:
        self.app.action_new_session()

    def _reset_session(self) -> None:
        app = self.app
        app._thinking_widget = None
        app._streaming_widget = None
        app._current_tool_widget = None
        app.session = Session(session_id=app.session.id)
        app.query_one("#chat").remove_children()
        app.bundle.session_store.save(app.session)
        app._refresh_sidebar()
        app.notify("会话已重置")

    def _toggle_sidebar(self) -> None:
        self.app.action_toggle_sidebar()

    def _show_status(self) -> None:
        app = self.app
        info = (
            f"模型: {app.bundle.kernel.model}\n"
            f"Trace: {app.bundle.trace_path}\n"
            f"工作区: {app.bundle.workspace}\n"
            f"历史: {len(app.session.history)} 条\n"
            f"主题: {app.theme}"
        )
        app.notify(info, title="状态")

    def _switch_theme(self, name: str) -> None:
        self.app.theme = name
        self.app.notify(f"已切换主题: {name}")

    def _quit(self) -> None:
        self.app.exit()
