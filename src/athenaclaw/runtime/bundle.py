"""
[INPUT]: os, pathlib, agent.kernel, agent.tools, agent.session_store, agent.providers, agent.automation, core.subagent（market adapters 仅 lazy import）
[OUTPUT]: AgentConfig, KernelBundle, build_kernel_bundle
[POS]: 入口无关的 Kernel 组装层：统一 tools/permission/wire/trace/session_store/subagent 路径约定
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from athenaclaw.kernel import Kernel, MEMORY_MAX_CHARS, Permission
from athenaclaw.automation.store import AutomationStore
from athenaclaw.automation import tools as automation_tools
from athenaclaw.llm.providers import LLMProvider, OpenAIChatProvider
from athenaclaw.runtime.session_store import JsonSessionStore, SessionStore
from athenaclaw.tools import bash, compute, edit, market, read, web, write
from athenaclaw.subagents import SubAgentDef


@dataclass(frozen=True)
class AgentConfig:
    model: str
    base_url: str | None
    api_key: str | None
    tushare_token: str | None
    finnhub_api_key: str | None
    market_cn: str
    market_us: str
    workspace_dir: Path
    state_dir: Path
    enable_bash: bool = True
    context_window: int = 100_000
    compact_recent_turns: int = 3
    session_keep_last_user_messages: int = 20
    search_provider: str = "tavily"
    tavily_api_key: str | None = None
    image_detail: str = "low"
    subagents: list[SubAgentDef] | None = None
    automation_default_timezone: str = "Asia/Shanghai"
    automation_task_scan_sec: int = 30

    @classmethod
    def from_env(cls) -> AgentConfig:
        model = os.getenv("ATHENACLAW_MODEL", "gpt-4o-mini")
        base_url = os.getenv("ATHENACLAW_BASE_URL") or None
        api_key = os.getenv("ATHENACLAW_API_KEY")
        tushare_token = os.getenv("TUSHARE_TOKEN")
        finnhub_api_key = os.getenv("FINNHUB_API_KEY") or None
        market_cn = os.getenv("ATHENACLAW_MARKET_CN", "yfinance")
        market_us = os.getenv("ATHENACLAW_MARKET_US", "yfinance")
        workspace_dir = Path(os.getenv("ATHENACLAW_WORKSPACE", "~/.athenaclaw/workspace")).expanduser()
        state_dir = Path(os.getenv("ATHENACLAW_STATE_DIR", "~/.athenaclaw/state")).expanduser()
        enable_bash = os.getenv("ATHENACLAW_ENABLE_BASH", "1").strip().lower() not in ("0", "false", "no", "n")
        context_window = int(os.getenv("ATHENACLAW_CONTEXT_WINDOW", "100000"))
        compact_recent_turns = int(os.getenv("ATHENACLAW_COMPACT_RECENT_TURNS", "3"))
        session_keep_last = int(os.getenv("ATHENACLAW_SESSION_KEEP_LAST_USER_MESSAGES", "20"))
        search_provider = os.getenv("ATHENACLAW_SEARCH_PROVIDER", "tavily")
        tavily_api_key = os.getenv("TAVILY_API_KEY") or None
        image_detail = (os.getenv("ATHENACLAW_IMAGE_DETAIL") or "low").strip().lower() or "low"
        automation_default_timezone = os.getenv("ATHENACLAW_AUTOMATION_DEFAULT_TIMEZONE", "Asia/Shanghai")
        automation_task_scan_sec = int(os.getenv("ATHENACLAW_AUTOMATION_TASK_SCAN_SEC", "30"))
        return cls(
            model=model,
            base_url=base_url,
            api_key=api_key,
            tushare_token=tushare_token,
            finnhub_api_key=finnhub_api_key,
            market_cn=market_cn,
            market_us=market_us,
            workspace_dir=workspace_dir,
            state_dir=state_dir,
            enable_bash=enable_bash,
            context_window=context_window,
            compact_recent_turns=compact_recent_turns,
            session_keep_last_user_messages=session_keep_last,
            search_provider=search_provider,
            tavily_api_key=tavily_api_key,
            image_detail=image_detail,
            automation_default_timezone=automation_default_timezone,
            automation_task_scan_sec=automation_task_scan_sec,
        )


@dataclass(frozen=True)
class KernelBundle:
    kernel: Kernel
    workspace: Path
    state: Path
    session_store: SessionStore
    session_path: Path
    trace_path: Path


class LLMCompressor:
    """用 LLM 做记忆整合（与 CLI 逻辑一致）。"""

    def __init__(self, provider: LLMProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    def compress(self, content: str, limit: int) -> str:
        response = self.provider.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": (
                    f"你是记忆压缩器。将以下记忆精简到{limit}字以内。"
                    "保持 newest-first 倒排结构。保留最新和最重要的条目。"
                    "合并相近主题的旧条目，丢弃过时的细节。保持 markdown 格式。"
                )},
                {"role": "user", "content": content},
            ],
        )
        return str(response.assistant_message.get("content") or content[:limit])


def _wire_trace(kernel: Kernel, trace_path: Path) -> None:
    """挂载 JSONL trace — 通过 wire/emit 零侵入记录 turn/tool 等事件。"""
    trace_path.parent.mkdir(parents=True, exist_ok=True)

    def _append(event: str, data: object) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": data,
        }
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")

    kernel.wire("turn.*", _append)
    kernel.wire("tool:*", _append)
    kernel.wire("llm.*", _append)
    kernel.wire("tool.*", _append)
    kernel.wire("subagent.*", _append)
    kernel.wire("memory.compressed", _append)
    kernel.wire("context.*", _append)


def _on_memory_write(kernel: Kernel, workspace: Path, compressor: LLMCompressor) -> None:
    """memory.md 超限时自动压缩。"""
    mem = workspace / "memory.md"
    if not mem.exists():
        return
    content = mem.read_text(encoding="utf-8")
    if len(content) <= MEMORY_MAX_CHARS:
        return
    compressed = compressor.compress(content, MEMORY_MAX_CHARS)
    mem.write_text(compressed, encoding="utf-8")
    kernel.emit(
        "memory.compressed",
        {
            "original_chars": len(content),
            "compressed_chars": len(compressed),
        },
    )


def _make_adapter(name: str, config: AgentConfig) -> object:
    """按名称构造 MarketAdapter 实例（lazy import — 未使用的数据源不构成启动硬依赖）"""
    if name == "tushare":
        from athenaclaw.integrations.market.tushare import TushareAdapter
        return TushareAdapter(token=config.tushare_token)
    if name == "yfinance":
        from athenaclaw.integrations.market.yfinance import YFinanceAdapter
        return YFinanceAdapter()
    if name == "finnhub":
        from athenaclaw.integrations.market.finnhub import FinnhubAdapter
        return FinnhubAdapter(api_key=config.finnhub_api_key)
    raise ValueError(f"Unknown market adapter: {name}")


def _build_market_adapter(config: AgentConfig) -> object:
    """构造运行时使用的市场适配器（必要时自动做 A 股/非 A 股路由）。"""
    cn = _make_adapter(config.market_cn, config)
    us = _make_adapter(config.market_us, config)
    if config.market_cn == config.market_us:
        return cn

    from athenaclaw.integrations.market.composite import CompositeMarketAdapter, is_ashare

    composite = CompositeMarketAdapter()
    composite.route(is_ashare, cn)
    composite.fallback(us)
    return composite


def _build_automation_delivery_channels() -> dict[str, object]:
    from athenaclaw.automation.delivery import DiscordDeliveryChannel, TelegramDeliveryChannel, WebhookDeliveryChannel

    channels: dict[str, object] = {"webhook": WebhookDeliveryChannel()}
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    if discord_token:
        channels["discord"] = DiscordDeliveryChannel(bot_token=discord_token)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        channels["telegram"] = TelegramDeliveryChannel(bot_token=token)
    return channels


def build_kernel_bundle(
    *,
    config: AgentConfig,
    adapter_name: str,
    conversation_id: str,
    cwd: Path,
) -> KernelBundle:
    """
    统一组装 Kernel（入口无关）。

    - workspace_dir：长期人格/记忆/notebook（可跨入口共享）
    - state_dir：会话/trace 等系统状态（建议各入口隔离）
    """
    workspace = config.workspace_dir.expanduser()
    state = config.state_dir.expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)

    provider = OpenAIChatProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        image_detail=config.image_detail,
    )
    kernel = Kernel(
        model=config.model,
        provider=provider,
        context_window=config.context_window, compact_recent_turns=config.compact_recent_turns,
    )

    # ── market 工具（显式声明数据源）──
    market.register(kernel, _build_market_adapter(config))
    compute.register(kernel)
    read.register(kernel, workspace, cwd=cwd)
    write.register(kernel, workspace, cwd=cwd)
    edit.register(kernel, workspace, cwd=cwd)
    if config.enable_bash:
        bash.register(kernel, cwd=cwd)

    # web 工具（fetch 始终注册，search 需要 API key）
    search_adapter = None
    if config.search_provider == "tavily" and config.tavily_api_key:
        from athenaclaw.integrations.web.tavily import TavilyAdapter
        search_adapter = TavilyAdapter(api_key=config.tavily_api_key)
    web.register(kernel, search_adapter=search_adapter)

    automation_store = AutomationStore(workspace=workspace, state=state)

    def _manual_trigger(task_id: str) -> dict[str, object]:
        from athenaclaw.automation.executor import AutomationExecutor
        from athenaclaw.automation.models import TriggerEvent, utc_now_iso

        task = automation_store.load_task(task_id)
        if task is None:
            return {"error": f"未找到 task: {task_id}"}
        requested_at = utc_now_iso()
        event = TriggerEvent(
            event_key=f"manual:{requested_at}",
            task_id=task_id,
            trigger_type="manual",
            payload={
                "requested_at": requested_at,
                "requested_by": adapter_name,
                "conversation_id": str(conversation_id),
            },
            triggered_at=requested_at,
        )
        executor = AutomationExecutor(
            config=config,
            store=automation_store,
            delivery_channels=_build_automation_delivery_channels(),
        )
        run = executor.execute(task, event)
        runtime = automation_store.load_runtime_state(task_id)
        if run.status == "succeeded":
            runtime.last_success_at = run.finished_at
        automation_store.save_runtime_state(runtime)
        return {
            "status": "ok",
            "task_id": task_id,
            "action": "trigger",
            "run": run.to_dict(),
        }

    automation_tools.register(
        kernel,
        store=automation_store,
        adapter_name=adapter_name,
        conversation_id=conversation_id,
        default_timezone=config.automation_default_timezone,
        manual_trigger=_manual_trigger,
    )

    # permissions
    # soul.md 允许主 Agent 直接成长；自动化任务仍由 AutomationToolPolicy 单独阻止。
    kernel.permission("soul.md", Permission.FREE)
    kernel.permission("memory.md", Permission.FREE)
    kernel.permission("notebook/**", Permission.FREE)
    kernel.permission("automation/tasks/**", Permission.USER_CONFIRM)
    kernel.permission("__external__", Permission.USER_CONFIRM)

    # boot (skills + subagents + system prompt)
    kernel.boot(workspace)

    # 程序化注册的 subagents
    if config.subagents:
        for defn in config.subagents:
            kernel.subagent(defn)

    # wires: soul refresh + memory compress + trace
    compressor = LLMCompressor(kernel.provider, kernel.model)
    kernel.wire("write:soul.md", lambda e, d: kernel._assemble_system_prompt())
    kernel.wire("edit:soul.md", lambda e, d: kernel._assemble_system_prompt())
    kernel.wire("write:memory.md", lambda e, d: _on_memory_write(kernel, workspace, compressor))
    kernel.wire("edit:memory.md", lambda e, d: _on_memory_write(kernel, workspace, compressor))

    # state paths
    safe_conv = str(conversation_id).replace("/", "_")
    session_path = state / "sessions" / adapter_name / f"{safe_conv}.json"
    trace_path = state / "traces" / adapter_name / f"{safe_conv}.jsonl"

    _wire_trace(kernel, trace_path)

    store = JsonSessionStore(session_path)
    return KernelBundle(
        kernel=kernel,
        workspace=workspace,
        state=state,
        session_store=store,
        session_path=session_path,
        trace_path=trace_path,
    )
