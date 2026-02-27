"""
[INPUT]: agenticbt.engine, agenticbt.indicators, agenticbt.memory, agenticbt.models, agenticbt.sandbox
[OUTPUT]: ToolKit — 工具桥接层，提供 schemas/execute/call_log/indicator_queries/trade_actions；_TOOL_REMEDIATION — 错误提示常量
[POS]: Agent 和 Engine/Memory 的中间层，OpenAI function calling 格式适配；execute() 带异常防御；含 compute 沙箱计算工具
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Any

from .engine import Engine
from .indicators import IndicatorEngine
from .memory import Memory
from .models import ToolCall
from .sandbox import exec_compute


# ─────────────────────────────────────────────────────────────────────────────
# 工具错误提示（B2: remediation）
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_REMEDIATION: dict[str, str] = {
    "indicator_calc": "先调用 market_observe 确认 symbol，再调用 indicator_calc",
    "trade_execute":  "先调用 account_status 确认余额，再调用 trade_execute",
    "order_cancel":   "先调用 order_query 获取有效 order_id，再调用 order_cancel",
}


# ─────────────────────────────────────────────────────────────────────────────
# Tool Schema 定义
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "market_observe",
            "description": (
                "查询指定 symbol 的当前行情快照。"
                "仅多资产场景需要，单资产行情已在上下文中提供。"
                "返回 {datetime, symbol, open, high, low, close, volume}。"
            ),
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
            "description": (
                "计算单个技术指标的最新值。"
                "支持: RSI, SMA, EMA, ATR (用 period 参数), MACD, BBANDS (用默认参数)。"
                "返回 {value: float} 或 {upper/middle/lower: float}。"
                "如需一次计算多个指标，推荐用 compute 工具更高效。"
            ),
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
            "description": (
                "查询最新账户状态。"
                "仅需确认最新持仓变化时使用，基础账户信息已在上下文中提供。"
                "返回 {cash, equity, positions}。"
            ),
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
            "description": (
                "执行交易。观望时不要调用此工具。"
                "action: buy/sell/close。close 时无需 quantity。"
                "支持 bracket: 同时传 stop_loss + take_profit 自动创建 OCO 保护单。"
                "返回 {status, order_id} 或 {status: rejected, reason}。"
                "风控拒绝返回 {status:rejected, reason, max_allowed_qty}，用 max_allowed_qty 重试即可。"
            ),
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
            "description": "在当日日志中追加一条记录。交易后用此记录决策理由。返回 {status: ok}。",
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
            "description": "创建或更新主题笔记（如持仓理由、策略参数）。返回 {status: ok}。",
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
            "description": "按关键词检索历史记忆。返回 {results: [str]}。",
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
            "description": "取消指定的挂单。先用 order_query 获取有效 order_id。返回 {status: cancelled}。",
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
            "description": "查询当前所有待执行的挂单。返回 {pending_orders: [{order_id, symbol, side, quantity, ...}]}。",
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
            "name": "market_history",
            "description": (
                "获取最近 N 根 K 线的完整 OHLCV 历史。"
                "仅当需要比 compute 中 df 更细粒度的分析时使用。"
                "返回 {history: [{date, open, high, low, close, volume}]}。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bars": {"type": "integer", "description": "要获取的 K 线数量"},
                    "symbol": {"type": "string", "description": "股票代码（默认主资产）"},
                },
                "required": ["bars"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute",
            "description": (
                "Python 计算沙箱。每次调用独立命名空间。"
                "预加载: df(OHLCV), pd, np, ta(=pandas_ta, 已注入禁止import), math, cash, equity, positions。"
                "Helpers: latest(s)→标量, prev(s,n), crossover(fast,slow)→bool, "
                "bbands(close,length,std)→(upper,mid,lower), macd(close)→(macd,signal,hist)。"
                "⚠ ta.macd()/ta.bbands() 返回 DataFrame 不可解包，必须用 helper。"
                "单表达式自动返回；多行赋值给 result。"
                "示例: result={'rsi':latest(ta.rsi(df.close,14)), 'bb':bbands(df.close,20,2)}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "指定主数据源的股票代码（默认主资产）",
                    },
                },
                "required": ["code"],
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
        # B2: 工具级异常防御 — 工具崩溃返回错误 dict，不中断 ReAct loop
        try:
            result = self._dispatch(tool_name, args)
        except Exception as e:
            result = {
                "error": f"{type(e).__name__}: {e}",
                "tool": tool_name,
                "remediation": _TOOL_REMEDIATION.get(tool_name, "检查参数后重试"),
            }
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
            "market_history": self._market_history,
            "compute": self._compute,
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
        # B4: 兼容单资产和多资产引擎，通过 _data_by_symbol 查找
        symbol = args.get("symbol", self._engine._symbol)
        bar_index = self._engine._bar_index
        df = self._engine._data_by_symbol.get(symbol)
        if df is None:
            return {
                "error": f"symbol {symbol!r} 不存在",
                "remediation": "检查 symbol 名称是否正确",
            }
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
                # B1: 用 is not None 而非 or，防止 0.0 被 falsy 误判
                sl = stop_loss if stop_loss is not None else 0.0
                tp = take_profit if take_profit is not None else float("inf")
                result = self._engine.submit_bracket(symbol, action, quantity, sl, tp)
                # O2: Bracket 覆盖提示，帮助 Agent 理解参数生效情况
                if order_type != "market" or price is not None:
                    result = dict(result)
                    result["warning"] = "Bracket 模式：order_type/price 参数已忽略"
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

    def _market_history(self, args: dict) -> dict:
        bars = args["bars"]
        symbol = args.get("symbol")
        return {"history": self._engine.market_history(bars, symbol)}

    def _compute(self, args: dict) -> dict:
        code = args["code"]
        symbol = args.get("symbol", self._engine._symbol)
        bar_index = self._engine._bar_index

        # 主数据源：截断到 bar_index 防前瞻
        primary_df = self._engine._data_by_symbol.get(symbol)
        if primary_df is None:
            return {"error": f"symbol {symbol!r} 不存在"}
        df = primary_df.iloc[: bar_index + 1]

        # 多资产数据：全部截断
        extra_dfs: dict = {}
        for sym, sym_df in self._engine._data_by_symbol.items():
            extra_dfs[sym] = sym_df.iloc[: bar_index + 1]

        # 账户快照
        snap = self._engine.account_snapshot()
        account = {
            "cash": snap.cash,
            "equity": snap.equity,
            "positions": {
                s: {"size": p.size, "avg_price": p.avg_price}
                for s, p in snap.positions.items()
            },
        }

        result = exec_compute(code, df, account, extra_dfs=extra_dfs)
        result["_meta"] = {"df_rows": len(df), "columns": list(df.columns)}
        return result
