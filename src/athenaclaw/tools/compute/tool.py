"""
[INPUT]: athenaclaw.kernel (Kernel), athenaclaw.tools.compute.sandbox, athenaclaw.tools.market.schema
[OUTPUT]: register()
[POS]: 领域增强工具，沙箱化 Python 计算；自动从 DataStore 注入 OHLCV
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from athenaclaw.tools.market.schema import (
    build_market_query,
    default_selector_key,
    normalize_interval,
    normalize_mode,
    normalize_symbol,
)
from athenaclaw.tools.compute.sandbox import exec_compute


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object) -> None:
    """向 Kernel 注册 compute 工具"""

    def compute_handler(args: dict) -> dict:
        code = args["code"]
        symbol = args.get("symbol")
        interval = args.get("interval")
        mode = args.get("mode")
        start = args.get("start")
        end = args.get("end")

        # 从 DataStore 查找 OHLCV
        keys: list[str] = []
        if start is not None or end is not None:
            if not symbol:
                raise ValueError("compute 的 start/end 需要配合 symbol 使用")
            query = build_market_query(
                symbol=symbol,
                interval=interval,
                mode=mode,
                start=start,
                end=end,
            )
            keys.extend([query.exact_key, query.selector_key, query.symbol_key])
        elif symbol and (interval is not None or mode is not None):
            query = build_market_query(symbol=symbol, interval=interval, mode=mode)
            keys.extend([query.selector_key, query.symbol_key])
        elif symbol:
            keys.append(f"ohlcv:{normalize_symbol(symbol)}")
        elif interval is not None or mode is not None:
            keys.append(default_selector_key(normalize_interval(interval), normalize_mode(mode)))

        if not symbol:
            keys.append("_default_ohlcv")

        df = None
        for key in keys:
            df = kernel.data.get(key)
            if df is not None:
                break
        if df is None:
            if symbol or interval or mode or start or end:
                return {"error": "未找到对应 OHLCV，请先用相同的 symbol/interval/mode/start/end 调用 market_ohlcv"}
            return {"error": "无 OHLCV 数据，请先调用 market_ohlcv"}

        account = kernel.data.get("account") or {
            "cash": 0, "equity": 0, "positions": {},
        }
        return exec_compute(code, df, account)

    kernel.tool(
        name="compute",
        description=(
            "Python 计算沙箱（通用分析终端，不是指标菜单）。"
            "每次调用独立命名空间，上一轮 compute 中定义的变量不会保留到下一轮。"
            "预加载: df(OHLCV DataFrame), open/high/low/close/volume/date(均为 pandas Series), "
            "account/cash/equity/positions, pd, np, ta(=pandas_ta), math。"
            "Helpers: latest, prev, crossover, crossunder, above, below, "
            "bbands(close,length,std)→(upper,mid,lower), macd(close)→(macd,signal,hist), tail, nz。"
            "返回: 单表达式自动返回；多行代码最后一行若为表达式也会返回；也可显式设置 result。"
            "重要语义: market_ohlcv 只是在后台注入 df，不会把其返回 JSON 中的 data 变量带进来；"
            "如果已经抓过多个 symbol/interval/mode/start/end 组合，compute 必须复用同一组 selector 才能取到正确的 df。"
            "一旦显式提供 symbol，compute 只会在该 symbol 的数据范围内查找，不会回退到别的 symbol。"
            "若需价格序列请直接使用 df/close/date。date 在分钟数据中会包含时分秒。Series 使用 pandas 语义且默认 RangeIndex，"
            "取最后一个值请用 latest(close) 或 close.iloc[-1]，不要写 close[-1]/date[-1]。"
            "若后续公式依赖 max_price/min_price/latest_close 等中间量，必须在同一次 compute 中重新计算。"
            "bbands()/macd() helper 返回的是最新标量三元组，不要再对返回值写 [-1]。"
            "注意: 不要写 import(已预注入)；不要 def 函数(用内联表达式)；不要文件 I/O；"
            "代码保持 5-20 行 REPL 风格。用 bbands()/macd() helper 而非 ta.bbands()/ta.macd()。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
                "symbol": {"type": "string", "description": "标的代码；多数据集并存时建议显式提供"},
                "interval": {
                    "type": "string",
                    "enum": ["1d", "1m", "5m", "15m", "30m", "60m"],
                    "description": "与 market_ohlcv 相同的 bar 粒度 selector",
                },
                "mode": {
                    "type": "string",
                    "enum": ["history", "latest"],
                    "description": "与 market_ohlcv 相同的模式 selector",
                },
                "start": {"type": "string", "description": "可选，精确匹配某次 history 查询的起始时间"},
                "end": {"type": "string", "description": "可选，精确匹配某次 history 查询的截止时间"},
            },
            "required": ["code"],
        },
        handler=compute_handler,
    )
