"""
[INPUT]: json, datetime, pathlib
[OUTPUT]: TraceWriter — 本地 JSONL 追踪写入器
[POS]: 公共可观测性基础，被 agenticbt 和 agent 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# TraceWriter
# ─────────────────────────────────────────────────────────────────────────────

class TraceWriter:
    """
    本地 JSONL 追踪写入器 — 对齐 OTel GenAI Semantic Conventions。

    每次 write() 追加一行 JSON 到文件，自动填充 ts。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._bar_index = 0

    def set_bar(self, bar_index: int) -> None:
        self._bar_index = bar_index

    def write(self, event: dict[str, Any]) -> None:
        event["ts"] = datetime.now().isoformat()
        event.setdefault("bar_index", self._bar_index)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
