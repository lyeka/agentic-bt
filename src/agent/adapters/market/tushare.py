"""
[INPUT]: tushare, pandas, datetime
[OUTPUT]: TushareAdapter — A 股日线 OHLCV 数据适配器
[POS]: MarketAdapter 实现，通过 tushare Pro API 获取真实 A 股数据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import tushare as ts


class TushareAdapter:
    """A 股日线 OHLCV — tushare Pro API"""

    name = "tushare"

    def __init__(self, token: str) -> None:
        self._api = ts.pro_api(token)

    def fetch(
        self,
        symbol: str,
        period: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        if end is None:
            end = datetime.now().strftime("%Y%m%d")
        if start is None:
            start = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        df = self._api.daily(ts_code=symbol, start_date=start, end_date=end)

        # ── 列名标准化 ──
        df = df.rename(columns={"trade_date": "date", "vol": "volume"})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]
