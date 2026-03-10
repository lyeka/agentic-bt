"""
[INPUT]: dotenv, agent.runtime, agent.adapters.tui
[OUTPUT]: main — CLI 入口（使用 runtime 统一组装 Kernel；默认启动 TUI，--simple 回退纯文本 REPL）
[POS]: 用户交互通道入口；启动逻辑（config/bundle/session）在此，展示层委托给 tui/
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.kernel import Session
from agent.runtime import AgentConfig, build_kernel_bundle
from agent.session_store import SessionStore


def _build() -> tuple[AgentConfig, Any]:
    """加载环境 + 组装 KernelBundle。"""
    load_dotenv()
    config = AgentConfig.from_env()
    raw_enable_bash = os.getenv("ENABLE_BASH")
    if raw_enable_bash is None or not raw_enable_bash.strip():
        config = replace(config, enable_bash=True)
    if not config.api_key:
        print("错误: 未设置 API_KEY，请配置 .env 文件")
        sys.exit(1)
    if not config.tushare_token:
        print("警告: 未设置 TUSHARE_TOKEN，market_ohlcv 将不可用")

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
    keep_last_user_messages: int,
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

        reply = kernel.turn(user_input, session)
        print(f"\n助手: {reply}")

        session.prune(keep_last_user_messages=max(1, int(keep_last_user_messages)))
        store.save(session)


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
        _simple_repl(kernel, session, bundle.session_store, config.session_keep_last_user_messages)
    finally:
        bundle.session_store.save(session)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI 入口 — 默认 TUI，--simple 回退纯文本。"""
    config, bundle = _build()

    if "--simple" in sys.argv:
        _run_simple(config, bundle)
        return

    from agent.adapters.tui import InvestmentApp

    session = _load_session(bundle)
    if session.history:
        pass
    else:
        session = Session(session_id="cli")

    app = InvestmentApp(bundle, session, keep_last=config.session_keep_last_user_messages)
    app.run()
    bundle.session_store.save(session)


if __name__ == "__main__":
    main()
