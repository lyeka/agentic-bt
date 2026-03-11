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
            "Python 计算沙箱（通用分析终端，不是指标菜单）。"
            "预加载: df(OHLCV DataFrame), open/high/low/close/volume/date(均为 pandas Series), "
            "account/cash/equity/positions, pd, np, ta(=pandas_ta), math。"
            "Helpers: latest, prev, crossover, crossunder, above, below, "
            "bbands(close,length,std)→(upper,mid,lower), macd(close)→(macd,signal,hist), tail, nz。"
            "返回: 单表达式自动返回；多行代码最后一行若为表达式也会返回；也可显式设置 result。"
            "重要语义: market_ohlcv 只是在后台注入 df，不会把其返回 JSON 中的 data 变量带进来；"
            "若需价格序列请直接使用 df/close/date。Series 使用 pandas 语义且默认 RangeIndex，"
            "取最后一个值请用 latest(close) 或 close.iloc[-1]，不要写 close[-1]/date[-1]。"
            "bbands()/macd() helper 返回的是最新标量三元组，不要再对返回值写 [-1]。"
            "注意: 不要写 import(已预注入)；不要 def 函数(用内联表达式)；不要文件 I/O；"
            "代码保持 5-20 行 REPL 风格。用 bbands()/macd() helper 而非 ta.bbands()/ta.macd()。"
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
