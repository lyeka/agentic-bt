"""
[INPUT]: pathlib, agent.kernel (Permission)
[OUTPUT]: resolve_path, is_trusted, check_trust
[POS]: 工具层共享路径安全基础设施；双信任区域（workspace + cwd）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 路径解析
# ─────────────────────────────────────────────────────────────────────────────

def resolve_path(workspace: Path, raw: str) -> Path:
    """解析路径：绝对路径直接用，相对路径基于 workspace"""
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (workspace / raw).resolve()


def is_trusted(resolved: Path, workspace: Path, cwd: Path) -> bool:
    """路径是否在信任区域内（workspace 或 cwd）"""
    ws = workspace.resolve()
    wd = cwd.resolve()
    return resolved.is_relative_to(ws) or resolved.is_relative_to(wd)


def check_trust(kernel: object, path: Path, workspace: Path, cwd: Path) -> str | None:
    """信任区域外请求确认。返回 None=通过，str=错误信息。"""
    if is_trusted(path, workspace, cwd):
        return None
    from agent.kernel import Permission
    if kernel.check_permission("__external__") == Permission.USER_CONFIRM:
        if not kernel.request_confirm(str(path)):
            return f"访问被拒绝: {path}"
    return None


def check_write_permission(kernel: object, raw: str, path: Path, workspace: Path, cwd: Path) -> str | None:
    """写操作权限检查：信任区域外走 check_trust，区域内走 Permission 系统。"""
    err = check_trust(kernel, path, workspace, cwd)
    if err:
        return err
    if is_trusted(path, workspace, cwd):
        from agent.kernel import Permission
        level = kernel.check_permission(raw)
        if level == Permission.USER_CONFIRM and not kernel.request_confirm(raw):
            return "需要用户确认"
    return None
