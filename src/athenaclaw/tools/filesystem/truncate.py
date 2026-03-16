"""
[INPUT]: dataclasses
[OUTPUT]: TruncationResult, truncate_head, truncate_tail
[POS]: 工具层私有截断基础设施；read 用 head（看开头），bash 用 tail（看错误）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# 截断结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TruncationResult:
    """截断操作的返回值"""
    content: str
    truncated: bool
    total_lines: int
    kept_lines: int


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

_MAX_LINES = 2000
_MAX_BYTES = 50_000


# ─────────────────────────────────────────────────────────────────────────────
# Head 截断 — 保留前 N 行（用于 read）
# ─────────────────────────────────────────────────────────────────────────────

def truncate_head(
    text: str,
    max_lines: int = _MAX_LINES,
    max_bytes: int = _MAX_BYTES,
) -> TruncationResult:
    """从前往后保留，双限制（行数 + 字节），先到先停。"""
    lines = text.split("\n")
    total = len(lines)

    kept: list[str] = []
    byte_count = 0

    for i, line in enumerate(lines):
        line_bytes = len(line.encode("utf-8")) + (1 if i > 0 else 0)
        if i >= max_lines or byte_count + line_bytes > max_bytes:
            break
        kept.append(line)
        byte_count += line_bytes

    truncated = len(kept) < total
    return TruncationResult(
        content="\n".join(kept),
        truncated=truncated,
        total_lines=total,
        kept_lines=len(kept),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tail 截断 — 保留后 N 行（用于 bash）
# ─────────────────────────────────────────────────────────────────────────────

def truncate_tail(
    text: str,
    max_lines: int = _MAX_LINES,
    max_bytes: int = _MAX_BYTES,
) -> TruncationResult:
    """从后往前保留，双限制（行数 + 字节），先到先停。"""
    lines = text.split("\n")
    total = len(lines)

    kept: list[str] = []
    byte_count = 0

    for i in range(total - 1, -1, -1):
        line = lines[i]
        line_bytes = len(line.encode("utf-8")) + (1 if kept else 0)
        if len(kept) >= max_lines or byte_count + line_bytes > max_bytes:
            break
        kept.insert(0, line)
        byte_count += line_bytes

    truncated = len(kept) < total
    return TruncationResult(
        content="\n".join(kept),
        truncated=truncated,
        total_lines=total,
        kept_lines=len(kept),
    )
