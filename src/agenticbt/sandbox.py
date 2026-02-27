"""
[INPUT]: pandas, numpy, pandas_ta, math, signal, builtins, io, traceback
[OUTPUT]: exec_compute — 沙箱化 Python 执行器；HELPERS — Trading Coreutils
[POS]: compute 工具的执行层，被 tools.py 的 _compute 调用；与 Engine 无耦合
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import builtins as _builtins
import io
import math
import signal as _signal
import traceback as _traceback
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta


# ─────────────────────────────────────────────────────────────────────────────
# 白名单 import — 允许 pandas/numpy/pandas_ta/math，拒绝其他
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_MODULES = frozenset({"pandas", "numpy", "pandas_ta", "math"})


def _safe_import(name: str, globals: Any = None, locals: Any = None,
                 fromlist: tuple = (), level: int = 0) -> Any:
    """白名单 import：顶层模块名必须在 _ALLOWED_MODULES 中"""
    top = name.split(".")[0]
    if top not in _ALLOWED_MODULES:
        raise ImportError(
            f"沙箱禁止导入 '{name}'。"
            f"可用模块: pandas, numpy, pandas_ta, math（已预注入为 pd/np/ta/math）"
        )
    return _builtins.__import__(name, globals, locals, fromlist, level)


# ─────────────────────────────────────────────────────────────────────────────
# 黑名单 builtins — 从标准 builtins 移除危险项，保留 ~55 个标准条目
# ─────────────────────────────────────────────────────────────────────────────

_DANGEROUS = frozenset({
    "open", "breakpoint", "input", "exit", "quit",
    "compile", "exec", "eval", "__import__",
    "globals", "locals", "vars",
    "memoryview",
})

_safe_builtins: dict[str, Any] = {
    k: v for k, v in _builtins.__dict__.items()
    if k not in _DANGEROUS and not k.startswith("_")
}
_safe_builtins["__import__"] = _safe_import

_SAFE_GLOBALS: dict[str, Any] = {
    "pd": pd,
    "np": np,
    "ta": ta,
    "math": math,
    "__builtins__": _safe_builtins,
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
    print() 输出通过 _stdout 字段返回。
    """
    # stdout 捕获
    stdout_buf = io.StringIO()

    # 构造命名空间
    local_ns: dict[str, Any] = {
        "df": df.copy(),
        "account": account,
        "cash": account.get("cash", 0),
        "equity": account.get("equity", 0),
        "positions": account.get("positions", {}),
        "print": lambda *a, **kw: _builtins.print(*a, file=stdout_buf, **kw),
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
        result = _exec_code(code, local_ns)
        stdout = stdout_buf.getvalue()
        if stdout:
            result["_stdout"] = stdout
        return result
    except TimeoutError:
        return {"error": "计算超时，请简化代码或减少数据量"}
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}
    except Exception as e:
        tb_lines = _traceback.format_exc().strip().split("\n")
        return {"error": f"{type(e).__name__}: {e}",
                "traceback": "\n".join(tb_lines[-3:])}
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
