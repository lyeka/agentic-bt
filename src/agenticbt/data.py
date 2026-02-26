"""
[INPUT]: pandas, pathlib, numpy
[OUTPUT]: load_csv, make_sample_data — 数据加载与示例数据生成（支持 regime 行情模式）
[POS]: 用户入口工具，标准化外部数据为框架所需的 OHLCV DataFrame
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# 框架要求的标准列名
_REQUIRED = {"open", "high", "low", "close", "volume"}

# 常见别名映射：用户 CSV 的列名 → 标准名
_ALIASES = {
    "Open": "open", "High": "high", "Low": "low",
    "Close": "close", "Adj Close": "close", "adj_close": "close",
    "Volume": "volume", "Vol": "volume",
    "Date": "date", "Datetime": "date", "datetime": "date",
    "timestamp": "date", "Timestamp": "date", "time": "date",
}


def load_csv(path: str | Path, date_col: str | None = None) -> pd.DataFrame:
    """
    加载 CSV 并标准化为框架所需格式。

    - 自动推断日期列
    - 列名自动映射（兼容 Yahoo Finance、AKShare、Tushare 等常见格式）
    - 按日期升序排列
    - 返回含 'date' 列（str 或 Timestamp）和 open/high/low/close/volume 的 DataFrame

    Args:
        path: CSV 文件路径
        date_col: 强制指定日期列名，None 时自动检测

    Raises:
        ValueError: 缺少必要的 OHLCV 列
    """
    df = pd.read_csv(path)

    # 列名标准化
    df = df.rename(columns=_ALIASES)

    # 自动检测日期列
    if date_col:
        df = df.rename(columns={date_col: "date"})
    if "date" not in df.columns:
        candidates = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
        if candidates:
            df = df.rename(columns={candidates[0]: "date"})

    # 验证必要列
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必要列: {missing}。现有列: {list(df.columns)}")

    # 类型转换
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 升序排列
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    return df


def make_sample_data(
    symbol: str = "AAPL",
    start: str = "2023-01-01",
    periods: int = 252,
    initial_price: float = 150.0,
    seed: int = 42,
    regime: str = "random",
) -> pd.DataFrame:
    """
    生成模拟 OHLCV 数据，用于测试和演示。

    regime 控制行情特征：
      random         — 默认随机漫步（μ=0.0003, σ=0.015）
      trending       — 强趋势低波动（μ=0.002, σ=0.01）
      mean_reverting — 零漂移高波动（μ=0, σ=0.02）
      volatile       — 极高波动（μ=0, σ=0.03）
      bull_bear      — 前半段牛市后半段熊市
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=periods, freq="B")

    close = _generate_close(regime, periods, initial_price, rng)
    returns = np.diff(np.log(close), prepend=np.log(initial_price))

    # 构造 OHLC：日内波动 ≈ ATR
    daily_range = close * rng.uniform(0.005, 0.025, size=periods)
    open_ = close * np.exp(rng.normal(0, 0.003, size=periods))
    high = np.maximum(close, open_) + daily_range * rng.uniform(0.3, 1.0, size=periods)
    low  = np.minimum(close, open_) - daily_range * rng.uniform(0.3, 1.0, size=periods)
    low  = np.maximum(low, close * 0.5)

    volume = rng.integers(5_000_000, 50_000_000, size=periods).astype(float)
    volume *= (1 + np.abs(returns) * 20)

    return pd.DataFrame({
        "date":   dates.strftime("%Y-%m-%d"),
        "open":   np.round(open_, 2),
        "high":   np.round(high, 2),
        "low":    np.round(low, 2),
        "close":  np.round(close, 2),
        "volume": np.round(volume).astype(int).astype(float),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Regime 价格生成
# ─────────────────────────────────────────────────────────────────────────────

_REGIME_PARAMS: dict[str, tuple[float, float]] = {
    "random":         (0.0003, 0.015),
    "trending":       (0.002,  0.01),
    "mean_reverting": (0.0,    0.02),
    "volatile":       (0.0,    0.03),
}


def _generate_close(
    regime: str, periods: int, initial_price: float, rng: np.random.Generator,
) -> np.ndarray:
    """根据 regime 生成收盘价序列"""
    if regime in _REGIME_PARAMS:
        mu, sigma = _REGIME_PARAMS[regime]
        returns = rng.normal(loc=mu, scale=sigma, size=periods)
        return initial_price * np.exp(np.cumsum(returns))

    if regime == "bull_bear":
        mid = periods // 2
        bull = rng.normal(loc=0.003, scale=0.01, size=mid)
        bear = rng.normal(loc=-0.002, scale=0.015, size=periods - mid)
        returns = np.concatenate([bull, bear])
        return initial_price * np.exp(np.cumsum(returns))

    raise ValueError(f"未知 regime: {regime!r}，可选: {list(_REGIME_PARAMS) + ['bull_bear']}")
