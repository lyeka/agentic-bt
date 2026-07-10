"""
[INPUT]: time
[OUTPUT]: call_with_retry
[POS]: llm/ 的重试策略层：指数退避 + temperature 不兼容自动降级，供 Kernel 与 subagents/runner 共用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import time
from typing import Any, Callable


def call_with_retry(
    *,
    provider: Any,
    model: str,
    messages: list,
    tools: list | None,
    temperature: float | None = None,
    timeout: float | None = None,
    attempts: int = 3,
    base_delay: float = 1.0,
    emit_fn: Callable[[str, dict], None] | None = None,
    emit_prefix: str = "llm",
    emit_context: dict | None = None,
    reraise_on_exhaustion: bool = True,
) -> Any | None:
    """带指数退避的 LLM 调用。

    - temperature 不兼容（错误信息含 "temperature"）时自动降级为 None 重试，不计入退避延迟。
    - 其余异常按 base_delay * 2**attempt 退避，耗尽后按 reraise_on_exhaustion 决定 raise 还是返回 None。
    - timeout 为 None 时不向 provider 传递该参数，兼容不支持 timeout kwarg 的 provider。
    """
    ctx = dict(emit_context or {})
    for attempt in range(attempts):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            return provider.complete(**kwargs)
        except Exception as exc:
            if "temperature" in str(exc).lower() and temperature is not None:
                if emit_fn:
                    emit_fn(f"{emit_prefix}.call.retry", {
                        **ctx,
                        "attempt": attempt + 1,
                        "reason": "temperature_incompatible",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    })
                temperature = None
                continue

            if emit_fn:
                emit_fn(f"{emit_prefix}.call.error", {
                    **ctx,
                    "attempt": attempt + 1,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })

            if attempt == attempts - 1:
                if reraise_on_exhaustion:
                    raise
                return None

            time.sleep(base_delay * (2 ** attempt))
    return None
