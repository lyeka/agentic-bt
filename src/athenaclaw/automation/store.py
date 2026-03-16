"""
[INPUT]: json, hashlib, pathlib, yaml, agent.automation.models
[OUTPUT]: AutomationStore
[POS]: 自动化子系统持久化层：tasks/drafts/state/runs/receipts 的文件存储
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from athenaclaw.automation.models import (
    DeliveryReceipt,
    TaskDefinition,
    TaskDraft,
    TaskRun,
    TaskRuntimeState,
    parse_delivery_receipt,
    parse_runtime_state,
    parse_task_definition,
    parse_task_run,
)


def _safe_name(raw: str) -> str:
    return raw.replace("/", "_")


class AutomationStore:
    def __init__(self, *, workspace: Path, state: Path) -> None:
        self._workspace = workspace
        self._state = state
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def tasks_dir(self) -> Path:
        return self._workspace / "automation" / "tasks"

    @property
    def drafts_dir(self) -> Path:
        return self._state / "automation" / "drafts"

    @property
    def runtime_dir(self) -> Path:
        return self._state / "automation" / "tasks"

    @property
    def runs_dir(self) -> Path:
        return self._state / "automation" / "runs"

    @property
    def receipts_dir(self) -> Path:
        return self._state / "automation" / "receipts"

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{_safe_name(task_id)}.yaml"

    def draft_path(self, draft_id: str) -> Path:
        return self.drafts_dir / f"{_safe_name(draft_id)}.json"

    def runtime_path(self, task_id: str) -> Path:
        return self.runtime_dir / f"{_safe_name(task_id)}.json"

    def run_dir(self, task_id: str) -> Path:
        return self.runs_dir / _safe_name(task_id)

    def run_path(self, task_id: str, run_id: str) -> Path:
        return self.run_dir(task_id) / f"{_safe_name(run_id)}.json"

    def receipt_path(self, receipt: DeliveryReceipt) -> Path:
        return (
            self.receipts_dir
            / _safe_name(receipt.channel)
            / _safe_name(receipt.target)
            / f"{_safe_name(receipt.outbound_message_id)}.json"
        )

    def save_task(self, task: TaskDefinition) -> None:
        path = self.task_path(task.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(task.to_dict(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def load_task(self, task_id: str) -> TaskDefinition | None:
        path = self.task_path(task_id)
        if not path.exists():
            return None
        return parse_task_definition(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def list_tasks(self) -> list[TaskDefinition]:
        tasks: list[TaskDefinition] = []
        for path in sorted(self.tasks_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            tasks.append(parse_task_definition(data))
        return tasks

    def save_draft(self, draft: TaskDraft) -> None:
        path = self.draft_path(draft.draft_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_draft(self, draft_id: str) -> TaskDraft | None:
        path = self.draft_path(draft_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TaskDraft(
            draft_id=str(data.get("draft_id", "")).strip(),
            task=parse_task_definition(dict(data.get("task") or {})),
            preview=str(data.get("preview", "")),
            warnings=tuple(str(item) for item in (data.get("warnings") or [])),
            created_at=str(data.get("created_at", "")),
        )

    def delete_draft(self, draft_id: str) -> None:
        path = self.draft_path(draft_id)
        if path.exists():
            path.unlink()

    def save_runtime_state(self, state: TaskRuntimeState) -> None:
        path = self.runtime_path(state.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_runtime_state(self, task_id: str) -> TaskRuntimeState:
        path = self.runtime_path(task_id)
        if not path.exists():
            return TaskRuntimeState(task_id=task_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return parse_runtime_state(data)

    def save_run(self, run: TaskRun) -> None:
        path = self.run_path(run.task_id, run.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_run(self, task_id: str, run_id: str) -> TaskRun | None:
        path = self.run_path(task_id, run_id)
        if not path.exists():
            return None
        return parse_task_run(json.loads(path.read_text(encoding="utf-8")))

    def list_runs(self, task_id: str, *, limit: int | None = None) -> list[TaskRun]:
        run_dir = self.run_dir(task_id)
        if not run_dir.exists():
            return []
        items: list[TaskRun] = []
        for path in sorted(run_dir.glob("*.json"), key=lambda p: p.name, reverse=True):
            items.append(parse_task_run(json.loads(path.read_text(encoding="utf-8"))))
            if limit is not None and len(items) >= limit:
                break
        return items

    def save_receipt(self, receipt: DeliveryReceipt) -> None:
        path = self.receipt_path(receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def find_receipt(self, *, channel: str, target: str, outbound_message_id: str) -> DeliveryReceipt | None:
        path = self.receipts_dir / _safe_name(channel) / _safe_name(target) / f"{_safe_name(outbound_message_id)}.json"
        if not path.exists():
            return None
        return parse_delivery_receipt(json.loads(path.read_text(encoding="utf-8")))

    def task_spec_hash(self, task: TaskDefinition) -> str:
        payload = json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def latest_run(self, task_id: str) -> TaskRun | None:
        runs = self.list_runs(task_id, limit=1)
        return runs[0] if runs else None

    def task_overview(self, task_id: str) -> dict[str, Any]:
        task = self.load_task(task_id)
        state = self.load_runtime_state(task_id)
        latest = self.latest_run(task_id)
        return {
            "task": task.to_dict() if task else None,
            "state": state.to_dict(),
            "latest_run": latest.to_dict() if latest else None,
        }
