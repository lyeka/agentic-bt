"""
[INPUT]: pytest-bdd, agenticbt.sandbox, agenticbt.engine, agenticbt.tools, agenticbt.memory
[OUTPUT]: compute.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 compute 沙箱计算工具的全部行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import numpy as np
import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.engine import Engine
from agenticbt.memory import Memory, Workspace
from agenticbt.models import RiskConfig
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/compute.feature", "单表达式计算（eval 模式）")
def test_eval_expression(): pass

@scenario("features/compute.feature", "close 别名可用")
def test_close_alias(): pass

@scenario("features/compute.feature", "多行代码计算（exec 模式）")
def test_exec_multiline(): pass

@scenario("features/compute.feature", "多行最后表达式自动返回")
def test_repl_last_expr(): pass

@scenario("features/compute.feature", "使用预置 helper 函数")
def test_helper_functions(): pass

@scenario("features/compute.feature", "crossover 金叉判断")
def test_crossover(): pass

@scenario("features/compute.feature", "账户数据通过顶层变量访问")
def test_account_toplevel(): pass

@scenario("features/compute.feature", "账户数据通过 dict 访问")
def test_account_dict(): pass

@scenario("features/compute.feature", "symbol 参数选择数据源（单次仍为单资产）")
def test_symbol_selects_data_source(): pass

@scenario("features/compute.feature", "symbol 不存在返回错误")
def test_symbol_missing_error(): pass

@scenario("features/compute.feature", "防前瞻 — 数据截断到当前 bar")
def test_anti_lookahead(): pass

@scenario("features/compute.feature", "防篡改 — df.copy() 隔离")
def test_data_isolation(): pass

@scenario("features/compute.feature", "禁止导入非白名单模块")
def test_no_import(): pass

@scenario("features/compute.feature", "白名单 import 正常执行")
def test_import_whitelist(): pass

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

@scenario("features/compute.feature", "dict 深度序列化（Series/numpy 标量）")
def test_deep_serialize_dict(): pass


@scenario("features/compute.feature", "DataFrame 返回摘要")
def test_dataframe_summary(): pass


@scenario("features/compute.feature", "长数组自动摘要")
def test_array_summary(): pass


@scenario("features/compute.feature", "print 输出通过 _stdout 返回")
def test_print_stdout(): pass


@scenario("features/compute.feature", "try-except 正常工作")
def test_try_except(): pass


@scenario("features/compute.feature", "错误时也返回 _meta")
def test_error_with_meta(): pass


@scenario("features/compute.feature", "bbands helper 返回三元组")
def test_bbands_helper(): pass


@scenario("features/compute.feature", "bbands helper 数据不足返回 None 三元组")
def test_bbands_helper_insufficient(): pass


@scenario("features/compute.feature", "macd helper 返回三元组")
def test_macd_helper(): pass


@scenario("features/compute.feature", "macd helper 数据不足返回 None 三元组")
def test_macd_helper_insufficient(): pass


@scenario("features/compute.feature", "latest 对 float 透传")
def test_latest_float_passthrough(): pass


@scenario("features/compute.feature", "latest 对 numpy float64 透传")
def test_latest_numpy_passthrough(): pass


@scenario("features/compute.feature", "latest 对 None 透传")
def test_latest_none_passthrough(): pass


@scenario("features/compute.feature", "latest 对 Series 取末值")
def test_latest_series_last(): pass


@scenario("features/compute.feature", "latest 对 bbands 返回值安全调用")
def test_latest_bbands_safe(): pass


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


@when(parsers.parse('调用 compute symbol "{symbol}" 代码 "{code}"'), target_fixture="cptx")
def when_compute_with_symbol(cptx, symbol, code):
    cptx["result"] = cptx["kit"].execute("compute", {"code": code, "symbol": symbol})
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


@when("调用 compute 多行最后表达式返回", target_fixture="cptx")
def when_compute_last_expr(cptx):
    code = "x = np.mean(close)\nx"
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


@when("调用 compute 白名单 import numpy 计算均值", target_fixture="cptx")
def when_compute_whitelist_import(cptx):
    code = "import numpy as np\nresult = np.mean(df.close)"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute print 后赋值 result", target_fixture="cptx")
def when_compute_print_then_result(cptx):
    code = "val = df.close.iloc[-1]\nprint('close:', val)\nresult = val"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute try-except 捕获异常", target_fixture="cptx")
def when_compute_try_except(cptx):
    code = "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    result = {'caught': True}"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute dict 深度序列化", target_fixture="cptx")
def when_compute_deep_serialize_dict(cptx):
    code = "result = {'rsi': ta.rsi(close, 14), 'mean': np.mean(close)}"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


@when("调用 compute bbands 后对返回值调用 latest", target_fixture="cptx")
def when_compute_latest_bbands(cptx):
    code = "upper, mid, lower = bbands(df.close, 20, 2)\nresult = latest(upper)"
    cptx["result"] = cptx["kit"].execute("compute", {"code": code})
    cptx["results"].append(cptx["result"])
    return cptx


# ─────────────────────────────────────────────────────────────────────────────
# Given — 多资产（compute 仍然是单资产：通过 symbol 选择数据源）
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


@then(parsers.parse('compute 返回值等于 symbol "{symbol}" 当前收盘价'))
def then_returns_close_for_symbol(cptx, symbol):
    r = cptx["result"]["result"]
    eng = cptx["eng"]
    df = eng._data_by_symbol[symbol]
    expected = float(df.iloc[eng._bar_index]["close"])
    assert isinstance(r, float)
    assert abs(r - expected) < 1e-6


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


@then(parsers.parse('compute 返回包含 "{text}" 的错误'))
def then_returns_error_with_text(cptx, text):
    assert "error" in cptx["result"], f"expected error, got {cptx['result']}"
    assert text in cptx["result"]["error"], f"expected '{text}' in error: {cptx['result']['error']}"


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


@then("compute 返回包含 rsi mean 的 dict 且都是 float")
def then_returns_dict_with_floats(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, dict), f"expected dict, got {type(r)}: {r}"
    assert "rsi" in r
    assert "mean" in r
    assert type(r["rsi"]) is float, f"expected python float, got {type(r['rsi'])}: {r['rsi']}"
    assert type(r["mean"]) is float, f"expected python float, got {type(r['mean'])}: {r['mean']}"


@then("compute 返回 DataFrame 摘要")
def then_returns_dataframe_summary(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, dict), f"expected dict summary, got {type(r)}: {r}"
    assert r.get("_type") == "dataframe", f"expected _type=dataframe, got {r.get('_type')}: {r}"
    assert "shape" in r and isinstance(r["shape"], list)
    assert "columns" in r and isinstance(r["columns"], list)
    assert "tail" in r and isinstance(r["tail"], list)


@then("compute 返回 array 摘要")
def then_returns_array_summary(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, dict), f"expected dict summary, got {type(r)}: {r}"
    assert r.get("_type") == "array", f"expected _type=array, got {r.get('_type')}: {r}"
    assert r.get("truncated") is True
    assert isinstance(r.get("tail"), list)
    assert len(r["tail"]) <= 200


@then("compute 返回包含 _stdout 的结果")
def then_returns_stdout(cptx):
    assert "_stdout" in cptx["result"], f"expected _stdout, got {cptx['result']}"
    assert "close:" in cptx["result"]["_stdout"]


@then("compute 返回包含 caught 的 dict")
def then_returns_caught_dict(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, dict), f"expected dict, got {type(r)}: {r}"
    assert r.get("caught") is True


@then("compute 返回包含 _meta 的错误结果")
def then_returns_error_with_meta(cptx):
    assert "error" in cptx["result"], f"expected error, got {cptx['result']}"
    assert "_meta" in cptx["result"], f"expected _meta in error result, got {cptx['result']}"


@then("compute 返回包含 upper middle lower 的三元组")
def then_returns_bbands_tuple(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, (list, tuple)), f"expected tuple/list, got {type(r)}: {r}"
    assert len(r) == 3
    upper, middle, lower = r
    assert isinstance(upper, float)
    assert isinstance(middle, float)
    assert isinstance(lower, float)


@then("compute 返回 None 三元组")
def then_returns_none_tuple(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, (list, tuple)), f"expected tuple/list, got {type(r)}: {r}"
    assert len(r) == 3
    assert all(v is None for v in r), f"expected all None, got {r}"


@then(parsers.parse("compute 返回值等于 {value:g}"))
def then_returns_value_equal(cptx, value):
    r = cptx["result"]["result"]
    assert isinstance(r, (int, float)), f"expected numeric, got {type(r)}: {r}"
    assert abs(r - value) < 1e-6, f"expected {value}, got {r}"


@then("compute 返回 None 结果")
def then_returns_none(cptx):
    r = cptx["result"]["result"]
    assert r is None, f"expected None, got {type(r)}: {r}"


@then("compute 无错误返回")
def then_no_error(cptx):
    assert "error" not in cptx["result"], f"unexpected error: {cptx['result'].get('error')}"


@then("compute 返回包含 macd signal histogram 的三元组")
def then_returns_macd_tuple(cptx):
    r = cptx["result"]["result"]
    assert isinstance(r, (list, tuple)), f"expected tuple/list, got {type(r)}: {r}"
    assert len(r) == 3
