"""
[INPUT]: 纯文本字符串
[OUTPUT]: chunk_text
[POS]: IM/Delivery 共用的长文本分片逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations


def chunk_text(text: str, *, max_len: int) -> list[str]:
    """保守分片：优先按段落/换行切分，避免触发平台长度限制。"""
    s = (text or "").strip()
    if not s:
        return [""]

    if len(s) <= max_len:
        return [s]

    parts: list[str] = []
    buf = ""
    for para in s.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        candidate = (buf + ("\n\n" if buf else "") + para) if buf else para
        if len(candidate) <= max_len:
            buf = candidate
            continue
        if buf:
            parts.append(buf)
            buf = ""
        for line in para.split("\n"):
            line = line.rstrip()
            candidate2 = (buf + "\n" + line) if buf else line
            if len(candidate2) <= max_len:
                buf = candidate2
                continue
            if buf:
                parts.append(buf)
                buf = ""
            for i in range(0, len(line), max_len):
                parts.append(line[i : i + max_len])
    if buf:
        parts.append(buf)
    return parts
