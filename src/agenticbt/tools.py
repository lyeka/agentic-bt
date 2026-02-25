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
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "指定查询的股票代码（默认主资产）",
                    },
                },
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
                    "order_type": {
                        "type": "string",
                        "enum": ["market", "limit", "stop"],
                        "default": "market",
                        "description": "订单类型：market/limit/stop",
                    },
                    "price": {
                        "type": "number",
                        "description": "限价（limit）或止损触发价（stop）",
                    },
                    "valid_bars": {
                        "type": "integer",
                        "description": "订单有效 bar 数，省略则永久有效",
                    },
                    "stop_loss": {
                        "type": "number",
                        "description": "止损价（自动创建 Bracket，与 take_profit 配合）",
                    },
                    "take_profit": {
                        "type": "number",
                        "description": "止盈价（自动创建 Bracket，与 stop_loss 配合）",
                    },
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
    {
        "type": "function",
        "function": {
            "name": "order_cancel",
            "description": "取消指定的挂单",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "要取消的订单 ID"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "order_query",
            "description": "查询当前所有待执行的挂单列表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
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
            "order_cancel": self._order_cancel,
            "order_query": self._order_query,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"未知工具: {name}"}
        return handler(args)

    def _market_observe(self, args: dict) -> dict:
        symbol = args.get("symbol")
        snap = self._engine.market_snapshot(symbol)
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
        quantity = args.get("quantity", 0)
        order_type = args.get("order_type", "market")
        price = args.get("price")
        valid_bars = args.get("valid_bars")
        stop_loss = args.get("stop_loss")
        take_profit = args.get("take_profit")

        if action == "hold":
            result: dict = {"status": "hold"}
        elif action in ("buy", "sell"):
            if stop_loss is not None or take_profit is not None:
                # Bracket 模式：忽略 order_type/price，直接用 stop_loss/take_profit
                sl = stop_loss or 0.0
                tp = take_profit or float("inf")
                result = self._engine.submit_bracket(symbol, action, quantity, sl, tp)
            else:
                result = self._engine.submit_order(
                    symbol, action, quantity,
                    order_type=order_type,
                    limit_price=price if order_type == "limit" else None,
                    stop_price=price if order_type == "stop" else None,
                    valid_bars=valid_bars,
                )
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

    def _order_cancel(self, args: dict) -> dict:
        return self._engine.cancel_order(args["order_id"])

    def _order_query(self, _args: dict) -> dict:
        return {"pending_orders": self._engine.pending_orders()}
