"""
[INPUT]: pandas, numpy, pandas_ta, math, signal, builtins, io, traceback, ast
[OUTPUT]: exec_compute — 沙箱化 Python 执行器；HELPERS — Trading Coreutils（含 REPL 语义与输出治理）
[POS]: 公共计算沙箱，被 agenticbt/tools.py 和 agent/tools/compute.py 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import ast
import builtins as _builtins
import io
import math
import signal as _signal
import traceback as _traceback
from datetime import date as _date
from datetime import datetime as _datetime
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

# 输出治理常量（保持稳定，便于测试/提示词学习）
_MAX_LIST_ITEMS = 200
_MAX_DICT_KEYS = 100
_MAX_STR_LEN = 2000
_MAX_DF_PREVIEW_ROWS = 5
_MAX_DF_PREVIEW_COLS = 8
_MAX_DEPTH = 6


# ─────────────────────────────────────────────────────────────────────────────
# Trading Coreutils — 预注入 helper
# ─────────────────────────────────────────────────────────────────────────────

def _latest(s: Any, *_: Any) -> float | None:
    """取最新值 — 幂等：Series→末值，标量→透传，None→None"""
    if s is None:
        return None
    if isinstance(s, (bool, np.bool_)):
        return bool(s)
    if isinstance(s, (int, float)):
        return None if pd.isna(s) else s
    if isinstance(s, (np.integer, np.floating)):
        return None if pd.isna(s) else float(s)
    # pd.Series 路径（原有行为）
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


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0) -> tuple:
    """布林带 helper：返回 (upper, middle, lower) 最新值，数据不足返回 (None, None, None)"""
    bb = ta.bbands(close, length=length, std=std)
    if bb is None or bb.empty:
        return (None, None, None)
    cols = list(bb.columns)  # 版本无关：BBL, BBM, BBU 顺序可能变化
    # pandas_ta 列名含 BBL/BBM/BBU 前缀，按前缀匹配
    get = lambda prefix: _latest(bb[[c for c in cols if c.startswith(prefix)][0]])
    return (get("BBU"), get("BBM"), get("BBL"))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD helper：返回 (macd, signal, histogram) 最新值，数据不足返回 (None, None, None)"""
    m = ta.macd(close, fast=fast, slow=slow, signal=signal)
    if m is None or m.empty:
        return (None, None, None)
    cols = list(m.columns)  # MACD_, MACDs_, MACDh_ 前缀
    get = lambda prefix: _latest(m[[c for c in cols if c.startswith(prefix)][0]])
    return (get("MACD_"), get("MACDs_"), get("MACDh_"))


def _tail(x: Any, n: int = 20) -> list[Any]:
    """取尾部 N 个元素，用于调试/查看序列（返回 Python list，长度硬上限）。"""
    try:
        n_int = int(n)
    except Exception:
        n_int = 20
    if n_int <= 0:
        n_int = 1
    if n_int > _MAX_LIST_ITEMS:
        n_int = _MAX_LIST_ITEMS

    if x is None:
        return []
    if isinstance(x, pd.Series):
        return [_serialize(v, depth=1) for v in x.tail(n_int).tolist()]
    if isinstance(x, np.ndarray):
        if x.ndim == 0:
            return [_serialize(x.item(), depth=1)]
        flat = x.ravel()
        tail_vals = flat[-n_int:] if flat.size > n_int else flat
        return [_serialize(v, depth=1) for v in tail_vals.tolist()]
    if isinstance(x, (list, tuple)):
        tail_vals = x[-n_int:] if len(x) > n_int else x
        return [_serialize(v, depth=1) for v in tail_vals]
    # 标量：给一个单元素 list，方便统一处理
    return [_serialize(x, depth=1)]


def _nz(x: Any, default: float = 0.0) -> Any:
    """None/NaN/inf → default；Series 取末值后再判空。"""
    v = x
    if isinstance(v, pd.Series):
        if v.empty:
            return default
        v = v.iloc[-1]
    if v is None:
        return default
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return default if (pd.isna(f) or not math.isfinite(f)) else f
    try:
        return default if pd.isna(v) else v
    except Exception:
        return v


HELPERS: dict[str, Any] = {
    "latest": _latest,
    "prev": _prev,
    "crossover": _crossover,
    "crossunder": _crossunder,
    "above": _above,
    "below": _below,
    "bbands": _bbands,
    "macd": _macd,
    "tail": _tail,
    "nz": _nz,
}


# ─────────────────────────────────────────────────────────────────────────────
# 沙箱执行器
# ─────────────────────────────────────────────────────────────────────────────

def exec_compute(
    code: str,
    df: pd.DataFrame,
    account: dict[str, Any],
    timeout_ms: int = 500,
) -> dict[str, Any]:
    """
    沙箱执行 Agent 的 compute 代码。

    eval-first 策略：单表达式 → eval 返回值；多行 → exec。
    REPL 语义：多行代码若最后一行是表达式，会自动返回该表达式的值（类似 Jupyter）。
    print() 输出通过 _stdout 字段返回。
    """
    # stdout 捕获
    stdout_buf = io.StringIO()

    df_copy = df.copy()
    # 构造命名空间
    local_ns: dict[str, Any] = {
        "df": df_copy,
        # TradingView 风格别名（单资产）
        "open": df_copy["open"],
        "high": df_copy["high"],
        "low": df_copy["low"],
        "close": df_copy["close"],
        "volume": df_copy["volume"],
        "date": df_copy["date"],
        "account": account,
        "cash": account.get("cash", 0),
        "equity": account.get("equity", 0),
        "positions": account.get("positions", {}),
        "print": lambda *a, **kw: _builtins.print(*a, file=stdout_buf, **kw),
        **HELPERS,
    }

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
        return {
            "error": "计算超时，请简化代码或减少数据量",
            "remediation": "避免 while/for 纯 Python 大循环；优先用 pandas/numpy 向量化与 rolling。",
        }
    except SyntaxError as e:
        return {
            "error": f"SyntaxError: {e}",
            "remediation": "检查 Python 语法（缩进/冒号/括号）。",
        }
    except Exception as e:
        tb_lines = _traceback.format_exc().strip().split("\n")
        return {
            "error": f"{type(e).__name__}: {e}",
            "remediation": _remediation_for_exc(e),
            "traceback": "\n".join(tb_lines[-8:]),
        }
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, old_handler)


def _exec_code(code: str, local_ns: dict[str, Any]) -> dict[str, Any]:
    """eval-first + REPL：单表达式直接返回；多行若最后一行是表达式，则返回该表达式。"""
    stripped = code.strip()
    if not stripped:
        return {
            "error": "未产生输出",
            "remediation": "写一个表达式（如 ta.rsi(close,14)）或赋值给 result。",
        }

    try:
        compiled = compile(stripped, "<compute>", "eval")
        value = eval(compiled, _SAFE_GLOBALS, local_ns)  # noqa: S307
        return {"result": _serialize(value, depth=0)}
    except SyntaxError:
        pass

    # 多行/语句 → exec（REPL：最后表达式自动返回）
    module = ast.parse(stripped, "<compute>", "exec")
    if not module.body:
        return {
            "error": "未产生输出",
            "remediation": "写一个表达式（如 ta.rsi(close,14)）或赋值给 result。",
        }

    last = module.body[-1]
    if isinstance(last, ast.Expr):
        prefix_body = module.body[:-1]
        if prefix_body:
            prefix_mod = ast.Module(body=prefix_body, type_ignores=[])
            exec(compile(prefix_mod, "<compute>", "exec"), _SAFE_GLOBALS, local_ns)  # noqa: S102
        if "result" in local_ns:
            return {"result": _serialize(local_ns.get("result"), depth=0)}
        expr = ast.Expression(last.value)
        value = eval(compile(expr, "<compute>", "eval"), _SAFE_GLOBALS, local_ns)  # noqa: S307
        return {"result": _serialize(value, depth=0)}

    exec(compile(module, "<compute>", "exec"), _SAFE_GLOBALS, local_ns)  # noqa: S102
    if "result" in local_ns:
        return {"result": _serialize(local_ns.get("result"), depth=0)}
    return {
        "error": "未产生输出",
        "remediation": "设置 result=... 或让最后一行成为表达式。",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 返回值序列化
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(value: Any, depth: int = 0) -> Any:
    """
    深度 JSON-safe 序列化 + 输出治理：
    - Series → 最新值
    - DataFrame/长数组 → 摘要对象（不会爆 token）
    - dict/list/tuple/ndarray → 递归转换 numpy/pandas 标量
    """
    if depth > _MAX_DEPTH:
        s = str(value)
        return s if len(s) <= _MAX_STR_LEN else (s[:_MAX_STR_LEN] + "...")

    if value is None:
        return None

    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)

    if isinstance(value, (float, np.floating)):
        f = float(value)
        return f if math.isfinite(f) else None

    if isinstance(value, (str,)):
        return value if len(value) <= _MAX_STR_LEN else (value[:_MAX_STR_LEN] + "...")

    if isinstance(value, (_datetime, _date, pd.Timestamp)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, np.datetime64):
        return str(value)

    if isinstance(value, pd.Series):
        if value.empty:
            return None
        return _serialize(value.iloc[-1], depth=depth + 1)

    if isinstance(value, pd.DataFrame):
        rows, cols = value.shape
        col_names = [str(c) for c in list(value.columns)[:_MAX_DF_PREVIEW_COLS]]
        row_start = max(0, rows - _MAX_DF_PREVIEW_ROWS)
        preview = value.iloc[row_start:rows, :_MAX_DF_PREVIEW_COLS]
        records: list[dict[str, Any]] = []
        for _, row in preview.iterrows():
            rec: dict[str, Any] = {}
            for i, col in enumerate(col_names):
                rec[col] = _serialize(row.iloc[i], depth=depth + 1)
            records.append(rec)
        truncated = rows > _MAX_DF_PREVIEW_ROWS or cols > _MAX_DF_PREVIEW_COLS
        return {
            "_type": "dataframe",
            "shape": [rows, cols],
            "columns": col_names,
            "tail": records,
            "truncated": truncated,
        }

    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return _serialize(value.item(), depth=depth + 1)
        flat = value.ravel()
        n_total = int(flat.size)
        n_tail = min(_MAX_LIST_ITEMS, n_total)
        tail_vals = flat[-n_tail:] if n_total > n_tail else flat
        return {
            "_type": "ndarray" if value.ndim > 1 else "array",
            "shape": list(value.shape),
            "len": n_total,
            "tail": [_serialize(v, depth=depth + 1) for v in tail_vals.tolist()],
            "truncated": n_total > _MAX_LIST_ITEMS,
        }

    if isinstance(value, (list, tuple)):
        n_total = len(value)
        if n_total <= _MAX_LIST_ITEMS:
            return [_serialize(v, depth=depth + 1) for v in value]
        tail_vals = value[-_MAX_LIST_ITEMS:]
        return {
            "_type": "array",
            "len": n_total,
            "tail": [_serialize(v, depth=depth + 1) for v in tail_vals],
            "truncated": True,
        }

    if isinstance(value, dict):
        items = sorted(((str(k), v) for k, v in value.items()), key=lambda kv: kv[0])
        n_total = len(items)
        if n_total <= _MAX_DICT_KEYS:
            return {k: _serialize(v, depth=depth + 1) for k, v in items}
        limited = items[:_MAX_DICT_KEYS]
        return {
            "_type": "dict",
            "len": n_total,
            "items": {k: _serialize(v, depth=depth + 1) for k, v in limited},
            "truncated": True,
        }

    s = str(value)
    return s if len(s) <= _MAX_STR_LEN else (s[:_MAX_STR_LEN] + "...")


def _remediation_for_exc(exc: Exception) -> str:
    """将常见异常映射为 LLM 可执行的修复建议（尽量短）。"""
    if isinstance(exc, ImportError):
        return "沙箱仅允许导入 pandas/numpy/pandas_ta/math；且已预注入为 pd/np/ta/math，通常不需要 import。"
    if isinstance(exc, NameError):
        return (
            "可用变量: df, open, high, low, close, volume, date, account, cash, equity, positions, pd, np, ta, math。"
            "helpers: latest, prev, crossover, crossunder, above, below, bbands, macd, tail, nz。"
            "compute 不是指标菜单：需要新指标直接用 Python/Series 运算实现。"
        )
    if isinstance(exc, KeyError):
        return "df 列为 date/open/high/low/close/volume（小写）。可用 df.columns 查看。"
    if isinstance(exc, IndexError):
        return "检查数据长度: len(df)。避免固定负索引；可用 min(n, len(df)) 或 tail(close, n)。"
    if isinstance(exc, ZeroDivisionError):
        return "检查除数是否为 0；可用 nz(x, default) 处理空值/NaN。"
    if isinstance(exc, ValueError) and "unpack" in str(exc):
        return "ta.macd()/ta.bbands() 返回 DataFrame，不能直接解包；请用 helper macd()/bbands()，或直接返回 DataFrame 让系统摘要。"
    return "检查变量名/索引/返回值；建议返回标量或小 dict。"
