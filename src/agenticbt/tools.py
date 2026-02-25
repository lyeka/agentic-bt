"""
[INPUT]: agenticbt.engine, agenticbt.indicators, agenticbt.memory, agenticbt.models
[OUTPUT]: ToolKit — 工具桥接层，提供 schemas/execute/call_log/indicator_queries/trade_actions
[POS]: Agent 和 Engine/Memory 的中间层，OpenAI function calling 格式适配
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Any

from .engine import Engine
from .indicators import IndicatorEngine
from .memory import Memory
from .models import ToolCall


# ─────────────────────────────────────────────────────────────────────────────
# Tool Schema 定义
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "market_observe",
            "description": "获取当前 bar 的市场行情",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "indicator_calc",
            "description": "计算技术指标",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "指标名称，如 RSI、SMA、EMA"},
                    "period": {"type": "integer", "description": "计算周期", "default": 14},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "account_status",
            "description": "查询当前账户持仓和资金状态",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trade_execute",
            "description": "执行交易操作",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["buy", "sell", "close", "hold"],
                        "description": "交易动作",
                    },
                    "symbol": {"type": "string", "description": "股票代码"},
                    "quantity": {"type": "integer", "description": "数量（close 时可省略）"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_log",
            "description": "在当日日志中追加一条记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "日志内容"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_note",
            "description": "创建或更新主题笔记",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "笔记键"},
                    "content": {"type": "string", "description": "笔记内容"},
                },
                "required": ["key", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "按关键词检索记忆",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"},
                },
                "required": ["query"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# ToolKit
# ─────────────────────────────────────────────────────────────────────────────

class ToolKit:
    """
    每次 Agent.decide() 创建一个新实例，追踪本次决策的所有工具调用。

    执行入口：execute(tool_name, args) → dict
    记录：call_log / indicator_queries / trade_actions
    """

    def __init__(self, engine: Engine, memory: Memory) -> None:
        self._engine = engine
        self._memory = memory
        self._indicators = IndicatorEngine()

        # 调用追踪
        self.call_log: list[ToolCall] = []
        self.indicator_queries: dict[str, Any] = {}
        self.trade_actions: list[dict[str, Any]] = []

    @property
    def schemas(self) -> list[dict]:
        return _SCHEMAS

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = self._dispatch(tool_name, args)
        self.call_log.append(ToolCall(tool=tool_name, input=args, output=result))
        return result

    # ── 分发逻辑 ──────────────────────────────────────────────────────────────

    def _dispatch(self, name: str, args: dict) -> dict:
        handlers = {
            "market_observe": self._market_observe,
            "indicator_calc": self._indicator_calc,
            "account_status": self._account_status,
            "trade_execute": self._trade_execute,
            "memory_log": self._memory_log,
            "memory_note": self._memory_note,
            "memory_recall": self._memory_recall,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"未知工具: {name}"}
        return handler(args)

    def _market_observe(self, _args: dict) -> dict:
        snap = self._engine.market_snapshot()
        return {
            "datetime": snap.datetime.isoformat(),
            "symbol": snap.symbol,
            "open": snap.open,
            "high": snap.high,
            "low": snap.low,
            "close": snap.close,
            "volume": snap.volume,
        }

    def _indicator_calc(self, args: dict) -> dict:
        name = args["name"]
        period = args.get("period", 14)
        bar_index = self._engine._bar_index
        df = self._engine._data.rename(columns={"date": "date"})  # noqa: simplify
        # 确保列名统一为小写 open/high/low/close/volume
        result = self._indicators.calc(name, df, bar_index, period=period)
        self.indicator_queries[name] = result
        return result

    def _account_status(self, _args: dict) -> dict:
        snap = self._engine.account_snapshot()
        return {
            "cash": snap.cash,
            "equity": snap.equity,
            "positions": {
                sym: {"size": p.size, "avg_price": p.avg_price}
                for sym, p in snap.positions.items()
            },
        }

    def _trade_execute(self, args: dict) -> dict:
        action = args.get("action", "hold")
        symbol = args.get("symbol", self._engine._symbol)
        quantity = args.get("quantity")

        if action == "hold":
            result: dict = {"status": "hold"}
        elif action == "buy":
            result = self._engine.submit_buy(symbol, quantity or 0)
        elif action == "sell":
            result = self._engine.submit_sell(symbol, quantity or 0)
        elif action == "close":
            result = self._engine.submit_close(symbol)
        else:
            result = {"status": "rejected", "reason": f"未知 action: {action}"}

        if action != "hold":
            self.trade_actions.append({"action": action, "symbol": symbol,
                                       "quantity": quantity, "result": result})
        return result

    def _memory_log(self, args: dict) -> dict:
        self._memory.log(args["content"])
        return {"status": "ok"}

    def _memory_note(self, args: dict) -> dict:
        self._memory.note(args["key"], args["content"])
        return {"status": "ok"}

    def _memory_recall(self, args: dict) -> dict:
        results = self._memory.recall(args["query"])
        return {"results": results}
