"""
[INPUT]: agent.kernel (Kernel, Permission), pathlib
[OUTPUT]: register()
[POS]: 通用原语工具 read/write/edit；write/edit 经过权限检查 + emit 管道事件
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, workspace: Path) -> None:
    """向 Kernel 注册 read/write/edit 三个通用原语"""

    # ── read ──────────────────────────────────────────────────────────────

    def read_handler(args: dict) -> dict:
        rel = args["path"]
        path = workspace / rel
        if not path.exists():
            return {"error": f"文件不存在: {rel}"}
        if path.is_dir():
            entries = sorted(p.relative_to(workspace) for p in path.iterdir())
            return {"entries": [str(e) for e in entries], "path": rel}
        return {"content": path.read_text(encoding="utf-8"), "path": rel}

    kernel.tool(
        name="read",
        description="读取工作区文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径"},
            },
            "required": ["path"],
        },
        handler=read_handler,
    )

    # ── write ─────────────────────────────────────────────────────────────

    def write_handler(args: dict) -> dict:
        rel = args["path"]
        from agent.kernel import Permission
        level = kernel.check_permission(rel)
        if level == Permission.USER_CONFIRM and not kernel.request_confirm(rel):
            return {"error": "需要用户确认", "path": rel, "permission": "user_confirm"}

        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        kernel.emit(f"write:{rel}", {"path": rel})
        return {"status": "ok", "path": rel}

    kernel.tool(
        name="write",
        description="写入工作区文件（自动创建目录）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
        handler=write_handler,
    )

    # ── edit ──────────────────────────────────────────────────────────────

    def edit_handler(args: dict) -> dict:
        rel = args["path"]
        from agent.kernel import Permission
        level = kernel.check_permission(rel)
        if level == Permission.USER_CONFIRM and not kernel.request_confirm(rel):
            return {"error": "需要用户确认", "path": rel, "permission": "user_confirm"}

        path = workspace / rel
        if not path.exists():
            return {"error": f"文件不存在: {rel}"}

        content = path.read_text(encoding="utf-8")
        old = args["old_string"]
        new = args["new_string"]
        if old not in content:
            return {"error": "未找到匹配文本", "path": rel}

        path.write_text(content.replace(old, new, 1), encoding="utf-8")
        kernel.emit(f"edit:{rel}", {"path": rel})
        return {"status": "ok", "path": rel}

    kernel.tool(
        name="edit",
        description="diff-based 修改工作区文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径"},
                "old_string": {"type": "string", "description": "要替换的文本"},
                "new_string": {"type": "string", "description": "替换后的文本"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=edit_handler,
    )
