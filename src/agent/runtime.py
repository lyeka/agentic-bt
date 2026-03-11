"""
[INPUT]: os, pathlib, agent.kernel, agent.tools, agent.adapters.market.{tushare,yfinance,finnhub,composite}, agent.adapters.web.tavily, agent.session_store, core.subagent
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

from agent.kernel import Kernel, MEMORY_MAX_CHARS, Permission
from agent.session_store import JsonSessionStore, SessionStore
from agent.adapters.market.tushare import TushareAdapter
from agent.adapters.market.yfinance import YFinanceAdapter
from agent.adapters.market.composite import CompositeMarketAdapter, is_ashare
from agent.tools import bash, compute, edit, market, read, web, write
from core.subagent import SubAgentDef


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
    search_provider: str = "tavily"
    tavily_api_key: str | None = None
    subagents: list[SubAgentDef] | None = None

    @classmethod
    def from_env(cls) -> AgentConfig:
        model = os.getenv("MODEL", "gpt-4o-mini")
        base_url = os.getenv("BASE_URL") or None
        api_key = os.getenv("API_KEY")
        tushare_token = os.getenv("TUSHARE_TOKEN")
        finnhub_api_key = os.getenv("FINNHUB_API_KEY") or None
        market_cn = os.getenv("MARKET_CN", "yfinance")
        market_us = os.getenv("MARKET_US", "yfinance")
        workspace_dir = Path(os.getenv("WORKSPACE", "~/.agent/workspace")).expanduser()
        state_dir = Path(os.getenv("STATE_DIR", "~/.agent/state")).expanduser()
        enable_bash = os.getenv("ENABLE_BASH", "1").strip().lower() not in ("0", "false", "no", "n")
        context_window = int(os.getenv("CONTEXT_WINDOW", "100000"))
        compact_recent_turns = int(os.getenv("COMPACT_RECENT_TURNS", "3"))
        search_provider = os.getenv("SEARCH_PROVIDER", "tavily")
        tavily_api_key = os.getenv("TAVILY_API_KEY") or None
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
            search_provider=search_provider,
            tavily_api_key=tavily_api_key,
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

    def __init__(self, client: object, model: str) -> None:
        self.client = client
        self.model = model

    def compress(self, content: str, limit: int) -> str:
        response = self.client.chat.completions.create(
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
        return response.choices[0].message.content or content[:limit]


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
    """按名称构造 MarketAdapter 实例"""
    if name == "tushare":
        return TushareAdapter(token=config.tushare_token)
    if name == "yfinance":
        return YFinanceAdapter()
    if name == "finnhub":
        from agent.adapters.market.finnhub import FinnhubAdapter
        return FinnhubAdapter(api_key=config.finnhub_api_key)
    raise ValueError(f"Unknown market adapter: {name}")


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

    kernel = Kernel(
        model=config.model, base_url=config.base_url, api_key=config.api_key,
        context_window=config.context_window, compact_recent_turns=config.compact_recent_turns,
    )

    # ── market 工具（显式声明数据源）──
    cn = _make_adapter(config.market_cn, config)
    us = _make_adapter(config.market_us, config)
    if config.market_cn == config.market_us:
        market.register(kernel, cn)
    else:
        composite = CompositeMarketAdapter()
        composite.route(is_ashare, cn)
        composite.fallback(us)
        market.register(kernel, composite)
    compute.register(kernel)
    read.register(kernel, workspace, cwd=cwd)
    write.register(kernel, workspace, cwd=cwd)
    edit.register(kernel, workspace, cwd=cwd)
    if config.enable_bash:
        bash.register(kernel, cwd=cwd)

    # web 工具（fetch 始终注册，search 需要 API key）
    search_adapter = None
    if config.search_provider == "tavily" and config.tavily_api_key:
        from agent.adapters.web.tavily import TavilyAdapter
        search_adapter = TavilyAdapter(api_key=config.tavily_api_key)
    web.register(kernel, search_adapter=search_adapter)

    # permissions
    kernel.permission("soul.md", Permission.USER_CONFIRM)
    kernel.permission("memory.md", Permission.FREE)
    kernel.permission("notebook/**", Permission.FREE)
    kernel.permission("__external__", Permission.USER_CONFIRM)

    # boot (skills + subagents + system prompt)
    kernel.boot(workspace)

    # 程序化注册的 subagents
    if config.subagents:
        for defn in config.subagents:
            kernel.subagent(defn)

    # wires: soul refresh + memory compress + trace
    compressor = LLMCompressor(kernel.client, kernel.model)
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
