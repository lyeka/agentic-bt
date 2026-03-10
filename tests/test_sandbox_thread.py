"""
[INPUT]: pytest-bdd, threading, core.sandbox
[OUTPUT]: sandbox_thread.feature step definitions（fixture: sbtx）
[POS]: tests/ BDD 测试层，验证沙箱线程安全：主线程/子线程/超时
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import threading
from typing import Any

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from core.sandbox import exec_compute


FEATURE = "features/sandbox_thread.feature"


@scenario(FEATURE, "主线程正常执行")
def test_main_thread(): pass


@scenario(FEATURE, "子线程正常执行")
def test_sub_thread(): pass


@scenario(FEATURE, "子线程中死循环触发超时")
def test_sub_thread_timeout(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个示例 DataFrame", target_fixture="sbtx")
def given_sample_df():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "open": [10.0, 11.0, 12.0, 11.5, 12.5],
        "high": [11.0, 12.0, 13.0, 12.5, 13.5],
        "low":  [9.5, 10.5, 11.5, 11.0, 12.0],
        "close": [10.5, 11.5, 12.5, 12.0, 13.0],
        "volume": [1000, 1100, 1200, 900, 1300],
    })
    return {"df": df, "account": {"cash": 100000, "equity": 100000, "positions": {}}}


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('在主线程执行 compute "{code}"'), target_fixture="sbtx")
def when_main_thread(sbtx, code):
    sbtx["result"] = exec_compute(code, sbtx["df"], sbtx["account"])
    return sbtx


@when(parsers.parse('在子线程执行 compute "{code}"'), target_fixture="sbtx")
def when_sub_thread(sbtx, code):
    result_holder: dict[str, Any] = {}

    def _run():
        result_holder["result"] = exec_compute(code, sbtx["df"], sbtx["account"])

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=5)
    sbtx["result"] = result_holder.get("result", {"error": "线程未返回"})
    return sbtx


@when(parsers.parse('在子线程执行 compute "{code}" 超时 {ms:d}ms'), target_fixture="sbtx")
def when_sub_thread_timeout(sbtx, code, ms):
    result_holder: dict[str, Any] = {}

    def _run():
        result_holder["result"] = exec_compute(code, sbtx["df"], sbtx["account"], timeout_ms=ms)

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=5)
    sbtx["result"] = result_holder.get("result", {"error": "线程未返回"})
    return sbtx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse("结果 result 为 {expected:d}"))
def then_result_eq(sbtx, expected):
    assert "error" not in sbtx["result"], f"unexpected error: {sbtx['result']}"
    assert sbtx["result"]["result"] == expected


@then("结果包含超时错误")
def then_timeout_error(sbtx):
    assert "error" in sbtx["result"]
    assert "超时" in sbtx["result"]["error"]
