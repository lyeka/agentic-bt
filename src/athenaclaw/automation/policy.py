"""
[INPUT]: pathlib, agent.kernel, agent.tools._path
[OUTPUT]: AutomationToolPolicy
[POS]: 自动化 reaction 的工具访问控制
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

from athenaclaw.kernel import ToolAccessPolicy
from athenaclaw.tools.filesystem.path import resolve_path


_ALWAYS_DENIED = {
    "bash",
    "task_plan",
    "task_apply",
    "task_control",
    "create_subagent",
}


class AutomationToolPolicy(ToolAccessPolicy):
    def __init__(
        self,
        *,
        workspace: Path,
        task_id: str,
        profile: str,
    ) -> None:
        self._workspace = workspace
        self._task_id = task_id
        self._profile = profile

    def authorize(self, name: str, args: dict[str, object]) -> str | None:
        if name in _ALWAYS_DENIED:
            return f"自动化任务禁止调用工具: {name}"
        if name in {"read", "write", "edit"}:
            raw = str(args.get("path", ""))
            path = resolve_path(self._workspace, raw)
            if not path.is_relative_to(self._workspace.resolve()):
                return "自动化任务不能访问 workspace 之外的路径"
            blocked = (
                (self._workspace / "automation" / "tasks").resolve(),
                (self._workspace / "soul.md").resolve(),
            )
            if any(path == item or path.is_relative_to(item) for item in blocked):
                return f"自动化任务不能访问路径: {raw}"
        return None
