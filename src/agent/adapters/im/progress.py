"""
[INPUT]: dataclasses
[OUTPUT]: ProgressBuffer
[POS]: IM 通用进度渲染（工具调用摘要、节流前的文本构建）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProgressBuffer:
    """保存最近的进度行，渲染为适配器友好的纯文本。"""

    max_lines: int = 10
    _lines: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self._lines.clear()

    def append(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        self._lines.append(line)
        if len(self._lines) > self.max_lines:
            self._lines = self._lines[-self.max_lines :]

    def render(self) -> str:
        if not self._lines:
            return ""
        return "\n".join(self._lines)

