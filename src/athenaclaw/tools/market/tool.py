"""
[INPUT]: athenaclaw.kernel (Kernel), pandas, athenaclaw.tools.market.schema
[OUTPUT]: MarketAdapter Protocol + register()
[POS]: 领域核心工具，获取 OHLCV 并注入 DataStore；返回原始数据供 LLM 直接推理；adapter pattern 解耦数据源
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from athenaclaw.tools.market.schema import (
    MarketFetchResult,
    MarketQuery,
    build_market_query,
    format_record_timestamp,
    meta_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# MarketAdapter Protocol
# ─────────────────────────────────────────────────────────────────────────────

class MarketAdapter(Protocol):
    """数据源适配器接口 — 返回 canonical OHLCV DataFrame + meta"""

    name: str

    def fetch(self, query: MarketQuery) -> MarketFetchResult: ...


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, adapter: MarketAdapter) -> None:
    """向 Kernel 注册 market_ohlcv 工具"""

    def market_ohlcv(args: dict) -> dict:
        query = build_market_query(
            symbol=args["symbol"],
            interval=args.get("interval"),
            mode=args.get("mode"),
            start=args.get("start"),
            end=args.get("end"),
        )
        result = adapter.fetch(query)
        df = result.df

        # 存入 DataStore（compute 可消费）
        for key in (
            query.exact_key,
            query.selector_key,
            query.symbol_key,
            query.default_selector_key,
            "_default_ohlcv",
        ):
            kernel.data.set(key, df)
            kernel.data.set(meta_key(key), result.meta())

        kernel.emit(
            f"market.ohlcv.done:{query.normalized_symbol}",
            {
                "symbol": query.normalized_symbol,
                "interval": query.interval,
                "mode": query.mode,
                "source": result.source,
            },
        )

        records = []
        for _, row in df.iterrows():
            volume = row["volume"]
            if pd.isna(volume):
                volume = 0
            records.append({
                "date": format_record_timestamp(row["date"], query.interval),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(float(volume)),
            })

        return {
            "symbol": query.symbol,
            "normalized_symbol": query.normalized_symbol,
            "source": result.source,
            "interval": query.interval,
            "mode": query.mode,
            "timezone": result.timezone,
            "as_of": result.as_of,
            "effective_start": result.effective_start,
            "effective_end": result.effective_end,
            "warning": result.warning,
            "total_rows": len(records),
            "data": records,
        }

    kernel.tool(
        name="market_ohlcv",
        description=(
            "获取 OHLCV 行情数据。interval 表示 bar 粒度，只能是 1d/1m/5m/15m/30m/60m；"
            "mode 表示取历史(history)还是最新可用一根 bar(latest)。latest 不是交易所实时流，而是数据源当前最新可用的一根分钟 bar；"
            "请结合返回中的 source/as_of/warning 判断新鲜度。默认: 1d/history 返回最近一年；"
            "分钟 history 返回当日盘中，休市则最近一个交易日；latest 需要显式指定分钟 interval。"
            "start/end 仅支持 history；1d 用 YYYY-MM-DD，分钟用 YYYY-MM-DD HH:MM:SS。"
            "工具会把 DataFrame 存入 DataStore，供后续 compute 使用。"
            "如果你加载了多个 symbol/interval/mode/start/end 组合，compute 必须复用同一组 selector 才能取到正确数据。"
            "注意: 返回结果中的 data 只是当前轮可读的 JSON，不会以 data 变量自动注入 compute。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码，如 AAPL、600519.SH、000001.SZ"},
                "interval": {
                    "type": "string",
                    "enum": ["1d", "1m", "5m", "15m", "30m", "60m"],
                    "description": "bar 粒度；latest 必须显式指定分钟 interval",
                    "default": "1d",
                },
                "mode": {
                    "type": "string",
                    "enum": ["history", "latest"],
                    "description": "history=历史 OHLCV；latest=最新可用一根分钟 bar",
                    "default": "history",
                },
                "start": {
                    "type": "string",
                    "description": "history 起始时间；1d 用 YYYY-MM-DD，分钟用 YYYY-MM-DD HH:MM:SS",
                },
                "end": {
                    "type": "string",
                    "description": "history 截止时间；1d 用 YYYY-MM-DD，分钟用 YYYY-MM-DD HH:MM:SS",
                },
            },
            "required": ["symbol"],
        },
        handler=market_ohlcv,
    )
