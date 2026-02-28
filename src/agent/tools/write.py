"""
[INPUT]: agent.tools._path, pathlib
[OUTPUT]: register()
[POS]: write 工具 — 文件写入（自动创建目录 + 权限检查 + 字节数反馈）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

from agent.tools._path import check_write_permission, resolve_path


def register(kernel: object, workspace: Path, cwd: Path) -> None:
    """向 Kernel 注册 write 工具"""

    def write_handler(args: dict) -> dict:
        raw = args["path"]
        path = resolve_path(workspace, raw)

        err = check_write_permission(kernel, raw, path, workspace, cwd)
        if err:
            return {"error": err, "path": raw, "permission": "user_confirm"}

        content = args["content"]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        path.write_bytes(data)
        kernel.emit(f"write:{raw}", {"path": raw})
        return {"status": "ok", "path": raw, "bytes_written": len(data)}

    kernel.tool(
        name="write",
        description="写入文件（自动创建目录）。返回写入字节数。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对 workspace 或绝对路径）"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
        handler=write_handler,
    )
