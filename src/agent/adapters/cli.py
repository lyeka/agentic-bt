"""
[INPUT]: dotenv, json, agent.kernel, agent.tools.*, agent.adapters.market.tushare
[OUTPUT]: main — 完整 CLI 入口（boot + 6 工具 + 权限 + Session 持久化 + JSONL trace）
[POS]: 用户交互通道，驱动完整 Kernel 生命周期
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from agent.kernel import Kernel, Permission, Session
from agent.adapters.market.tushare import TushareAdapter
from agent.tools import compute, market, primitives, recall


# ─────────────────────────────────────────────────────────────────────────────
# 启动流程
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI REPL — 完整 Agent 生命周期"""

    # ── 1. 加载环境变量 ──
    load_dotenv()

    model = os.getenv("MODEL", "gpt-4o-mini")
    base_url = os.getenv("BASE_URL") or None
    api_key = os.getenv("API_KEY")
    tushare_token = os.getenv("TUSHARE_TOKEN")
    workspace = Path(
        os.getenv("WORKSPACE", "~/.agent/workspace")
    ).expanduser()

    if not api_key:
        print("错误: 未设置 API_KEY，请配置 .env 文件")
        sys.exit(1)
    if not tushare_token:
        print("警告: 未设置 TUSHARE_TOKEN，market_ohlcv 将不可用")

    # ── 2. 创建 Kernel ──
    kernel = Kernel(model=model, base_url=base_url, api_key=api_key)

    # ── 3. 注册 6 工具 ──
    if tushare_token:
        adapter = TushareAdapter(token=tushare_token)
        market.register(kernel, adapter)
    compute.register(kernel)
    primitives.register(kernel, workspace)
    recall.register(kernel, workspace)

    # ── 4. 声明权限 ──
    kernel.permission("soul.md", Permission.USER_CONFIRM)
    kernel.permission("memory/**", Permission.FREE)
    kernel.permission("notebook/**", Permission.FREE)

    # ── 5. 自举 ──
    kernel.boot(workspace)

    # ── 6. JSONL trace ──
    trace_path = workspace / "trace.jsonl"
    _wire_trace(kernel, trace_path)

    # ── 7. Session 持久化 ──
    session_path = workspace / ".session.json"
    if session_path.exists():
        session = Session.load(session_path)
        print(f"已恢复会话（{len(session.history)} 条历史）")
    else:
        session = Session(session_id="cli")

    # ── 8. REPL ──
    print(f"投资助手已启动 | 模型: {model} | trace → {trace_path}")
    print("输入 quit 退出")
    try:
        _repl(kernel, session, session_path)
    finally:
        session.save(session_path)
        print(f"会话已保存 → {session_path}")


def _wire_trace(kernel: Kernel, trace_path: Path) -> None:
    """挂载 JSONL trace — 通过 wire/emit 零侵入记录所有事件"""
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


def _repl(
    kernel: Kernel,
    session: Session,
    session_path: Path,
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
        session.save(session_path)


if __name__ == "__main__":
    main()
