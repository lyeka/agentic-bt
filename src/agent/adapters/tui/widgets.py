"""
[INPUT]: textual
[OUTPUT]: StreamingMarkdown — 流式 Markdown 渲染；ToolStatusBar — 工具状态行
[POS]: TUI 自定义 Widget 层，被 app.py 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from textual.timer import Timer
from textual.widgets import Markdown


class StreamingMarkdown(Markdown):
    """流式 Markdown：接收 chunk 后防抖更新，避免逐 token 重渲染。"""

    DEBOUNCE_SEC = 0.08

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._chunks: list[str] = []
        self._dirty = False
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(self.DEBOUNCE_SEC, self._flush)

    def append(self, text: str) -> None:
        self._chunks.append(text)
        self._dirty = True

    def _flush(self) -> None:
        if self._dirty:
            self._dirty = False
            self.update("".join(self._chunks))

    def finalize(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._flush()

    @property
    def full_text(self) -> str:
        return "".join(self._chunks)
