"""
[INPUT]: json, pathlib, datetime
[OUTPUT]: TradeAuditLog
[POS]: 交易审计的轻量持久层
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeAuditLog:
    def __init__(self, state_dir: Path) -> None:
        self._audit_dir = state_dir / "trade" / "audit"

    def append(self, record: dict[str, Any]) -> None:
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        path = self._audit_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
