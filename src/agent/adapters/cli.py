"""
[INPUT]: dotenv, agent.runtime
[OUTPUT]: main — CLI 入口（使用 runtime 统一组装 Kernel；Session 落盘到 state_dir）
[POS]: 用户交互通道（CLI），尽量薄；业务组装逻辑下沉到 runtime
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


# ─────────────────────────────────────────────────────────────────────────────
# 启动流程
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI REPL — 完整 Agent 生命周期"""

    # ── 1. 加载环境变量 ──
    load_dotenv()

    config = AgentConfig.from_env()
    # 兼容：CLI 历史行为默认启用 bash；IM 入口仍默认关闭。
    raw_enable_bash = os.getenv("ENABLE_BASH")
    if raw_enable_bash is None or not raw_enable_bash.strip():
        config = replace(config, enable_bash=True)
    if not config.api_key:
        print("错误: 未设置 API_KEY，请配置 .env 文件")
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
    kernel = bundle.kernel
    workspace = bundle.workspace

    # ── 3. 确认回调 ──
    def _cli_confirm(path: str) -> bool:
        answer = input(f"\n确认操作 {path}? [y/n] ").strip().lower()
        return answer in ("y", "yes")

    kernel.on_confirm(_cli_confirm)

    # ── 4. Session 持久化（state_dir） + 兼容迁移 ──
    legacy_path = workspace / ".session.json"
    if legacy_path.exists() and not bundle.session_path.exists():
        legacy = Session.load(legacy_path)
        bundle.session_store.save(legacy)

    session = bundle.session_store.load()
    session.id = "cli"
    if session.history:
        print(f"已恢复会话（{len(session.history)} 条历史）")
    else:
        session = Session(session_id="cli")

    # ── 9. REPL ──
    print(f"投资助手已启动 | 模型: {config.model} | trace → {bundle.trace_path}")
    print("输入 quit 退出")
    try:
        _repl(kernel, session, bundle.session_store, config.session_keep_last_user_messages)
    finally:
        bundle.session_store.save(session)
        # 保存路径由 store 决定；CLI 不需要额外打印绝对路径


def _repl(
    kernel: Any,
    session: Session,
    store: SessionStore,
    keep_last_user_messages: int,
) -> None:
    """交互循环"""
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

        # 每轮自动保存（防崩溃丢失）
        session.prune(keep_last_user_messages=max(1, int(keep_last_user_messages)))
        store.save(session)


if __name__ == "__main__":
    main()
