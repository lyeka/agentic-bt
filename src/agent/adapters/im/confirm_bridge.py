"""
[INPUT]: asyncio, typing
[OUTPUT]: make_sync_confirm
[POS]: 将 async IM confirm 交互桥接为 Kernel 需要的同步 bool 回调（跨线程）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
from typing import Callable

from agent.adapters.im.backend import IMBackend


def make_sync_confirm(
    *,
    backend: IMBackend,
    loop: asyncio.AbstractEventLoop,
    conversation_id: str,
    timeout_sec: int,
) -> Callable[[str], bool]:
    """
    Kernel.on_confirm() 需要同步函数；IM backend.ask_confirm() 是 async。
    此函数用于在 worker 线程中阻塞等待 IM 用户确认。
    """

    def _confirm(path: str) -> bool:
        coro = backend.ask_confirm(conversation_id, f"确认操作 {path}?", timeout_sec=timeout_sec)
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return bool(fut.result(timeout=timeout_sec + 5))
        except Exception:
            # 超时或 backend 异常都默认拒绝
            return False

    return _confirm

