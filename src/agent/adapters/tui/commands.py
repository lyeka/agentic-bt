"""
[INPUT]: textual.command
[OUTPUT]: AppCommandProvider — 命令面板
[POS]: TUI 命令面板扩展：会话重置/侧边栏切换/状态/退出
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from textual.command import Hit, Hits, Provider

from agent.kernel import Session


class AppCommandProvider(Provider):
    """Ctrl+P 命令面板：投资助手操作集合。"""

    async def search(self, query: str) -> Hits:
        app = self.app
        commands = [
            ("重置会话", "清空当前对话历史", self._reset_session),
            ("切换侧边栏", "显示或隐藏右侧工作区面板", self._toggle_sidebar),
            ("查看状态", "显示模型、trace 路径等信息", self._show_status),
            ("退出", "关闭投资助手", self._quit),
        ]
        matcher = self.matcher(query)
        for name, help_text, callback in commands:
            match = matcher.match(name)
            if match > 0:
                yield Hit(match, matcher.highlight(name), callback, help=help_text)

    def _reset_session(self) -> None:
        app = self.app
        app.session = Session(session_id=app.session.id)
        chat = app.query_one("#chat")
        chat.remove_children()
        app.bundle.session_store.save(app.session)
        app.notify("会话已重置")

    def _toggle_sidebar(self) -> None:
        self.app.action_toggle_sidebar()

    def _show_status(self) -> None:
        app = self.app
        info = (
            f"模型: {app.bundle.kernel.model}\n"
            f"Trace: {app.bundle.trace_path}\n"
            f"工作区: {app.bundle.workspace}\n"
            f"历史: {len(app.session.history)} 条"
        )
        app.notify(info, title="状态")

    def _quit(self) -> None:
        self.app.exit()
