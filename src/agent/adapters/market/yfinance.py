"""
[INPUT]: yfinance, pandas, datetime
[OUTPUT]: YFinanceAdapter — 美股日线 OHLCV 数据适配器
[POS]: MarketAdapter 实现，通过 yfinance 获取 Yahoo Finance 美股数据（零 API Key）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


class YFinanceAdapter:
    """美股日线 OHLCV — Yahoo Finance (yfinance)"""

    name = "yfinance"

    def fetch(
        self,
        symbol: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        if start is None:
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        df = yf.download(symbol, start=start, end=end, interval="1d", progress=False)

        # ── MultiIndex 降维（单 ticker download 返回 MultiIndex 列） ──
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # ── DatetimeIndex → date 列 ──
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]
