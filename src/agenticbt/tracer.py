"""
[INPUT]: core.tracer (TraceWriter), agenticbt.models (Decision, ToolCall)
[OUTPUT]: TraceWriter (re-export from core) + decision_to_dict — Decision 完整序列化
[POS]: 可观测性层，被 Agent 和 Runner 消费；TraceWriter 已提取至 core/
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.tracer import TraceWriter  # noqa: F401 — re-export

if TYPE_CHECKING:
    from .models import Decision


# ─────────────────────────────────────────────────────────────────────────────
# 序列化工具
# ─────────────────────────────────────────────────────────────────────────────

def decision_to_dict(decision: Decision) -> dict[str, Any]:
    """Decision → JSON-safe dict，完整保留所有 15 个字段。"""
    return {
        "datetime": (
            decision.datetime.isoformat()
            if isinstance(decision.datetime, datetime)
            else str(decision.datetime)
        ),
        "bar_index": decision.bar_index,
        "action": decision.action,
        "symbol": decision.symbol,
        "quantity": decision.quantity,
        "reasoning": decision.reasoning,
        "market_snapshot": decision.market_snapshot,
        "account_snapshot": decision.account_snapshot,
        "indicators_used": decision.indicators_used,
        "tool_calls": [
            {"tool": tc.tool, "input": tc.input, "output": tc.output}
            for tc in decision.tool_calls
        ],
        "order_result": decision.order_result,
        "model": decision.model,
        "tokens_used": decision.tokens_used,
        "latency_ms": decision.latency_ms,
    }
