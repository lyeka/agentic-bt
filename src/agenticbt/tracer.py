"""
[INPUT]: json, datetime, pathlib, agenticbt.models (Decision, ToolCall)
[OUTPUT]: TraceWriter — 本地 JSONL 追踪写入器；decision_to_dict — Decision 完整序列化
[POS]: 可观测性层，被 Agent 和 Runner 消费；不依赖 Engine/Memory/Tools
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Decision


# ─────────────────────────────────────────────────────────────────────────────
# TraceWriter
# ─────────────────────────────────────────────────────────────────────────────

class TraceWriter:
    """
    本地 JSONL 追踪写入器 — 对齐 OTel GenAI Semantic Conventions。

    每次 write() 追加一行 JSON 到文件，自动填充 ts 和 bar_index。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._bar_index = 0

    def set_bar(self, bar_index: int) -> None:
        self._bar_index = bar_index

    def write(self, event: dict[str, Any]) -> None:
        event["ts"] = datetime.now().isoformat()
        event.setdefault("bar_index", self._bar_index)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


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
