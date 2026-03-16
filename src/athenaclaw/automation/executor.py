"""
[INPUT]: json, pathlib, string, agent.runtime, agent.kernel, agent.automation.*
[OUTPUT]: AutomationExecutor
[POS]: 自动化 reaction 执行器：TriggerEvent -> pre_alert -> executor -> artifact -> final_result
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from string import Template

from athenaclaw.automation.delivery import DeliveryChannel
from athenaclaw.automation.models import (
    DeliveryPhase,
    TaskDefinition,
    TaskRun,
    TriggerEvent,
    utc_now_iso,
)
from athenaclaw.automation.policy import AutomationToolPolicy
from athenaclaw.automation.store import AutomationStore
from athenaclaw.kernel import Session
from athenaclaw.runtime import AgentConfig, build_kernel_bundle


def _slug(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-") or "task"


class AutomationExecutor:
    def __init__(
        self,
        *,
        config: AgentConfig,
        store: AutomationStore,
        delivery_channels: dict[str, DeliveryChannel],
    ) -> None:
        self._config = config
        self._store = store
        self._delivery_channels = delivery_channels

    def execute(self, task: TaskDefinition, event: TriggerEvent) -> TaskRun:
        run_id = f"{event.task_id}-{event.event_key}"
        existing = self._store.load_run(task.id, run_id)
        if existing is not None:
            return existing
        started_at = utc_now_iso()
        receipts = []

        if task.delivery.pre_alert.enabled:
            receipts.extend(self._deliver(
                phase=task.delivery.pre_alert,
                task=task,
                run_id=run_id,
                kind="pre_alert",
                text=self._render_pre_alert(task, event),
            ))

        try:
            result_text = self._run_reaction(task, event)
            artifact_path = self._write_artifact(task, run_id, result_text)
            if task.delivery.final_result.enabled:
                receipts.extend(self._deliver(
                    phase=task.delivery.final_result,
                    task=task,
                    run_id=run_id,
                    kind="final_result",
                    text=self._render_final_result(task, event, result_text),
                ))
            run = TaskRun(
                run_id=run_id,
                task_id=task.id,
                trigger_event=event,
                executor=task.reaction.executor.type if task.reaction.executor.type == "main_agent" else (
                    f"{task.reaction.executor.type}:{task.reaction.executor.name}"
                ),
                status="succeeded",
                started_at=started_at,
                finished_at=utc_now_iso(),
                artifact_path=str(artifact_path),
                summary_excerpt=result_text[:400],
                delivery_receipts=tuple(receipts),
            )
            self._store.save_run(run)
            return run
        except Exception as exc:
            if task.delivery.on_failure.enabled:
                receipts.extend(self._deliver(
                    phase=task.delivery.on_failure,
                    task=task,
                    run_id=run_id,
                    kind="failure",
                    text=f"自动化任务失败\n\n任务: {task.name}\nrun_id: {run_id}\n错误: {type(exc).__name__}: {exc}",
                ))
            run = TaskRun(
                run_id=run_id,
                task_id=task.id,
                trigger_event=event,
                executor=task.reaction.executor.type if task.reaction.executor.type == "main_agent" else (
                    f"{task.reaction.executor.type}:{task.reaction.executor.name}"
                ),
                status="failed",
                started_at=started_at,
                finished_at=utc_now_iso(),
                delivery_receipts=tuple(receipts),
                error=f"{type(exc).__name__}: {exc}",
            )
            self._store.save_run(run)
            return run

    def _run_reaction(self, task: TaskDefinition, event: TriggerEvent) -> str:
        rendered_prompt = self._render_prompt(task, event)
        executor_type = task.reaction.executor.type

        if executor_type in {"main_agent", "skill"}:
            bundle = build_kernel_bundle(
                config=self._config,
                adapter_name="automation",
                conversation_id=task.id,
                cwd=self._config.workspace_dir.expanduser(),
            )
            bundle.kernel.set_tool_policy(AutomationToolPolicy(
                workspace=bundle.workspace,
                task_id=task.id,
                profile=task.reaction.tool_profile,
            ))
            bundle.kernel.max_rounds = task.reaction.budget.max_rounds
            session = bundle.session_store.load()
            session.id = f"automation:{task.id}"
            if executor_type == "skill":
                text = f"/skill:{task.reaction.executor.name} {rendered_prompt}".strip()
            else:
                text = rendered_prompt
            reply = bundle.kernel.turn(text, session)
            bundle.session_store.save(session)
            return reply

        if executor_type == "subagent":
            bundle = build_kernel_bundle(
                config=self._config,
                adapter_name="automation",
                conversation_id=task.id,
                cwd=self._config.workspace_dir.expanduser(),
            )
            bundle.kernel.set_tool_policy(AutomationToolPolicy(
                workspace=bundle.workspace,
                task_id=task.id,
                profile=task.reaction.tool_profile,
            ))
            system = getattr(bundle.kernel, "_subagent_system", None)
            if system is None:
                raise RuntimeError("当前 workspace 中没有可用 subagent")
            context = self._build_subagent_context(task.id, event)
            result = system.invoke(str(task.reaction.executor.name), rendered_prompt, context)
            return result.response

        raise RuntimeError(f"未知 executor.type: {executor_type}")

    def _build_subagent_context(self, task_id: str, event: TriggerEvent) -> str:
        recent = self._store.list_runs(task_id, limit=3)
        lines = [
            "<automation_context>",
            json.dumps(event.to_dict(), ensure_ascii=False, indent=2),
        ]
        if recent:
            lines.append("<recent_runs>")
            for run in recent:
                lines.append(
                    json.dumps(
                        {
                            "run_id": run.run_id,
                            "status": run.status,
                            "summary_excerpt": run.summary_excerpt,
                            "artifact_path": run.artifact_path,
                        },
                        ensure_ascii=False,
                    )
                )
            lines.append("</recent_runs>")
        lines.append("</automation_context>")
        return "\n".join(lines)

    def _write_artifact(self, task: TaskDefinition, run_id: str, content: str) -> Path:
        task_dir = self._config.workspace_dir.expanduser() / "notebook" / "automation" / _slug(task.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / f"{_slug(run_id)}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _deliver(
        self,
        *,
        phase: DeliveryPhase,
        task: TaskDefinition,
        run_id: str,
        kind: str,
        text: str,
    ):
        receipts = []
        for channel in phase.channels:
            if channel.type == "none":
                continue
            backend = self._delivery_channels.get(channel.type)
            if backend is None:
                continue
            items = backend.send(
                target=channel.target,
                text=text,
                task_id=task.id,
                run_id=run_id,
                kind=kind,
            )
            for receipt in items:
                self._store.save_receipt(receipt)
                receipts.append(receipt)
        return receipts

    def _render_prompt(self, task: TaskDefinition, event: TriggerEvent) -> str:
        mapping = dict(event.payload)
        mapping.setdefault("task_id", task.id)
        mapping.setdefault("task_name", task.name)
        mapping.setdefault("run_id", f"{event.task_id}-{event.event_key}")
        mapping.setdefault("triggered_at", event.triggered_at)
        mapping.setdefault("event_key", event.event_key)
        return Template(task.reaction.prompt_template).safe_substitute(mapping)

    def _render_pre_alert(self, task: TaskDefinition, event: TriggerEvent) -> str:
        payload = event.payload
        return (
            f"价格事件触发\n\n"
            f"任务: {task.name}\n"
            f"标的: {payload.get('symbol', '-')}\n"
            f"方向: {payload.get('condition', '-')}\n"
            f"价格: {payload.get('current_price', '-')}\n"
            f"阈值: {payload.get('threshold', '-')}\n"
            f"as_of: {payload.get('as_of', '-')}"
        )

    def _render_final_result(self, task: TaskDefinition, event: TriggerEvent, result_text: str) -> str:
        return (
            f"自动化任务完成\n\n"
            f"任务: {task.name}\n"
            f"run_id: {event.task_id}-{event.event_key}\n\n"
            f"{result_text}"
        )
