"""
[INPUT]: agent.kernel (Kernel, Session)
[OUTPUT]: main — CLI 交互入口
[POS]: 最简用户交互通道，驱动 Kernel.turn()
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import sys

from agent.kernel import Kernel, Session


def main(
    model: str = "gpt-4o-mini",
    base_url: str | None = None,
    api_key: str | None = None,
) -> None:
    """CLI REPL — 最简交互循环"""
    kernel = Kernel(model=model, base_url=base_url, api_key=api_key)
    session = Session(session_id=f"cli-{id(kernel)}")

    print("投资助手已启动（输入 quit 退出）")
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


if __name__ == "__main__":
    # 最简启动：python -m agent.adapters.cli
    import os
    main(
        model=os.getenv("MODEL", "gpt-4o-mini"),
        base_url=os.getenv("BASE_URL"),
        api_key=os.getenv("API_KEY"),
    )
