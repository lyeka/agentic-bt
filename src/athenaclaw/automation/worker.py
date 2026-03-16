"""
[INPUT]: asyncio, datetime, dotenv, agent.runtime, agent.automation.*, market schema
[OUTPUT]: AutomationWorker, main
[POS]: 自动化 worker：周期扫描 task 定义，驱动 cron 与价格阈值任务
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from athenaclaw.tools.market.schema import build_market_query
from athenaclaw.automation.cron import SimpleCron
from athenaclaw.automation.delivery import DiscordDeliveryChannel, TelegramDeliveryChannel, WebhookDeliveryChannel
from athenaclaw.automation.executor import AutomationExecutor
from athenaclaw.automation.models import PriceThresholdTrigger, TaskDefinition, TaskRuntimeState, TriggerEvent
from athenaclaw.automation.store import AutomationStore
from athenaclaw.runtime import AgentConfig, _build_market_adapter


class AutomationWorker:
    def __init__(
        self,
        *,
        config: AgentConfig,
        store: AutomationStore,
        scan_sec: int = 30,
        market_adapter: object | None = None,
        executor: AutomationExecutor | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._scan_sec = max(5, int(scan_sec))
        self._market_adapter = market_adapter or _build_market_adapter(config)
        self._executor = executor or AutomationExecutor(
            config=config,
            store=store,
            delivery_channels=_build_delivery_channels(),
        )

    async def run_forever(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self._scan_sec)

    async def tick(self, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        for task in self._store.list_tasks():
            state = self._store.load_runtime_state(task.id)
            state.status = task.status
            spec_hash = self._store.task_spec_hash(task)
            if state.spec_hash != spec_hash:
                state.spec_hash = spec_hash
                state.next_fire_at = None
                state.last_event_key = None
            if task.status != "active":
                self._store.save_runtime_state(state)
                continue
            try:
                if task.trigger.type == "cron":
                    self._handle_cron(task, state, current)
                else:
                    self._handle_price_threshold(task, state, current)
            except Exception:
                pass
            finally:
                self._store.save_runtime_state(state)

    def _handle_cron(self, task: TaskDefinition, state: TaskRuntimeState, now: datetime) -> None:
        trigger = task.trigger
        cron = SimpleCron.parse(trigger.cron_expr)
        if state.next_fire_at is None:
            state.next_fire_at = cron.next_after(now, timezone=trigger.timezone).astimezone(timezone.utc).isoformat()
            return

        next_fire = datetime.fromisoformat(state.next_fire_at)
        if now < next_fire:
            return

        grace = timedelta(seconds=trigger.misfire_grace_sec)
        if grace.total_seconds() >= 0 and now - next_fire > grace:
            state.next_fire_at = cron.next_after(now, timezone=trigger.timezone).astimezone(timezone.utc).isoformat()
            return

        event_key = f"cron:{next_fire.isoformat()}"
        if state.last_event_key == event_key:
            state.next_fire_at = cron.next_after(next_fire, timezone=trigger.timezone).astimezone(timezone.utc).isoformat()
            return

        event = TriggerEvent(
            event_key=event_key,
            task_id=task.id,
            trigger_type="cron",
            payload={"scheduled_at": next_fire.isoformat()},
            triggered_at=now.isoformat(),
        )
        run = self._executor.execute(task, event)
        state.last_event_key = event_key
        if run.status == "succeeded":
            state.last_success_at = run.finished_at
        state.next_fire_at = cron.next_after(next_fire, timezone=trigger.timezone).astimezone(timezone.utc).isoformat()

    def _handle_price_threshold(self, task: TaskDefinition, state: TaskRuntimeState, now: datetime) -> None:
        trigger = task.trigger
        assert isinstance(trigger, PriceThresholdTrigger)
        if state.last_polled_at:
            last_polled = datetime.fromisoformat(state.last_polled_at)
            if now < last_polled + timedelta(seconds=trigger.poll_sec):
                return
        state.last_polled_at = now.isoformat()

        result = self._market_adapter.fetch(build_market_query(
            symbol=trigger.symbol,
            interval=trigger.interval,
            mode="latest",
        ))
        if result.df.empty:
            return

        current_price = float(result.df.iloc[-1]["close"])
        as_of = str(result.as_of or "")
        if self._is_stale(as_of, now, trigger.max_data_age_sec):
            return

        current_side = "above" if current_price >= trigger.threshold else "below"
        previous_side = state.last_side
        state.last_side = current_side

        if state.cooldown_until:
            until = datetime.fromisoformat(state.cooldown_until)
            if now < until:
                return

        should_fire = (
            trigger.condition == "cross_above"
            and previous_side == "below"
            and current_side == "above"
        ) or (
            trigger.condition == "cross_below"
            and previous_side == "above"
            and current_side == "below"
        )

        if not should_fire:
            return

        event_key = f"{trigger.condition}:{as_of or now.isoformat()}"
        if state.last_event_key == event_key:
            return

        event = TriggerEvent(
            event_key=event_key,
            task_id=task.id,
            trigger_type="price_threshold",
            payload={
                "symbol": trigger.symbol,
                "interval": trigger.interval,
                "condition": trigger.condition,
                "threshold": trigger.threshold,
                "current_price": current_price,
                "as_of": as_of,
                "source": result.source,
            },
            triggered_at=now.isoformat(),
        )
        run = self._executor.execute(task, event)
        state.last_event_key = event_key
        if run.status == "succeeded":
            state.last_success_at = run.finished_at
        if trigger.cooldown_sec > 0:
            state.cooldown_until = (now + timedelta(seconds=trigger.cooldown_sec)).isoformat()

    def _is_stale(self, as_of: str, now: datetime, max_age_sec: int) -> bool:
        if not as_of:
            return False
        try:
            ts = _parse_dt(as_of, now.tzinfo or timezone.utc)
        except ValueError:
            return False
        return now - ts > timedelta(seconds=max_age_sec)


def _parse_dt(text: str, fallback_tz) -> datetime:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty time")
    if "T" in raw:
        dt = datetime.fromisoformat(raw)
    elif len(raw) == 10:
        dt = datetime.strptime(raw, "%Y-%m-%d")
    else:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=fallback_tz)
    return dt


def _build_delivery_channels() -> dict[str, object]:
    channels: dict[str, object] = {"webhook": WebhookDeliveryChannel()}
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    if discord_token:
        channels["discord"] = DiscordDeliveryChannel(bot_token=discord_token)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        channels["telegram"] = TelegramDeliveryChannel(bot_token=token)
    return channels


@contextmanager
def _worker_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"automation worker 已在运行: {path}")
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        if path.exists():
            path.unlink()


def main() -> None:
    load_dotenv()
    config = AgentConfig.from_env()
    if not config.api_key:
        raise SystemExit("错误: 未设置 ATHENACLAW_API_KEY（用于 automation reaction）")
    if not config.tushare_token:
        config = replace(config, market_cn="yfinance")

    store = AutomationStore(
        workspace=config.workspace_dir.expanduser(),
        state=config.state_dir.expanduser(),
    )
    worker = AutomationWorker(config=config, store=store)
    lock = config.state_dir.expanduser() / "automation" / "worker.lock"
    with _worker_lock(lock):
        asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
