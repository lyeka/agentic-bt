"""
[INPUT]: json, pathlib, agent.messages
[OUTPUT]: SessionStore, JsonSessionStore
[POS]: 会话持久化基础设施（入口无关）：原子写入 + 兼容旧格式
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from athenaclaw.kernel import Session
from athenaclaw.llm.messages import normalize_history


class SessionStore(Protocol):
    """Session 持久化接口（入口无关）。"""

    def load(self) -> Session: ...

    def save(self, session: Session) -> None: ...


@dataclass(frozen=True)
class JsonSessionStore(SessionStore):
    """
    JSON SessionStore（原子写入）。

    兼容旧格式: {"id": "...", "history": [...]}
    新格式: {"version": 2, "id": "...", "history": [...], "updated_at": "..."}
    """

    path: Path

    def load(self) -> Session:
        if not self.path.exists():
            # 约定：文件不存在则返回默认空 Session，id 由调用方自行覆盖/命名
            return Session()

        data = json.loads(self.path.read_text(encoding="utf-8"))

        # 兼容旧格式
        session_id = data.get("id", "default")
        history = data.get("history", [])

        s = Session(session_id=session_id)
        if isinstance(history, list):
            s.history = normalize_history(history)
        s.repair()
        return s

    def save(self, session: Session) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 2,
            "id": session.id,
            "history": normalize_history(session.history),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)
