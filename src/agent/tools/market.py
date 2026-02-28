"""
[INPUT]: agent.kernel (Kernel), pandas
[OUTPUT]: MarketAdapter Protocol + register()
[POS]: 领域核心工具，获取 OHLCV 并注入 DataStore；adapter pattern 解耦数据源
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
    """向 Kernel 注册 market.ohlcv 工具"""

    def market_ohlcv(args: dict) -> dict:
        symbol = args["symbol"]
        period = args.get("period", "daily")
        df = adapter.fetch(symbol, period)

        # 存入 DataStore（compute 可消费）
        kernel.data.set(f"ohlcv:{symbol}", df)
        kernel.data.set("_default_ohlcv", df)

        kernel.emit(f"market.ohlcv.done:{symbol}", {"symbol": symbol})
        return {
            "symbol": symbol,
            "rows": len(df),
            "columns": list(df.columns),
            "latest": {
                "date": str(df["date"].iloc[-1]),
                "close": float(df["close"].iloc[-1]),
            },
        }

    kernel.tool(
        name="market.ohlcv",
        description="获取指定标的的 OHLCV 行情数据",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码"},
                "period": {"type": "string", "description": "周期", "default": "daily"},
            },
            "required": ["symbol"],
        },
        handler=market_ohlcv,
    )
