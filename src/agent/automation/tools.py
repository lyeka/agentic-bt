"""
[INPUT]: uuid, pathlib, agent.kernel, agent.messages, agent.automation.*
[OUTPUT]: register()
[POS]: automation 对外工具层：task_plan / task_apply / task_context / task_control
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.automation.cron import preview as cron_preview
from agent.automation.models import (
    CONTROL_ACTIONS,
    TASK_CONTEXT_VIEWS,
    TASK_STATUSES,
    CronTrigger,
    DeliveryPhase,
    DeliverySpec,
    DeliveryTarget,
    ReactionBudget,
    ReactionExecutor,
    ReactionSpec,
    TaskDefinition,
    TaskDraft,
    TaskRuntimeState,
    parse_task_definition,
    utc_now_iso,
)
from agent.automation.store import AutomationStore


def register(
    kernel: object,
    *,
    store: AutomationStore,
    adapter_name: str,
    conversation_id: str,
    default_timezone: str,
    manual_trigger: Any | None = None,
) -> None:
    def task_plan_handler(args: dict) -> dict:
        raw_task = dict(args.get("task") or {})
        _apply_defaults(
            raw_task,
            adapter_name=adapter_name,
            conversation_id=conversation_id,
            default_timezone=default_timezone,
        )
        now = utc_now_iso()
        raw_task.setdefault("created_at", now)
        raw_task["updated_at"] = now
        raw_task.setdefault("status", "active")
        raw_task.setdefault("id", _task_id(raw_task.get("id"), raw_task.get("name")))
        try:
            task = parse_task_definition(raw_task)
        except ValueError as exc:
            return _task_plan_error(
                raw_task,
                str(exc),
                default_timezone=default_timezone,
                adapter_name=adapter_name,
                conversation_id=conversation_id,
            )
        warnings = _plan_warnings(task)
        if _needs_clarification(task):
            return {
                "status": "needs_clarification",
                "task": task.to_dict(),
                "preview": _preview(task),
                "warnings": warnings,
            }
        draft = TaskDraft(
            draft_id=f"draft-{uuid.uuid4().hex[:12]}",
            task=task,
            preview=_preview(task),
            warnings=tuple(warnings),
        )
        store.save_draft(draft)
        return draft.to_dict()

    def task_apply_handler(args: dict) -> dict:
        draft_id = str(args.get("draft_id", "")).strip()
        if not draft_id:
            return {"error": "缺少参数: draft_id"}
        draft = store.load_draft(draft_id)
        if draft is None:
            return {
                "error": f"未找到 draft: {draft_id}",
                "hints": [
                    "只能传入 task_plan 刚返回的原始 draft_id。",
                    "如果 task_plan 返回的是 status='needs_clarification'，应先向用户澄清，不能直接 task_apply。",
                    "不要从任务名、task_id 或 preview 文本猜测 draft_id。",
                ],
            }
        store.save_task(draft.task)
        runtime = store.load_runtime_state(draft.task.id)
        runtime.status = draft.task.status
        runtime.spec_hash = store.task_spec_hash(draft.task)
        store.save_runtime_state(runtime)
        store.delete_draft(draft_id)
        return {
            "status": "ok",
            "task_id": draft.task.id,
            "task": draft.task.to_dict(),
        }

    def task_context_handler(args: dict) -> dict:
        view = str(args.get("view") or "overview").strip() or "overview"
        if view not in TASK_CONTEXT_VIEWS:
            return {"error": f"view 必须是 {sorted(TASK_CONTEXT_VIEWS)}"}
        if view == "all_tasks":
            items = []
            for task in store.list_tasks():
                state = store.load_runtime_state(task.id)
                latest = store.latest_run(task.id)
                items.append({
                    "task_id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "status": task.status,
                    "trigger": task.to_dict()["trigger"],
                    "next_fire_at": state.next_fire_at,
                    "last_success_at": state.last_success_at,
                    "latest_run_status": latest.status if latest else None,
                })
            return {"tasks": items}
        selector = _select_context(kernel, args)
        if selector.get("run_id"):
            task_id = selector.get("task_id")
            run_id = selector["run_id"]
            if not task_id:
                receipt_task = _task_id_from_run(store, run_id)
                task_id = receipt_task
            if not task_id:
                return {"error": "缺少 task_id，且无法从 run_id 反查"}
            run = store.load_run(task_id, run_id)
            if run is None:
                return {"error": f"未找到 run: {run_id}"}
            if view in {"run_detail", "latest_run"}:
                return {"run": run.to_dict()}
            if view == "artifact_excerpt":
                excerpt = _read_artifact_excerpt(run.artifact_path, lines=int(args.get("lines", 40) or 40))
                return {"run_id": run_id, "artifact_excerpt": excerpt}
        task_id = selector.get("task_id")
        if not task_id:
            return {"error": "缺少 task_id 或 run_id"}
        if view == "overview":
            return store.task_overview(task_id)
        if view == "status":
            return {"state": store.load_runtime_state(task_id).to_dict()}
        if view == "latest_run":
            latest = store.latest_run(task_id)
            return {"run": latest.to_dict() if latest else None}
        if view == "recent_runs":
            limit = max(1, int(args.get("limit", 5) or 5))
            return {"runs": [run.to_dict() for run in store.list_runs(task_id, limit=limit)]}
        return {"task": store.load_task(task_id).to_dict() if store.load_task(task_id) else None}

    def task_control_handler(args: dict) -> dict:
        task_id = str(args.get("task_id", "")).strip()
        action = str(args.get("action", "")).strip()
        if action not in CONTROL_ACTIONS:
            return {"error": f"action 必须是 {sorted(CONTROL_ACTIONS)}"}
        task = store.load_task(task_id)
        if task is None:
            return {"error": f"未找到 task: {task_id}"}
        if action == "trigger":
            if task.status == "archived":
                return {"error": f"archived task 不能触发: {task_id}"}
            if manual_trigger is None:
                return {"error": "当前入口不支持手动触发 task"}
            return manual_trigger(task_id)
        new_status = {
            "pause": "paused",
            "resume": "active",
            "archive": "archived",
        }[action]
        updated = TaskDefinition(
            id=task.id,
            name=task.name,
            description=task.description,
            status=new_status,
            trigger=task.trigger,
            reaction=task.reaction,
            delivery=task.delivery,
            created_at=task.created_at,
            updated_at=utc_now_iso(),
        )
        store.save_task(updated)
        runtime = store.load_runtime_state(task_id)
        runtime.status = new_status
        runtime.spec_hash = store.task_spec_hash(updated)
        store.save_runtime_state(runtime)
        return {"status": "ok", "task_id": task_id, "new_status": new_status}

    kernel.tool(
        name="task_plan",
        description=(
            "创建或修改自动化任务草案。仅做校验/预览，不直接生效。"
            "返回结果分三种："
            "1) 有 draft_id：表示可继续 task_apply；"
            "2) status='needs_clarification'：表示必须先向用户澄清，不能 task_apply；"
            "3) error：表示参数不合法，应修正后重新 task_plan。"
            "task 必须使用 canonical 结构：顶层字段是 name/description/trigger/reaction/delivery。"
            "不要使用 schedule、steps、output、pipeline、action。"
            "cron 任务必须写 trigger.type='cron'、trigger.cron_expr、trigger.timezone。"
            "价格监控任务必须写 trigger.type='price_threshold'、symbol、interval、condition、threshold、poll_sec。"
            "reaction 只描述一次执行：executor + prompt_template；不要把 reaction 写成 tools/steps 工作流。"
            "如果想让触发后去获取行情、计算、研究，请把目标写进 reaction.prompt_template，让 agent 在运行时自己调用现有工具。"
            "如果当前是在 Telegram 会话里创建任务，且要推送到当前聊天，不要手动填写 telegram 的 target；系统会自动绑定当前 chat_id。"
            "如果返回 needs_clarification 或 error，不要改去调用 task_apply、task_context、bash、market_ohlcv 来补救创建流程。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "object",
                    "description": (
                        "完整 task 定义对象。"
                        "示例 cron："
                        "{"
                        "\"name\":\"每日复盘\","
                        "\"description\":\"每天 21:53 推送复盘\","
                        "\"trigger\":{\"type\":\"cron\",\"cron_expr\":\"53 21 * * 0-4\",\"timezone\":\"Asia/Shanghai\"},"
                        "\"reaction\":{\"executor\":{\"type\":\"main_agent\"},\"prompt_template\":\"请复盘我今天的持仓表现。\"}"
                        "}"
                    ),
                    "properties": {
                        "id": {"type": "string", "description": "可选；不填则按 name 自动生成"},
                        "name": {"type": "string", "description": "任务名"},
                        "description": {"type": "string", "description": "任务描述"},
                        "status": {
                            "type": "string",
                            "enum": sorted(TASK_STATUSES),
                            "description": "可选；默认 active",
                        },
                        "trigger": {
                            "type": "object",
                            "description": (
                                "触发器定义。"
                                "cron 写法：type='cron' + cron_expr + timezone。"
                                "价格监控写法：type='price_threshold' + symbol + interval + condition + threshold + poll_sec。"
                                "不要使用 schedule。"
                            ),
                            "properties": {
                                "type": {"type": "string", "enum": ["cron", "price_threshold"]},
                                "cron_expr": {"type": "string", "description": "5 段 cron 表达式，例如 53 21 * * 0-4"},
                                "timezone": {"type": "string", "description": "例如 Asia/Shanghai"},
                                "misfire_grace_sec": {"type": "integer"},
                                "symbol": {"type": "string"},
                                "interval": {"type": "string", "enum": ["1m", "5m", "15m", "30m", "60m"]},
                                "condition": {"type": "string", "enum": ["cross_above", "cross_below"]},
                                "threshold": {"type": "number"},
                                "poll_sec": {"type": "integer"},
                                "cooldown_sec": {"type": "integer"},
                                "max_data_age_sec": {"type": "integer"},
                            },
                        },
                        "reaction": {
                            "type": "object",
                            "description": (
                                "触发后的执行定义。"
                                "只写 executor 和 prompt_template，不要写 steps/tools。"
                            ),
                            "properties": {
                                "executor": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["main_agent", "skill", "subagent"]},
                                        "name": {"type": "string", "description": "skill/subagent 名称；main_agent 不需要"},
                                    },
                                },
                                "prompt_template": {
                                    "type": "string",
                                    "description": "告诉 reaction 要做什么；如需行情/计算/研究，让 agent 运行时自己决定调用工具",
                                },
                                "tool_profile": {"type": "string", "enum": ["analysis", "report_writer"]},
                                "budget": {
                                    "type": "object",
                                    "properties": {
                                        "max_rounds": {"type": "integer"},
                                        "timeout_sec": {"type": "integer"},
                                    },
                                },
                            },
                        },
                        "delivery": {
                            "type": "object",
                            "description": (
                                "投递配置。只描述 pre_alert/final_result/on_failure 和 channels。"
                                "在 Telegram 会话里，如要推送到当前聊天，只需把 channel.type 写成 telegram，"
                                "或直接省略 target；系统会自动补当前 chat_id。"
                            ),
                        },
                    },
                    "required": ["name", "trigger", "reaction"],
                },
            },
            "required": ["task"],
        },
        handler=task_plan_handler,
    )
    kernel.tool(
        name="task_apply",
        description=(
            "应用 task_plan 生成的 draft。先 task_plan，再把返回的原始 draft_id 传给 task_apply。"
            "只有 task_plan 返回了 draft_id 时才能调用。"
            "不要从任务名、task_id、preview 文本中猜测 draft_id。"
            "automation task 会直接生效，不再请求用户确认。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "要应用的 draft id"},
            },
            "required": ["draft_id"],
        },
        handler=task_apply_handler,
    )
    kernel.tool(
        name="task_context",
        description="查询自动化 task/run 的上下文。view='all_tasks' 可列出当前全部任务。若当前消息是 reply 某次自动推送，可省略 selector 直接查询绑定的 run/task。不要把它当成创建任务工具。",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "run_id": {"type": "string"},
                "view": {
                    "type": "string",
                    "enum": sorted(TASK_CONTEXT_VIEWS),
                    "default": "overview",
                },
                "limit": {"type": "integer"},
                "lines": {"type": "integer"},
            },
            "required": [],
        },
        handler=task_context_handler,
    )
    kernel.tool(
        name="task_control",
        description="控制 task 运行状态。支持 pause/resume/archive/trigger。trigger 表示按当前定义立刻临时执行一次。不要用它修改任务定义；修改定义应重新走 task_plan + task_apply。automation task 控制会直接执行，不再请求用户确认。",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "action": {"type": "string", "enum": sorted(CONTROL_ACTIONS)},
            },
            "required": ["task_id", "action"],
        },
        handler=task_control_handler,
    )


def _task_id(raw_id: Any, raw_name: Any) -> str:
    text = str(raw_id or raw_name or "").strip().lower()
    if not text:
        return f"task-{uuid.uuid4().hex[:8]}"
    out = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text)
    out = out.strip("-_")
    return out or f"task-{uuid.uuid4().hex[:8]}"


def _default_channels(adapter_name: str, conversation_id: str) -> list[dict[str, Any]]:
    if adapter_name == "telegram":
        return [{"type": "telegram", "target": conversation_id}]
    return [{"type": "none", "target": ""}]


def _copy_channels(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in channels]


def _default_delivery(adapter_name: str, conversation_id: str) -> dict[str, Any]:
    channels = _default_channels(adapter_name, conversation_id)
    return {
        "pre_alert": {"enabled": False, "channels": _copy_channels(channels)},
        "final_result": {"enabled": True, "channels": _copy_channels(channels)},
        "on_failure": {"enabled": True, "channels": _copy_channels(channels)},
    }


def _normalize_delivery_channel(
    raw_channel: Any,
    *,
    adapter_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    if isinstance(raw_channel, str):
        channel_type = raw_channel.strip() or "none"
        target = conversation_id if channel_type == "telegram" and adapter_name == "telegram" else ""
        if channel_type == "none":
            target = ""
        return {"type": channel_type, "target": target}
    if not isinstance(raw_channel, dict):
        return dict(raw_channel)
    channel = dict(raw_channel)
    channel_type = str(channel.get("type") or "none").strip() or "none"
    target = str(channel.get("target") or "").strip()
    if channel_type == "telegram" and not target and adapter_name == "telegram":
        target = conversation_id
    if channel_type == "none":
        target = ""
    return {"type": channel_type, "target": target}


def _normalize_delivery_phase(
    raw_phase: Any,
    *,
    default_phase: dict[str, Any],
    adapter_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    if raw_phase is None:
        return {
            "enabled": bool(default_phase.get("enabled", False)),
            "channels": _copy_channels(list(default_phase.get("channels") or [])),
        }
    if isinstance(raw_phase, bool):
        return {
            "enabled": raw_phase,
            "channels": _copy_channels(list(default_phase.get("channels") or [])) if raw_phase else [],
        }
    if not isinstance(raw_phase, dict):
        return dict(raw_phase)
    phase = dict(raw_phase)
    enabled = bool(phase.get("enabled", default_phase.get("enabled", False)))
    raw_channels = phase.get("channels")
    if raw_channels is None:
        channels = _copy_channels(list(default_phase.get("channels") or [])) if enabled else []
    else:
        channels = [
            _normalize_delivery_channel(
                item,
                adapter_name=adapter_name,
                conversation_id=conversation_id,
            )
            for item in list(raw_channels)
        ]
        if enabled and not channels:
            channels = _copy_channels(list(default_phase.get("channels") or []))
    return {"enabled": enabled, "channels": channels}


def _normalize_delivery(
    raw_delivery: Any,
    *,
    adapter_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    default = _default_delivery(adapter_name, conversation_id)
    if raw_delivery in (None, {}):
        return default
    if not isinstance(raw_delivery, dict):
        return dict(raw_delivery)
    delivery = dict(raw_delivery)
    return {
        "pre_alert": _normalize_delivery_phase(
            delivery.get("pre_alert"),
            default_phase=default["pre_alert"],
            adapter_name=adapter_name,
            conversation_id=conversation_id,
        ),
        "final_result": _normalize_delivery_phase(
            delivery.get("final_result"),
            default_phase=default["final_result"],
            adapter_name=adapter_name,
            conversation_id=conversation_id,
        ),
        "on_failure": _normalize_delivery_phase(
            delivery.get("on_failure"),
            default_phase=default["on_failure"],
            adapter_name=adapter_name,
            conversation_id=conversation_id,
        ),
    }


def _apply_defaults(
    raw_task: dict[str, Any],
    *,
    adapter_name: str,
    conversation_id: str,
    default_timezone: str,
) -> None:
    trigger = raw_task.get("trigger")
    if isinstance(trigger, dict) and str(trigger.get("type", "")).strip() == "cron":
        trigger.setdefault("timezone", default_timezone)
    raw_task["delivery"] = _normalize_delivery(
        raw_task.get("delivery"),
        adapter_name=adapter_name,
        conversation_id=conversation_id,
    )


def _plan_warnings(task: TaskDefinition) -> list[str]:
    warnings: list[str] = []
    if isinstance(task.trigger, CronTrigger):
        if task.trigger.timezone:
            warnings.append(f"cron 将按时区 {task.trigger.timezone} 解释。")
        text = task.reaction.prompt_template
        if any(token in text for token in ("收盘", "开盘", "交易日")):
            warnings.append("v1 不支持市场日历语义；请确认 cron 时间是明确 wall-clock 时间。")
    return warnings


def _task_plan_error(
    raw_task: dict[str, Any],
    error: str,
    *,
    default_timezone: str,
    adapter_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    hints: list[str] = []
    if "schedule" in raw_task and "trigger" not in raw_task:
        hints.append("检测到 schedule；请改为 trigger。")
        schedule = raw_task.get("schedule")
        if isinstance(schedule, dict) and "cron" in schedule:
            hints.append("检测到 schedule.cron；请改为 trigger.cron_expr。")
    trigger = raw_task.get("trigger")
    if isinstance(trigger, dict) and "cron" in trigger and "cron_expr" not in trigger:
        hints.append("检测到 trigger.cron；请改为 trigger.cron_expr。")
    if "steps" in raw_task:
        hints.append("当前任务模型不支持 steps；请把目标写进 reaction.prompt_template。")
    if "output" in raw_task:
        hints.append("检测到 output；请改为 delivery。")
    if not hints:
        hints.extend([
            "顶层字段应为 name/description/trigger/reaction/delivery。",
            "cron 任务必须提供 trigger.type='cron' 和 trigger.cron_expr。",
            "不要使用 schedule、steps、output。",
        ])

    example = {
        "name": str(raw_task.get("name") or "自动化任务"),
        "description": str(raw_task.get("description") or ""),
        "trigger": {
            "type": "cron",
            "cron_expr": "53 21 * * 0-4",
            "timezone": default_timezone,
        },
        "reaction": {
            "executor": {"type": "main_agent"},
            "prompt_template": "请完成这次自动化任务，并把关键结论整理成适合推送给我的结果。",
            "tool_profile": "analysis",
            "budget": {"max_rounds": 8, "timeout_sec": 120},
        },
        "delivery": _default_delivery(adapter_name, conversation_id),
    }
    return {
        "error": error,
        "hints": hints,
        "expected_shape": example,
    }


def _needs_clarification(task: TaskDefinition) -> bool:
    if not isinstance(task.trigger, CronTrigger):
        return False
    text = task.reaction.prompt_template
    return any(token in text for token in ("收盘", "开盘", "交易日"))


def _preview(task: TaskDefinition) -> str:
    if isinstance(task.trigger, CronTrigger):
        next_times = cron_preview(
            task.trigger.cron_expr,
            timezone=task.trigger.timezone,
            now=datetime.now(timezone.utc),
            count=3,
        )
        return (
            f"任务 {task.name} ({task.id})\n"
            f"- type: cron\n"
            f"- cron: {task.trigger.cron_expr}\n"
            f"- timezone: {task.trigger.timezone}\n"
            f"- next: {', '.join(next_times)}\n"
            f"- executor: {task.reaction.executor.type}{':' + task.reaction.executor.name if task.reaction.executor.name else ''}"
        )
    return (
        f"任务 {task.name} ({task.id})\n"
        f"- type: price_threshold\n"
        f"- symbol: {task.trigger.symbol}\n"
        f"- condition: {task.trigger.condition}\n"
        f"- threshold: {task.trigger.threshold}\n"
        f"- poll_sec: {task.trigger.poll_sec}\n"
        f"- executor: {task.reaction.executor.type}{':' + task.reaction.executor.name if task.reaction.executor.name else ''}"
    )


def _select_context(kernel: object, args: dict[str, Any]) -> dict[str, str]:
    task_id = str(args.get("task_id", "")).strip()
    run_id = str(args.get("run_id", "")).strip()
    ctx = kernel.execution_context()
    if not run_id:
        ref = ctx.first_ref("automation_run")
        if ref is not None:
            run_id = ref.value
    if not task_id:
        ref = ctx.first_ref("automation_task")
        if ref is not None:
            task_id = ref.value
    return {"task_id": task_id, "run_id": run_id}


def _task_id_from_run(store: AutomationStore, run_id: str) -> str | None:
    for task in store.list_tasks():
        if store.load_run(task.id, run_id) is not None:
            return task.id
    return None


def _read_artifact_excerpt(path_str: str | None, *, lines: int) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(content[: max(1, lines)])
