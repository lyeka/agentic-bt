"""
[INPUT]: agent.kernel (Kernel), core.sandbox (exec_compute)
[OUTPUT]: register()
[POS]: 领域增强工具，沙箱化 Python 计算；自动从 DataStore 注入 OHLCV
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from core.sandbox import exec_compute


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object) -> None:
    """向 Kernel 注册 compute 工具"""

    def compute_handler(args: dict) -> dict:
        code = args["code"]
        symbol = args.get("symbol")

        # 从 DataStore 查找 OHLCV
        df = None
        if symbol:
            df = kernel.data.get(f"ohlcv:{symbol}")
        if df is None:
            df = kernel.data.get("_default_ohlcv")
        if df is None:
            return {"error": "无 OHLCV 数据，请先调用 market_ohlcv"}

        account = kernel.data.get("account") or {
            "cash": 0, "equity": 0, "positions": {},
        }
        return exec_compute(code, df, account)

    kernel.tool(
        name="compute",
        description=(
            "Python 沙箱计算。预加载: df(OHLCV), close/open/high/low/volume/date, "
            "pd, np, ta(=pandas_ta), math。"
            "Helpers: latest, crossover, bbands, macd, tail, nz。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
                "symbol": {"type": "string", "description": "标的代码（默认最近获取的）"},
            },
            "required": ["code"],
        },
        handler=compute_handler,
    )
