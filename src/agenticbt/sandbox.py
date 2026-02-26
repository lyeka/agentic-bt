"""
[INPUT]: pandas, numpy, pandas_ta, math, signal
[OUTPUT]: exec_compute — 沙箱化 Python 执行器；HELPERS — Trading Coreutils
[POS]: compute 工具的执行层，被 tools.py 的 _compute 调用；与 Engine 无耦合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import math
import signal as _signal
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta


# ─────────────────────────────────────────────────────────────────────────────
# 白名单 globals — 禁用所有内置函数
# ─────────────────────────────────────────────────────────────────────────────

_SAFE_GLOBALS: dict[str, Any] = {
    "pd": pd,
    "np": np,
    "ta": ta,
    "math": math,
    "__builtins__": {
        "len": len,
        "range": range,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sum": sum,
        "sorted": sorted,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "True": True,
        "False": False,
        "None": None,
        "isinstance": isinstance,
        "type": type,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Trading Coreutils — 预注入 helper
# ─────────────────────────────────────────────────────────────────────────────

def _latest(s: pd.Series, *_: Any) -> float | None:
    v = s.iloc[-1]
    return None if pd.isna(v) else float(v)


def _prev(s: pd.Series, n: int = 1) -> float | None:
    v = s.iloc[-1 - n]
    return None if pd.isna(v) else float(v)


def _crossover(fast: pd.Series, slow: pd.Series) -> bool:
    return bool(fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-2] <= slow.iloc[-2])


def _crossunder(fast: pd.Series, slow: pd.Series) -> bool:
    return bool(fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-2] >= slow.iloc[-2])


def _above(s: pd.Series, threshold: float) -> bool:
    return bool(s.iloc[-1] > threshold)


def _below(s: pd.Series, threshold: float) -> bool:
    return bool(s.iloc[-1] < threshold)


HELPERS: dict[str, Any] = {
    "latest": _latest,
    "prev": _prev,
    "crossover": _crossover,
    "crossunder": _crossunder,
    "above": _above,
    "below": _below,
}


# ─────────────────────────────────────────────────────────────────────────────
# 沙箱执行器
# ─────────────────────────────────────────────────────────────────────────────

def exec_compute(
    code: str,
    df: pd.DataFrame,
    account: dict[str, Any],
    extra_dfs: dict[str, pd.DataFrame] | None = None,
    timeout_ms: int = 500,
) -> dict[str, Any]:
    """
    沙箱执行 Agent 的 compute 代码。

    eval-first 策略：单表达式 → eval 返回值；多行 → exec 提取 result。
    """
    # 构造命名空间
    local_ns: dict[str, Any] = {
        "df": df.copy(),
        "account": account,
        "cash": account.get("cash", 0),
        "equity": account.get("equity", 0),
        "positions": account.get("positions", {}),
        **HELPERS,
    }
    # 多资产注入: df_aapl, df_spy, ...
    if extra_dfs:
        for sym, sym_df in extra_dfs.items():
            safe_name = f"df_{sym.lower().replace('.', '_').replace('-', '_')}"
            local_ns[safe_name] = sym_df.copy()

    # 超时保护（SIGALRM，仅 Unix/macOS）
    def _timeout_handler(_signum: int, _frame: Any) -> None:
        raise TimeoutError("计算超时")

    old_handler = _signal.signal(_signal.SIGALRM, _timeout_handler)
    _signal.setitimer(_signal.ITIMER_REAL, timeout_ms / 1000)
    try:
        return _exec_code(code, local_ns)
    except TimeoutError:
        return {"error": "计算超时，请简化代码或减少数据量"}
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}",
                "remediation": "检查变量名和数据访问是否正确"}
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, old_handler)


def _exec_code(code: str, local_ns: dict[str, Any]) -> dict[str, Any]:
    """eval-first：单表达式直接返回，多行 fallback 到 exec。"""
    stripped = code.strip()
    try:
        value = eval(stripped, _SAFE_GLOBALS, local_ns)  # noqa: S307
        return {"result": _serialize(value)}
    except SyntaxError:
        pass
    # 多行/语句 → exec
    exec(stripped, _SAFE_GLOBALS, local_ns)  # noqa: S102
    return {"result": _serialize(local_ns.get("result"))}


# ─────────────────────────────────────────────────────────────────────────────
# 返回值序列化
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(value: Any) -> Any:
    """自动降维：Series→最新值，DataFrame→报错，numpy→float。"""
    if value is None:
        return None
    if isinstance(value, pd.Series):
        v = value.iloc[-1]
        return None if pd.isna(v) else float(v)
    if isinstance(value, pd.DataFrame):
        return {"error": "DataFrame 太大，请用 .iloc[-1] 或聚合函数缩小结果"}
    if isinstance(value, (np.integer, np.floating)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return value
