from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd

from agent.adapters.market.schema import build_market_query, make_fetch_result
from agent.automation.models import (
    TaskRun,
    TriggerEvent,
    TaskDefinition,
    parse_task_definition,
    utc_now_iso,
)
from agent.automation.store import AutomationStore
from agent.automation.tools import register as register_automation_tools
from agent.automation.worker import AutomationWorker
from agent.kernel import ExecutionContext, Kernel
from agent.messages import ContextRef
from agent.tools import edit, write


def _price_task(*, threshold: float = 100.0) -> TaskDefinition:
    now = utc_now_iso()
    return parse_task_definition(
        {
            "id": "aapl-watch",
            "name": "AAPL Watch",
            "description": "alert on breakout",
            "status": "active",
            "trigger": {
                "type": "price_threshold",
                "symbol": "AAPL",
                "interval": "1m",
                "condition": "cross_above",
                "threshold": threshold,
                "poll_sec": 60,
                "cooldown_sec": 120,
                "max_data_age_sec": 120,
            },
            "reaction": {
                "executor": {"type": "main_agent"},
                "prompt_template": "AAPL crossed ${threshold}",
                "tool_profile": "analysis",
                "budget": {"max_rounds": 4, "timeout_sec": 30},
            },
            "delivery": {},
            "created_at": now,
            "updated_at": now,
        }
    )


class _SequenceMarketAdapter:
    name = "seq"

    def __init__(self, snapshots: list[tuple[float, datetime]]) -> None:
        self._snapshots = list(snapshots)

    def fetch(self, query):
        price, as_of = self._snapshots.pop(0)
        df = pd.DataFrame(
            {
                "date": [pd.Timestamp(as_of.replace(tzinfo=None))],
                "open": [price],
                "high": [price],
                "low": [price],
                "close": [price],
                "volume": [100],
            }
        )
        return make_fetch_result(
            df=df,
            query=query,
            source=self.name,
            timezone=query.timezone,
        )


class _RecordingExecutor:
    def __init__(self) -> None:
        self.events: list[TriggerEvent] = []

    def execute(self, task: TaskDefinition, event: TriggerEvent) -> TaskRun:
        self.events.append(event)
        return TaskRun(
            run_id=f"{task.id}-{event.event_key}",
            task_id=task.id,
            trigger_event=event,
            executor="main_agent",
            status="succeeded",
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            summary_excerpt="ok",
        )


class _NoConfirmKernel(Kernel):
    def request_confirm(self, path: str) -> bool:  # pragma: no cover - should not be called
        raise AssertionError(f"unexpected confirm request: {path}")


def test_task_plan_apply_and_context_default_selector(tmp_path):
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    store = AutomationStore(workspace=workspace, state=state)
    kernel = Kernel(api_key="test")
    register_automation_tools(
        kernel,
        store=store,
        adapter_name="telegram",
        conversation_id="12345",
        default_timezone="Asia/Shanghai",
    )

    draft = kernel._tools["task_plan"].handler(
        {
            "task": {
                "name": "daily-stock-note",
                "description": "daily market note",
                "trigger": {
                    "type": "cron",
                    "cron_expr": "0 9 * * *",
                },
                "reaction": {
                    "executor": {"type": "main_agent"},
                    "prompt_template": "Analyze today's watchlist.",
                },
            }
        }
    )

    assert draft["task"]["trigger"]["timezone"] == "Asia/Shanghai"
    channels = draft["task"]["delivery"]["final_result"]["channels"]
    assert channels == [{"type": "telegram", "target": "12345"}]

    applied = kernel._tools["task_apply"].handler({"draft_id": draft["draft_id"]})
    assert applied["status"] == "ok"

    task_id = applied["task_id"]
    run_id = f"{task_id}-cron:2026-03-12T01:00:00+00:00"
    artifact = workspace / "notebook" / "automation" / task_id / "run.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("line1\nline2\nline3", encoding="utf-8")
    store.save_run(
        TaskRun(
            run_id=run_id,
            task_id=task_id,
            trigger_event=TriggerEvent(
                event_key="cron:2026-03-12T01:00:00+00:00",
                task_id=task_id,
                trigger_type="cron",
                payload={"scheduled_at": "2026-03-12T01:00:00+00:00"},
                triggered_at="2026-03-12T01:00:01+00:00",
            ),
            executor="main_agent",
            status="succeeded",
            started_at="2026-03-12T01:00:01+00:00",
            finished_at="2026-03-12T01:00:05+00:00",
            artifact_path=str(artifact),
            summary_excerpt="done",
        )
    )

    kernel._execution_context = ExecutionContext(
        refs=(
            ContextRef("automation_task", task_id),
            ContextRef("automation_run", run_id),
        )
    )
    excerpt = kernel._tools["task_context"].handler({"view": "artifact_excerpt", "lines": 2})
    overview = kernel._tools["task_context"].handler({"view": "overview"})

    assert excerpt["run_id"] == run_id
    assert excerpt["artifact_excerpt"] == "line1\nline2"
    assert overview["task"]["id"] == task_id


def test_task_apply_and_control_do_not_require_confirm(tmp_path):
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    store = AutomationStore(workspace=workspace, state=state)
    kernel = _NoConfirmKernel(api_key="test")
    register_automation_tools(
        kernel,
        store=store,
        adapter_name="telegram",
        conversation_id="12345",
        default_timezone="Asia/Shanghai",
    )

    draft = kernel._tools["task_plan"].handler(
        {
            "task": {
                "name": "auto-no-confirm",
                "description": "apply directly",
                "trigger": {
                    "type": "cron",
                    "cron_expr": "0 9 * * *",
                },
                "reaction": {
                    "executor": {"type": "main_agent"},
                    "prompt_template": "Analyze today's watchlist.",
                },
            }
        }
    )

    applied = kernel._tools["task_apply"].handler({"draft_id": draft["draft_id"]})
    assert applied["status"] == "ok"

    paused = kernel._tools["task_control"].handler(
        {"task_id": applied["task_id"], "action": "pause"}
    )
    assert paused == {
        "status": "ok",
        "task_id": applied["task_id"],
        "new_status": "paused",
    }


def test_task_plan_needs_clarification_for_market_calendar_language(tmp_path):
    store = AutomationStore(workspace=tmp_path / "workspace", state=tmp_path / "state")
    kernel = Kernel(api_key="test")
    register_automation_tools(
        kernel,
        store=store,
        adapter_name="telegram",
        conversation_id="12345",
        default_timezone="Asia/Shanghai",
    )

    result = kernel._tools["task_plan"].handler(
        {
            "task": {
                "name": "close-review",
                "description": "market close review",
                "trigger": {
                    "type": "cron",
                    "cron_expr": "0 15 * * *",
                },
                "reaction": {
                    "executor": {"type": "main_agent"},
                    "prompt_template": "请在收盘后分析我的持仓。",
                },
            }
        }
    )

    assert result["status"] == "needs_clarification"
    assert any("市场日历语义" in item for item in result["warnings"])
    assert list(store.drafts_dir.glob("*.json")) == []


def test_task_plan_returns_guidance_for_non_canonical_shape(tmp_path):
    store = AutomationStore(workspace=tmp_path / "workspace", state=tmp_path / "state")
    kernel = Kernel(api_key="test")
    register_automation_tools(
        kernel,
        store=store,
        adapter_name="telegram",
        conversation_id="12345",
        default_timezone="Asia/Shanghai",
    )

    result = kernel._tools["task_plan"].handler(
        {
            "task": {
                "name": "每日持仓盈亏复盘",
                "schedule": {"type": "cron", "cron": "53 21 * * 0-4", "timezone": "Asia/Shanghai"},
                "steps": [{"tool": "market_ohlcv", "symbol": "002130.SZ"}],
                "output": {"channel": "tg", "text": "{{result}}"},
            }
        }
    )

    assert "error" in result
    assert any("schedule" in item for item in result["hints"])
    assert any("cron_expr" in item for item in result["hints"])
    assert any("steps" in item for item in result["hints"])
    assert any("output" in item for item in result["hints"])
    assert result["expected_shape"]["trigger"]["cron_expr"] == "53 21 * * 0-4"


def test_write_and_edit_reject_automation_task_specs(tmp_path):
    kernel = Kernel(api_key="test")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write.register(kernel, workspace, cwd=workspace)
    edit.register(kernel, workspace, cwd=workspace)

    write_result = kernel._tools["write"].handler(
        {"path": "automation/tasks/demo.yaml", "content": "x"}
    )
    edit_result = kernel._tools["edit"].handler(
        {"path": "automation/tasks/demo.yaml", "old_string": "x", "new_string": "y"}
    )

    assert "只能通过 task_apply 修改" in write_result["error"]
    assert "只能通过 task_apply 修改" in edit_result["error"]


def test_price_threshold_worker_crosses_once_per_rearm_cycle(tmp_path):
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    store = AutomationStore(workspace=workspace, state=state)
    task = _price_task()
    store.save_task(task)

    base = datetime(2026, 3, 12, 1, 0, tzinfo=timezone.utc)
    adapter = _SequenceMarketAdapter(
        [
            (99.0, base),
            (101.0, base + timedelta(seconds=61)),
            (102.0, base + timedelta(seconds=122)),
            (102.0, base + timedelta(seconds=243)),
            (98.0, base + timedelta(seconds=304)),
            (101.0, base + timedelta(seconds=365)),
        ]
    )
    executor = _RecordingExecutor()
    worker = AutomationWorker(
        config=None,  # type: ignore[arg-type]
        store=store,
        market_adapter=adapter,
        executor=executor,
    )

    for offset in (0, 61, 122, 243, 304, 365):
        asyncio.run(worker.tick(base + timedelta(seconds=offset)))

    assert len(executor.events) == 2
    assert executor.events[0].payload["current_price"] == 101.0
    assert executor.events[1].payload["current_price"] == 101.0
    runtime = store.load_runtime_state(task.id)
    assert runtime.last_side == "above"


def test_worker_skips_cron_misfire_beyond_grace(tmp_path):
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    store = AutomationStore(workspace=workspace, state=state)
    now = utc_now_iso()
    task = parse_task_definition(
        {
            "id": "daily-note",
            "name": "Daily Note",
            "description": "",
            "status": "active",
            "trigger": {
                "type": "cron",
                "cron_expr": "* * * * *",
                "timezone": "UTC",
                "misfire_grace_sec": 10,
            },
            "reaction": {
                "executor": {"type": "main_agent"},
                "prompt_template": "say hi",
            },
            "delivery": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    store.save_task(task)
    state_obj = store.load_runtime_state(task.id)
    state_obj.next_fire_at = "2026-03-12T00:00:00+00:00"
    store.save_runtime_state(state_obj)

    executor = _RecordingExecutor()
    worker = AutomationWorker(
        config=None,  # type: ignore[arg-type]
        store=store,
        market_adapter=_SequenceMarketAdapter([(1.0, datetime.now(timezone.utc))]),
        executor=executor,
    )

    asyncio.run(worker.tick(datetime(2026, 3, 12, 0, 5, tzinfo=timezone.utc)))

    assert executor.events == []
    updated = store.load_runtime_state(task.id)
    assert updated.next_fire_at is not None
    assert updated.next_fire_at > "2026-03-12T00:05:00+00:00"
