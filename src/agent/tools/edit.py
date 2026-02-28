"""
[INPUT]: agent.tools._path, difflib, re, pathlib
[OUTPUT]: register()
[POS]: edit 工具 — 精确文本替换（模糊匹配 + 唯一性检查 + diff 输出）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from agent.tools._path import check_write_permission, resolve_path


# ─────────────────────────────────────────────────────────────────────────────
# 模糊匹配
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """规范化：去行尾空白 + Unicode 引号/破折号归一化"""
    lines = [line.rstrip() for line in text.split("\n")]
    result = "\n".join(lines)
    # 智能引号 → ASCII
    result = re.sub(r"[\u2018\u2019\u201a\u201b]", "'", result)
    result = re.sub(r'[\u201c\u201d\u201e\u201f]', '"', result)
    # 各种破折号 → ASCII 连字符
    result = re.sub(r"[\u2010-\u2015\u2212]", "-", result)
    return result


def _fuzzy_find(content: str, old_text: str) -> tuple[bool, str, str]:
    """
    查找 old_text 在 content 中的位置。
    先精确匹配，失败后规范化重试。
    返回 (found, work_content, work_old)。
    """
    if old_text in content:
        return True, content, old_text
    norm_c = _normalize(content)
    norm_o = _normalize(old_text)
    if norm_o in norm_c:
        return True, norm_c, norm_o
    return False, content, old_text


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, workspace: Path, cwd: Path) -> None:
    """向 Kernel 注册 edit 工具"""

    def edit_handler(args: dict) -> dict:
        raw = args["path"]
        path = resolve_path(workspace, raw)

        err = check_write_permission(kernel, raw, path, workspace, cwd)
        if err:
            return {"error": err, "path": raw, "permission": "user_confirm"}

        if not path.exists():
            return {"error": f"文件不存在: {raw}"}

        content = path.read_text(encoding="utf-8")
        old = args["old_string"]
        new = args["new_string"]

        # 模糊匹配
        found, work_content, work_old = _fuzzy_find(content, old)
        if not found:
            return {"error": "未找到匹配文本", "path": raw}

        # 唯一性检查
        count = work_content.count(work_old)
        if count > 1:
            return {
                "error": f"找到 {count} 处匹配，请提供更多上下文使其唯一",
                "path": raw,
                "occurrences": count,
            }

        # 执行替换
        new_content = work_content.replace(work_old, new, 1)
        path.write_text(new_content, encoding="utf-8")
        kernel.emit(f"edit:{raw}", {"path": raw})

        # 生成 diff
        old_lines = work_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(old_lines, new_lines, n=3))

        # 计算首个变更行号
        first_changed = None
        for i, (a, b) in enumerate(
            zip(work_content.split("\n"), new_content.split("\n"))
        ):
            if a != b:
                first_changed = i + 1
                break
        if first_changed is None and len(new_content.split("\n")) != len(work_content.split("\n")):
            first_changed = min(len(work_content.split("\n")), len(new_content.split("\n"))) + 1

        return {
            "status": "ok",
            "path": raw,
            "diff": diff,
            "first_changed_line": first_changed,
        }

    kernel.tool(
        name="edit",
        description=(
            "精确文本替换（支持模糊匹配）。old_string 必须在文件中唯一。"
            "返回 unified diff。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对 workspace 或绝对路径）"},
                "old_string": {"type": "string", "description": "要替换的文本（必须唯一）"},
                "new_string": {"type": "string", "description": "替换后的文本"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=edit_handler,
    )
