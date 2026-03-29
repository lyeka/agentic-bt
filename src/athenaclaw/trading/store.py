"""
[INPUT]: json, pathlib, datetime
[OUTPUT]: TradePlanStore, TradeAuditLog
[POS]: 交易 plan 与审计的轻量持久层
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from athenaclaw.trading.types import TradePlan


class TradePlanStore:
    def __init__(self, state_dir: Path) -> None:
        self._plans_dir = state_dir / "trade" / "plans"

    def save(self, plan: TradePlan, *, payload: dict[str, Any]) -> None:
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "status": "pending",
            "plan": plan.to_dict(),
            "payload": payload,
            "applied_at": None,
            "result": None,
        }
        self._path(plan.plan_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load(self, plan_id: str) -> dict[str, Any] | None:
        path = self._path(plan_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def mark_applied(self, plan_id: str, *, result: dict[str, Any], applied_at: str | None = None) -> None:
        record = self.load(plan_id)
        if record is None:
            return
        record["status"] = "applied"
        record["applied_at"] = applied_at or datetime.now(timezone.utc).isoformat()
        record["result"] = result
        self._path(plan_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def mark_expired(self, plan_id: str) -> None:
        record = self.load(plan_id)
        if record is None:
            return
        record["status"] = "expired"
        self._path(plan_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _path(self, plan_id: str) -> Path:
        return self._plans_dir / f"{plan_id}.json"


class TradeAuditLog:
    def __init__(self, state_dir: Path) -> None:
        self._audit_dir = state_dir / "trade" / "audit"

    def append(self, record: dict[str, Any]) -> None:
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        path = self._audit_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
