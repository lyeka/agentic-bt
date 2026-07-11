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


# trade_execute 不在硬禁清单里：Agent 已是自主交易操作员，automation 可执行交易。
# ⚠️ 风控专题首要 TODO：无人值守 automation 对 real 账户裸奔风险最高——
# 当前 orchestrator 传给 RiskGuard 的 RiskContext.automation 字段就是为它预留的挂钩，
# 但 AllowAllGuard 恒 ALLOW，此刻没有任何拦截。方案在此显式标注，不假装安全。
_ALWAYS_DENIED = {
    "bash",
    "task_plan",
    "task_apply",
    "task_control",
    "create_subagent",
}


class AutomationToolPolicy(ToolAccessPolicy):
    # automation 标记：交易工具据此把 RiskContext.automation 置 True。
    # 单点标记，不散落到别处判断“这是不是自动化触发”。
    automation = True

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
