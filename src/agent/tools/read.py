"""
[INPUT]: agent.tools._path, agent.tools._truncate, pathlib
[OUTPUT]: register()
[POS]: read 工具 — 文件读取（行号 + 分页 + 截断 + 二进制检测 + 目录列表）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

from agent.tools._path import check_trust, resolve_path
from agent.tools._truncate import truncate_head


def register(kernel: object, workspace: Path, cwd: Path) -> None:
    """向 Kernel 注册 read 工具"""

    def read_handler(args: dict) -> dict:
        raw = args["path"]
        path = resolve_path(workspace, raw)

        err = check_trust(kernel, path, workspace, cwd)
        if err:
            return {"error": err}

        if not path.exists():
            return {"error": f"文件不存在: {raw}"}

        # 目录列表
        if path.is_dir():
            entries = sorted(p.name + ("/" if p.is_dir() else "")
                             for p in path.iterdir())
            return {"entries": entries, "path": raw}

        # 二进制检测
        try:
            head = path.read_bytes()[:1024]
            if b"\x00" in head:
                return {"error": f"二进制文件，无法读取: {raw}"}
        except OSError as e:
            return {"error": f"读取失败: {e}"}

        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
        total = len(lines)

        # 分页
        offset = args.get("offset", 1)
        limit = args.get("limit")
        start = max(0, offset - 1)
        if start >= total:
            return {"error": f"offset {offset} 超出文件范围（共 {total} 行）"}

        end = min(start + limit, total) if limit else total
        selected = lines[start:end]

        # 截断
        text = "\n".join(selected)
        tr = truncate_head(text)

        # 带行号输出
        numbered = []
        for i, line in enumerate(tr.content.split("\n")):
            numbered.append(f"{start + i + 1}| {line}")

        result: dict = {
            "content": "\n".join(numbered),
            "path": raw,
            "total_lines": total,
        }
        if tr.truncated:
            next_off = start + tr.kept_lines + 1
            result["truncated"] = True
            result["kept_lines"] = tr.kept_lines
            result["next_offset"] = next_off
        return result

    kernel.tool(
        name="read",
        description=(
            "读取文件内容（带行号）。支持 offset/limit 分页。"
            "目录路径返回文件列表。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对 workspace 或绝对路径）"},
                "offset": {"type": "integer", "description": "起始行号（1-indexed），默认 1"},
                "limit": {"type": "integer", "description": "读取行数（默认读到截断为止）"},
            },
            "required": ["path"],
        },
        handler=read_handler,
    )
