"""
[INPUT]: dotenv, signal, athenaclaw.runtime, athenaclaw.interfaces.tui
[OUTPUT]: main — CLI 入口（使用 runtime 统一组装 Kernel；默认启动 TUI，--simple 回退纯文本 REPL；支持 exit(42) 触发 harness 更新重启）
[POS]: 用户交互通道入口；启动逻辑（config/bundle/session）在此，展示层委托给 tui/
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import os
import signal
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from athenaclaw.kernel import Session
from athenaclaw.runtime import AgentConfig, build_kernel_bundle
from athenaclaw.runtime.session_store import SessionStore


def _build() -> tuple[AgentConfig, Any]:
    """加载环境 + 组装 KernelBundle。"""
    load_dotenv()
    config = AgentConfig.from_env()
    raw_enable_bash = os.getenv("ATHENACLAW_ENABLE_BASH")
    if raw_enable_bash is None or not raw_enable_bash.strip():
        config = replace(config, enable_bash=True)
    if not config.api_key:
        print("错误: 未设置 ATHENACLAW_API_KEY，请配置 .env 文件")
        sys.exit(1)
    if not config.tushare_token:
        print("警告: 未设置 TUSHARE_TOKEN，market_ohlcv 将不可用")

    # ── 2. 组装 Kernel（runtime） ──
    bundle = build_kernel_bundle(
        config=config,
        adapter_name="cli",
        conversation_id="cli",
        cwd=Path.cwd(),
    )
    return config, bundle


def _load_session(bundle: Any) -> Session:
    """加载或迁移 Session。"""
    workspace = bundle.workspace
    legacy_path = workspace / ".session.json"
    if legacy_path.exists() and not bundle.session_path.exists():
        legacy = Session.load(legacy_path)
        bundle.session_store.save(legacy)

    session = bundle.session_store.load()
    session.id = "cli"
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Simple REPL fallback (--simple)
# ─────────────────────────────────────────────────────────────────────────────

def _simple_repl(
    kernel: Any,
    session: Session,
    store: SessionStore,
) -> None:
    """纯文本交互循环（无 TUI 依赖）。"""
    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见。")
            break

        # 命令路由
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd in ("/new", "/reset"):
                session.history.clear()
                session.summary = None
                store.save(session)
                print("已开始新会话。")
                continue
            if cmd == "/compact":
                from athenaclaw.llm.context import compact_history, estimate_tokens

                before_tokens = estimate_tokens(session.history)
                result = compact_history(
                    provider=kernel.provider, model=kernel.model,
                    history=session.history,
                )
                session.history = result.retained
                if result.summary:
                    session.summary = (
                        f"{session.summary}\n\n{result.summary}"
                        if session.summary else result.summary
                    )
                after_tokens = estimate_tokens(session.history)
                store.save(session)
                kernel.emit("context.compacted", {
                    "trigger": "manual",
                    "messages_compressed": result.compressed_count,
                    "messages_retained": result.retained_count,
                    "tokens_before": before_tokens,
                    "tokens_after": after_tokens,
                    "summary": result.summary,
                })
                print(
                    f"已压缩上下文。\n"
                    f"消息: {result.compressed_count + result.retained_count} → {result.retained_count}\n"
                    f"Token 估算: ~{before_tokens} → ~{after_tokens}"
                )
                continue
            if cmd == "/context":
                from athenaclaw.llm.context import context_info

                info = context_info(session.history, kernel.context_window)
                print(
                    f"消息数: {info.message_count}（user: {info.user_message_count}）\n"
                    f"估算 Token: ~{info.estimated_tokens}\n"
                    f"Context Window: {info.context_window}\n"
                    f"使用率: {info.usage_pct}%"
                )
                continue
            if cmd == "/help":
                print(
                    "可用命令:\n"
                    "  /new, /reset  — 开始新会话\n"
                    "  /compact      — 压缩上下文\n"
                    "  /context      — 显示上下文统计\n"
                    "  /help         — 显示此帮助\n"
                    "  quit          — 退出"
                )
                continue

        reply = kernel.turn(user_input, session)
        print(f"\n助手: {reply}")

        # 每轮自动保存（防崩溃丢失）
        store.save(session)

        # harness 更新重启
        if kernel.data.get("_restart_requested"):
            print("[harness] 正在触发更新重启...")
            sys.exit(42)


def _run_simple(config: AgentConfig, bundle: Any) -> None:
    """--simple 模式：纯文本 REPL。"""
    session = _load_session(bundle)
    kernel = bundle.kernel

    def _cli_confirm(path: str) -> bool:
        answer = input(f"\n确认操作 {path}? [y/n] ").strip().lower()
        return answer in ("y", "yes")

    kernel.on_confirm(_cli_confirm)

    if session.history:
        print(f"已恢复会话（{len(session.history)} 条历史）")
    else:
        session = Session(session_id="cli")

    print(f"投资助手已启动 | 模型: {config.model} | trace → {bundle.trace_path}")
    print("输入 quit 退出")
    try:
        _simple_repl(kernel, session, bundle.session_store)
    finally:
        bundle.session_store.save(session)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI 入口 — 默认 TUI，--simple 回退纯文本。"""
    config, bundle = _build()

    # SIGUSR1: harness 外部触发更新
    def _on_update_signal(signum, frame):
        bundle.kernel.data.set("_restart_requested", True)

    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, _on_update_signal)

    if "--simple" in sys.argv:
        _run_simple(config, bundle)
        return

    from athenaclaw.interfaces.tui import InvestmentApp

    session = _load_session(bundle)
    if not session.history:
        session = Session(session_id="cli")

    app = InvestmentApp(bundle, session)
    app.run()
    bundle.session_store.save(session)


if __name__ == "__main__":
    main()
