"""
[INPUT]: pytest-bdd, agenticbt.sandbox, agenticbt.engine, agenticbt.tools, agenticbt.memory
[OUTPUT]: compute.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 compute 沙箱计算工具的全部行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.engine import Engine
from agenticbt.memory import Memory, Workspace
from agenticbt.models import RiskConfig
from agenticbt.sandbox import exec_compute
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/compute.feature", "单表达式计算（eval 模式）")
def test_eval_expression(): pass

@scenario("features/compute.feature", "多行代码计算（exec 模式）")
def test_exec_multiline(): pass

@scenario("features/compute.feature", "使用预置 helper 函数")
def test_helper_functions(): pass

@scenario("features/compute.feature", "crossover 金叉判断")
def test_crossover(): pass

@scenario("features/compute.feature", "账户数据通过顶层变量访问")
def test_account_toplevel(): pass

@scenario("features/compute.feature", "账户数据通过 dict 访问")
def test_account_dict(): pass

@scenario("features/compute.feature", "多资产数据注入")
def test_multi_asset(): pass

@scenario("features/compute.feature", "防前瞻 — 数据截断到当前 bar")
def test_anti_lookahead(): pass

@scenario("features/compute.feature", "防篡改 — df.copy() 隔离")
def test_data_isolation(): pass

@scenario("features/compute.feature", "禁止导入模块")
def test_no_import(): pass

@scenario("features/compute.feature", "超时保护")
def test_timeout(): pass

@scenario("features/compute.feature", "语法错误友好提示")
def test_syntax_error(): pass

@scenario("features/compute.feature", "运行时错误友好提示")
def test_runtime_error(): pass

@scenario("features/compute.feature", "越界访问友好提示")
def test_index_error(): pass

@scenario("features/compute.feature", "Series 自动取最新值")
def test_series_auto_latest(): pass

@scenario("features/compute.feature", "numpy 类型自动转 float")
def test_numpy_to_float(): pass


# ─────────────────────────────────────────────────────────────────────────────
# 数据工厂
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": close + rng.normal(0, 0.5, n),
        "high": close + rng.uniform(0.5, 2, n),
        "low": close - rng.uniform(0.5, 2, n),
        "close": close,
        "volume": rng.integers(500_000, 2_000_000, n).astype(float),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Background
# ─────────────────────────────────────────────────────────────────────────────

@given("初始化 compute 测试引擎（50 根 bar 推进到第 30 根）", target_fixture="cptx")
def given_compute_engine():
    df = _make_df(50)
    eng = Engine(data=df, symbol="AAPL", initial_cash=100_000.0,
                 risk=RiskConfig(max_position_pct=1.0))
    # 推进到 bar 30
    for _ in range(31):
        eng.advance()
    ws = Workspace()
    mem = Memory(ws)
    kit = ToolKit(engine=eng, memory=mem)
    return {"eng": eng, "kit": kit, "results": []}


# ─────────────────────────────────────────────────────────────────────────────
# When — 调用 compute
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('调用 compute "{code}"'), target_fixture="cptx")
def when_compute_inline(cptx, code):
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute 多行代码计算 sma 和 above", target_fixture="cptx")
def when_compute_multiline(cptx):
    code = (
        "sma = df.close.rolling(20).mean().iloc[-1]\n"
        "result = {'sma': sma, 'above': df.close.iloc[-1] > sma}"
    )
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when(parsers.parse('再次调用 compute "{code}"'), target_fixture="cptx")
def when_compute_again(cptx, code):
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute 超时代码", target_fixture="cptx")
def when_compute_timeout(cptx):
    # 用大量计算触发超时（500ms）
    code = "x = 0\nwhile True:\n    x += 1"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


# ─────────────────────────────────────────────────────────────────────────────
# Given — 多资产
# ─────────────────────────────────────────────────────────────────────────────

@given("初始化多资产 compute 引擎（AAPL 和 SPY）", target_fixture="cptx")
def given_multi_asset_compute():
    data = {"AAPL": _make_df(50, seed=42), "SPY": _make_df(50, seed=99)}
    eng = Engine(data=data, symbol="AAPL", initial_cash=100_000.0,
                 risk=RiskConfig(max_position_pct=1.0))
    for _ in range(31):
        eng.advance()
    ws = Workspace()
    mem = Memory(ws)
    kit = ToolKit(engine=eng, memory=mem)
    return {"eng": eng, "kit": kit, "results": []}


# ─────────────────────────────────────────────────────────────────────────────
# Then — 断言
# ─────────────────────────────────────────────────────────────────────────────

@then("compute 返回当前收盘价标量")
def then_returns_close_scalar(cptx):
    r = cptx["result"]["result"]
    eng = cptx["eng"]
    expected = float(eng._data.iloc[eng._bar_index]["close"])
    assert isinstance(r, float)
    assert abs(r - expected) < 1e-6


@then("compute 返回包含 sma 和 above 的 dict")
def then_returns_sma_dict(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, dict)
    assert "sma" in r
    assert "above" in r
    assert bool(r["above"]) in (True, False)  # np.bool_ 兼容


@then("compute 返回浮点数值")
def then_returns_float(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, float), f"expected float, got {type(r)}: {r}"


@then("compute 返回布尔值")
def then_returns_bool(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, bool), f"expected bool, got {type(r)}: {r}"


@then("compute 返回值等于当前账户净值")
def then_returns_equity(cptx):
    r = cptx["result"]["result"]
    snap = cptx["eng"].account_snapshot()
    assert abs(r - snap.equity) < 1e-6


@then("compute 返回值等于当前现金余额")
def then_returns_cash(cptx):
    r = cptx["result"]["result"]
    snap = cptx["eng"].account_snapshot()
    assert abs(r - snap.cash) < 1e-6


@then("compute 返回值等于 31")
def then_returns_31(cptx):
    r = cptx["result"]["result"]
    assert r == 31, f"expected 31, got {r}"


@then("compute 第二次返回原始收盘价")
def then_second_returns_original(cptx):
    # 第二次调用的结果
    r = cptx["results"][-1]["result"]
    eng = cptx["eng"]
    expected = float(eng._data.iloc[eng._bar_index]["close"])
    assert isinstance(r, float)
    assert abs(r - expected) < 1e-6


@then("compute 返回包含 error 的结果")
def then_returns_error(cptx):
    assert "error" in cptx["result"], f"expected error, got {cptx['result']}"


@then("compute 返回超时错误")
def then_returns_timeout(cptx):
    assert "error" in cptx["result"]
    assert "超时" in cptx["result"]["error"]


@then("compute 返回包含 SyntaxError 的错误")
def then_returns_syntax_error(cptx):
    assert "error" in cptx["result"]
    assert "SyntaxError" in cptx["result"]["error"]


@then("compute 返回包含 ZeroDivisionError 的错误")
def then_returns_zero_division(cptx):
    assert "error" in cptx["result"]
    assert "ZeroDivisionError" in cptx["result"]["error"]


@then("compute 返回包含 IndexError 的错误")
def then_returns_index_error(cptx):
    assert "error" in cptx["result"]
    assert "IndexError" in cptx["result"]["error"]


@then("compute 返回 Python float 类型")
def then_returns_python_float(cptx):
    r = cptx["result"]["result"]
    assert type(r) is float, f"expected float, got {type(r)}"
