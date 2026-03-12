"""
[INPUT]: dataclasses, datetime, typing, zoneinfo
[OUTPUT]: automation 领域模型与校验辅助
[POS]: 自动化子系统协议层：TaskDefinition / Draft / Run / Receipt / TriggerEvent / 校验
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


TASK_STATUSES = {"active", "paused", "archived"}
DELIVERY_CHANNELS = {"telegram", "webhook", "none"}
EXECUTOR_TYPES = {"main_agent", "skill", "subagent"}
TOOL_PROFILES = {"analysis", "report_writer"}
TRIGGER_TYPES = {"cron", "price_threshold"}
CONTROL_ACTIONS = {"pause", "resume", "archive"}
TASK_CONTEXT_VIEWS = {
    "overview",
    "status",
    "latest_run",
    "recent_runs",
    "run_detail",
    "artifact_excerpt",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CronTrigger:
    type: str
    cron_expr: str
    timezone: str
    misfire_grace_sec: int = 300

    def __post_init__(self) -> None:
        if self.type != "cron":
            raise ValueError("cron trigger type must be 'cron'")
        _validate_timezone(self.timezone)
        if not str(self.cron_expr or "").strip():
            raise ValueError("cron_expr 不能为空")
        if self.misfire_grace_sec < 0:
            raise ValueError("misfire_grace_sec 不能小于 0")


@dataclass(frozen=True)
class PriceThresholdTrigger:
    type: str
    symbol: str
    interval: str
    condition: str
    threshold: float
    poll_sec: int
    cooldown_sec: int = 0
    max_data_age_sec: int = 120

    def __post_init__(self) -> None:
        if self.type != "price_threshold":
            raise ValueError("price threshold trigger type must be 'price_threshold'")
        if not str(self.symbol or "").strip():
            raise ValueError("symbol 不能为空")
        if self.interval not in {"1m", "5m", "15m", "30m", "60m"}:
            raise ValueError("interval 必须是分钟级")
        if self.condition not in {"cross_above", "cross_below"}:
            raise ValueError("condition 必须是 cross_above 或 cross_below")
        if self.poll_sec <= 0:
            raise ValueError("poll_sec 必须大于 0")
        if self.cooldown_sec < 0:
            raise ValueError("cooldown_sec 不能小于 0")
        if self.max_data_age_sec <= 0:
            raise ValueError("max_data_age_sec 必须大于 0")


TriggerSpec = CronTrigger | PriceThresholdTrigger


@dataclass(frozen=True)
class ReactionBudget:
    max_rounds: int = 8
    timeout_sec: int = 120

    def __post_init__(self) -> None:
        if self.max_rounds <= 0:
            raise ValueError("max_rounds 必须大于 0")
        if self.timeout_sec <= 0:
            raise ValueError("timeout_sec 必须大于 0")


@dataclass(frozen=True)
class ReactionExecutor:
    type: str
    name: str | None = None

    def __post_init__(self) -> None:
        if self.type not in EXECUTOR_TYPES:
            raise ValueError(f"executor.type 必须是 {sorted(EXECUTOR_TYPES)}")
        if self.type in {"skill", "subagent"} and not str(self.name or "").strip():
            raise ValueError(f"{self.type} executor 需要 name")


@dataclass(frozen=True)
class ReactionSpec:
    executor: ReactionExecutor
    prompt_template: str
    tool_profile: str = "analysis"
    budget: ReactionBudget = field(default_factory=ReactionBudget)

    def __post_init__(self) -> None:
        if self.tool_profile not in TOOL_PROFILES:
            raise ValueError(f"tool_profile 必须是 {sorted(TOOL_PROFILES)}")
        if not str(self.prompt_template or "").strip():
            raise ValueError("prompt_template 不能为空")


@dataclass(frozen=True)
class DeliveryTarget:
    type: str
    target: str

    def __post_init__(self) -> None:
        if self.type not in DELIVERY_CHANNELS:
            raise ValueError(f"delivery target type 必须是 {sorted(DELIVERY_CHANNELS)}")
        if self.type != "none" and not str(self.target or "").strip():
            raise ValueError("delivery target 不能为空")


@dataclass(frozen=True)
class DeliveryPhase:
    enabled: bool = False
    channels: tuple[DeliveryTarget, ...] = ()


@dataclass(frozen=True)
class DeliverySpec:
    pre_alert: DeliveryPhase = field(default_factory=DeliveryPhase)
    final_result: DeliveryPhase = field(default_factory=lambda: DeliveryPhase(enabled=True))
    on_failure: DeliveryPhase = field(default_factory=lambda: DeliveryPhase(enabled=True))


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    name: str
    description: str
    status: str
    trigger: TriggerSpec
    reaction: ReactionSpec
    delivery: DeliverySpec
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("task id 不能为空")
        if not str(self.name or "").strip():
            raise ValueError("task name 不能为空")
        if self.status not in TASK_STATUSES:
            raise ValueError(f"task status 必须是 {sorted(TASK_STATUSES)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "trigger": trigger_to_dict(self.trigger),
            "reaction": reaction_to_dict(self.reaction),
            "delivery": delivery_to_dict(self.delivery),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TriggerEvent:
    event_key: str
    task_id: str
    trigger_type: str
    payload: dict[str, Any]
    triggered_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskDraft:
    draft_id: str
    task: TaskDefinition
    preview: str
    warnings: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "task": self.task.to_dict(),
            "preview": self.preview,
            "warnings": list(self.warnings),
            "created_at": self.created_at,
        }


@dataclass
class TaskRuntimeState:
    task_id: str
    status: str = "active"
    spec_hash: str | None = None
    next_fire_at: str | None = None
    last_event_key: str | None = None
    last_side: str | None = None
    cooldown_until: str | None = None
    last_success_at: str | None = None
    last_polled_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeliveryReceipt:
    channel: str
    target: str
    outbound_message_id: str
    task_id: str
    run_id: str
    kind: str
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.channel not in {"telegram", "webhook"}:
            raise ValueError("channel 必须是 telegram 或 webhook")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskRun:
    run_id: str
    task_id: str
    trigger_event: TriggerEvent
    executor: str
    status: str
    started_at: str
    finished_at: str | None = None
    artifact_path: str | None = None
    summary_excerpt: str | None = None
    delivery_receipts: tuple[DeliveryReceipt, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "trigger_event": self.trigger_event.to_dict(),
            "executor": self.executor,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "artifact_path": self.artifact_path,
            "summary_excerpt": self.summary_excerpt,
            "delivery_receipts": [receipt.to_dict() for receipt in self.delivery_receipts],
            "error": self.error,
        }


def parse_task_definition(data: dict[str, Any]) -> TaskDefinition:
    trigger = parse_trigger(data.get("trigger") or {})
    reaction = parse_reaction(data.get("reaction") or {})
    delivery = parse_delivery(data.get("delivery") or {})
    created_at = str(data.get("created_at") or utc_now_iso())
    updated_at = str(data.get("updated_at") or created_at)
    return TaskDefinition(
        id=str(data.get("id", "")).strip(),
        name=str(data.get("name", "")).strip(),
        description=str(data.get("description", "")).strip(),
        status=str(data.get("status") or "active").strip() or "active",
        trigger=trigger,
        reaction=reaction,
        delivery=delivery,
        created_at=created_at,
        updated_at=updated_at,
    )


def parse_trigger(data: dict[str, Any]) -> TriggerSpec:
    raw_type = str(data.get("type", "")).strip()
    if raw_type == "cron":
        return CronTrigger(
            type="cron",
            cron_expr=str(data.get("cron_expr", "")).strip(),
            timezone=str(data.get("timezone", "")).strip(),
            misfire_grace_sec=int(data.get("misfire_grace_sec", 300)),
        )
    if raw_type == "price_threshold":
        return PriceThresholdTrigger(
            type="price_threshold",
            symbol=str(data.get("symbol", "")).strip().upper(),
            interval=str(data.get("interval", "")).strip(),
            condition=str(data.get("condition", "")).strip(),
            threshold=float(data.get("threshold")),
            poll_sec=int(data.get("poll_sec", 0)),
            cooldown_sec=int(data.get("cooldown_sec", 0)),
            max_data_age_sec=int(data.get("max_data_age_sec", 120)),
        )
    raise ValueError(f"未知 trigger.type: {raw_type!r}")


def parse_reaction(data: dict[str, Any]) -> ReactionSpec:
    exec_data = data.get("executor") or {}
    budget_data = data.get("budget") or {}
    executor = ReactionExecutor(
        type=str(exec_data.get("type") or "main_agent").strip() or "main_agent",
        name=_optional_str(exec_data.get("name")),
    )
    budget = ReactionBudget(
        max_rounds=int(budget_data.get("max_rounds", 8)),
        timeout_sec=int(budget_data.get("timeout_sec", 120)),
    )
    return ReactionSpec(
        executor=executor,
        prompt_template=str(data.get("prompt_template", "")).strip(),
        tool_profile=str(data.get("tool_profile") or "analysis").strip() or "analysis",
        budget=budget,
    )


def parse_delivery(data: dict[str, Any]) -> DeliverySpec:
    return DeliverySpec(
        pre_alert=parse_delivery_phase(data.get("pre_alert")),
        final_result=parse_delivery_phase(data.get("final_result"), enabled_default=True),
        on_failure=parse_delivery_phase(data.get("on_failure"), enabled_default=True),
    )


def parse_delivery_phase(
    data: Any,
    *,
    enabled_default: bool = False,
) -> DeliveryPhase:
    if data is None:
        return DeliveryPhase(enabled=enabled_default)
    if isinstance(data, bool):
        return DeliveryPhase(enabled=data)
    raw = dict(data)
    channels = tuple(parse_delivery_target(item) for item in (raw.get("channels") or []))
    return DeliveryPhase(
        enabled=bool(raw.get("enabled", enabled_default)),
        channels=channels,
    )


def parse_delivery_target(data: Any) -> DeliveryTarget:
    raw = dict(data)
    return DeliveryTarget(
        type=str(raw.get("type") or "none").strip() or "none",
        target=str(raw.get("target") or "").strip(),
    )


def trigger_to_dict(trigger: TriggerSpec) -> dict[str, Any]:
    return asdict(trigger)


def reaction_to_dict(reaction: ReactionSpec) -> dict[str, Any]:
    return {
        "executor": asdict(reaction.executor),
        "prompt_template": reaction.prompt_template,
        "tool_profile": reaction.tool_profile,
        "budget": asdict(reaction.budget),
    }


def delivery_to_dict(delivery: DeliverySpec) -> dict[str, Any]:
    return {
        "pre_alert": delivery_phase_to_dict(delivery.pre_alert),
        "final_result": delivery_phase_to_dict(delivery.final_result),
        "on_failure": delivery_phase_to_dict(delivery.on_failure),
    }


def delivery_phase_to_dict(phase: DeliveryPhase) -> dict[str, Any]:
    return {
        "enabled": phase.enabled,
        "channels": [asdict(channel) for channel in phase.channels],
    }


def parse_runtime_state(data: dict[str, Any]) -> TaskRuntimeState:
    return TaskRuntimeState(
        task_id=str(data.get("task_id", "")).strip(),
        status=str(data.get("status") or "active").strip() or "active",
        spec_hash=_optional_str(data.get("spec_hash")),
        next_fire_at=_optional_str(data.get("next_fire_at")),
        last_event_key=_optional_str(data.get("last_event_key")),
        last_side=_optional_str(data.get("last_side")),
        cooldown_until=_optional_str(data.get("cooldown_until")),
        last_success_at=_optional_str(data.get("last_success_at")),
        last_polled_at=_optional_str(data.get("last_polled_at")),
    )


def parse_task_run(data: dict[str, Any]) -> TaskRun:
    receipts = tuple(parse_delivery_receipt(item) for item in (data.get("delivery_receipts") or []))
    return TaskRun(
        run_id=str(data.get("run_id", "")).strip(),
        task_id=str(data.get("task_id", "")).strip(),
        trigger_event=TriggerEvent(**dict(data.get("trigger_event") or {})),
        executor=str(data.get("executor", "")).strip(),
        status=str(data.get("status", "")).strip(),
        started_at=str(data.get("started_at", "")).strip(),
        finished_at=_optional_str(data.get("finished_at")),
        artifact_path=_optional_str(data.get("artifact_path")),
        summary_excerpt=_optional_str(data.get("summary_excerpt")),
        delivery_receipts=receipts,
        error=_optional_str(data.get("error")),
    )


def parse_delivery_receipt(data: dict[str, Any]) -> DeliveryReceipt:
    return DeliveryReceipt(
        channel=str(data.get("channel", "")).strip(),
        target=str(data.get("target", "")).strip(),
        outbound_message_id=str(data.get("outbound_message_id", "")).strip(),
        task_id=str(data.get("task_id", "")).strip(),
        run_id=str(data.get("run_id", "")).strip(),
        kind=str(data.get("kind", "")).strip(),
        created_at=str(data.get("created_at") or utc_now_iso()),
    )


def _validate_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except Exception as exc:  # pragma: no cover - zoneinfo 错误即可
        raise ValueError(f"无效 timezone: {name}") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
