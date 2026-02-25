"""
[INPUT]: pandas, pandas_ta
[OUTPUT]: IndicatorEngine — 技术指标计算引擎（防前瞻包装）
[POS]: Engine 子组件，被 tools.py 的 indicator_calc 工具调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import math

import pandas as pd
import pandas_ta as ta


# ─────────────────────────────────────────────────────────────────────────────
# 可用指标注册表
# ─────────────────────────────────────────────────────────────────────────────

AVAILABLE_INDICATORS = ["RSI", "SMA", "EMA", "ATR", "MACD", "BBANDS"]


class IndicatorEngine:
    """
    防前瞻技术指标计算。

    调用方式：calc(name, df, bar_index, **params)
    - df: 完整 OHLCV DataFrame（含所有历史数据）
    - bar_index: 当前 bar 序号，只使用 0..bar_index 的数据
    - 返回：{"value": float | None, ...} 或 {"macd": ..., "signal": ..., "histogram": ...}
    """

    def calc(self, name: str, df: pd.DataFrame, bar_index: int, **params) -> dict:
        """计算指标，严格限制为 bar_index 及之前的数据"""
        subset = df.iloc[: bar_index + 1].copy()
        name_upper = name.upper()

        if name_upper == "RSI":
            return self._rsi(subset, **params)
        if name_upper == "SMA":
            return self._sma(subset, **params)
        if name_upper == "EMA":
            return self._ema(subset, **params)
        if name_upper == "ATR":
            return self._atr(subset, **params)
        if name_upper == "MACD":
            return self._macd(subset, **params)
        if name_upper == "BBANDS":
            return self._bbands(subset, **params)
        raise ValueError(f"未知指标: {name}")

    def list_indicators(self) -> list[str]:
        return list(AVAILABLE_INDICATORS)

    # ── 各指标实现 ────────────────────────────────────────────────────────────

    def _rsi(self, df: pd.DataFrame, period: int = 14) -> dict:
        result = ta.rsi(df["close"], length=period)
        val = None if result is None else result.iloc[-1]
        return {"value": None if _is_nan(val) else float(val)}

    def _sma(self, df: pd.DataFrame, period: int = 20) -> dict:
        result = ta.sma(df["close"], length=period)
        val = None if result is None else result.iloc[-1]
        return {"value": None if _is_nan(val) else float(val)}

    def _ema(self, df: pd.DataFrame, period: int = 20) -> dict:
        result = ta.ema(df["close"], length=period)
        val = None if result is None else result.iloc[-1]
        return {"value": None if _is_nan(val) else float(val)}

    def _atr(self, df: pd.DataFrame, period: int = 14) -> dict:
        result = ta.atr(df["high"], df["low"], df["close"], length=period)
        val = None if result is None else result.iloc[-1]
        return {"value": None if _is_nan(val) else float(val)}

    def _macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        if result is None or result.empty:
            return {"macd": None, "signal": None, "histogram": None}
        row = result.iloc[-1]
        cols = result.columns.tolist()
        macd_col = next((c for c in cols if "MACD_" in c and "signal" not in c.lower() and "hist" not in c.lower()), cols[0])
        sig_col = next((c for c in cols if "signal" in c.lower() or "MACDs" in c), cols[1])
        hist_col = next((c for c in cols if "hist" in c.lower() or "MACDh" in c), cols[2])
        return {
            "macd": None if _is_nan(row[macd_col]) else float(row[macd_col]),
            "signal": None if _is_nan(row[sig_col]) else float(row[sig_col]),
            "histogram": None if _is_nan(row[hist_col]) else float(row[hist_col]),
        }

    def _bbands(self, df: pd.DataFrame, period: int = 20) -> dict:
        result = ta.bbands(df["close"], length=period)
        if result is None or result.empty:
            return {"upper": None, "mid": None, "lower": None}
        row = result.iloc[-1]
        cols = result.columns.tolist()
        return {
            "upper": None if _is_nan(row[cols[0]]) else float(row[cols[0]]),
            "mid": None if _is_nan(row[cols[1]]) else float(row[cols[1]]),
            "lower": None if _is_nan(row[cols[2]]) else float(row[cols[2]]),
        }


def _is_nan(val) -> bool:
    if val is None:
        return True
    try:
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return True
