"""
[INPUT]: agent.kernel (Kernel), pandas
[OUTPUT]: MarketAdapter Protocol + register()
[POS]: 领域核心工具，获取 OHLCV 并注入 DataStore；返回原始数据供 LLM 直接推理；adapter pattern 解耦数据源
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# MarketAdapter Protocol
# ─────────────────────────────────────────────────────────────────────────────

class MarketAdapter(Protocol):
    """数据源适配器接口 — 返回 canonical OHLCV DataFrame"""
    name: str

    def fetch(
        self,
        symbol: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame: ...


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, adapter: MarketAdapter) -> None:
    """向 Kernel 注册 market_ohlcv 工具"""

    def market_ohlcv(args: dict) -> dict:
        symbol = args["symbol"]
        period = args.get("period", "daily")
        start = args.get("start")
        end = args.get("end")
        df = adapter.fetch(symbol, period, start=start, end=end)

        # 存入 DataStore（compute 可消费）
        kernel.data.set(f"ohlcv:{symbol}", df)
        kernel.data.set("_default_ohlcv", df)

        kernel.emit(f"market.ohlcv.done:{symbol}", {"symbol": symbol})

        # 返回原始 OHLCV records — 数据即答案
        records = []
        for _, r in df.iterrows():
            d = r["date"]
            records.append({
                "date": str(d.date()) if hasattr(d, "date") else str(d),
                "open": round(float(r["open"]), 2),
                "high": round(float(r["high"]), 2),
                "low": round(float(r["low"]), 2),
                "close": round(float(r["close"]), 2),
                "volume": int(r["volume"]),
            })

        return {
            "symbol": symbol,
            "total_rows": len(records),
            "data": records,
        }

    kernel.tool(
        name="market_ohlcv",
        description=(
            "获取 OHLCV 行情数据（返回完整日线：date/open/high/low/close/volume），可直接分析。"
            "同时会把该标的的 DataFrame 存入 DataStore，供后续 compute 直接使用 df/open/high/low/close/volume/date。"
            "注意: 返回结果中的 data 只是当前轮可读的 JSON，不会以 data 变量自动注入 compute。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码，如 AAPL、000001.SZ"},
                "period": {"type": "string", "description": "周期", "default": "daily"},
                "start": {"type": "string", "description": "起始日期 YYYY-MM-DD，省略则默认近一年"},
                "end": {"type": "string", "description": "截止日期 YYYY-MM-DD，省略则默认今天"},
            },
            "required": ["symbol"],
        },
        handler=market_ohlcv,
    )
