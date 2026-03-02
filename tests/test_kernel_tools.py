"""
[INPUT]: pytest-bdd, agent.kernel, agent.tools, agent.adapters.market.csv
[OUTPUT]: kernel_tools.feature step definitions（直接调用工具 handler）
[POS]: tests/ BDD 测试层，验证 Phase 1b/1c：6 工具 + 权限 + Session 持久化 + 自举
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from agent.kernel import Kernel, Permission, Session
from agent.adapters.market.csv import CsvAdapter
from agent.tools import compute, edit, market, read, write


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/kernel_tools.feature"

@scenario(FEATURE, "market_ohlcv 获取行情")
def test_market_ohlcv(): pass

@scenario(FEATURE, "compute 使用行情数据计算")
def test_compute(): pass

@scenario(FEATURE, "write 创建文件")
def test_write(): pass

@scenario(FEATURE, "read 读取文件")
def test_read(): pass

@scenario(FEATURE, "edit 修改文件")
def test_edit(): pass

@scenario(FEATURE, "受保护路径无确认回调时放行")
def test_permission_yolo(): pass

@scenario(FEATURE, "受保护路径确认拒绝时被拒")
def test_permission_denied(): pass

@scenario(FEATURE, "Session 保存与恢复")
def test_session_persistence(): pass

@scenario(FEATURE, "空工作区触发自举")
def test_bootstrap_empty(): pass

@scenario(FEATURE, "soul.md 存在时注入灵魂")
def test_bootstrap_soul(): pass


# ─────────────────────────────────────────────────────────────────────────────
# 测试数据
# ─────────────────────────────────────────────────────────────────────────────

def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "open": [10.0, 11.0, 12.0, 11.5, 12.5],
        "high": [11.0, 12.0, 13.0, 12.5, 13.5],
        "low":  [9.5, 10.5, 11.5, 11.0, 12.0],
        "close": [10.5, 11.5, 12.5, 12.0, 13.0],
        "volume": [1000, 1100, 1200, 900, 1300],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个带市场工具的 Kernel", target_fixture="ktctx")
def given_kernel_with_market():
    kernel = Kernel(api_key="test")
    adapter = CsvAdapter({"TEST": _sample_df()})
    market.register(kernel, adapter)
    compute.register(kernel)
    return {"kernel": kernel}


@given("一个带文件工具的 Kernel", target_fixture="ktctx")
def given_kernel_with_files(tmp_path):
    kernel = Kernel(api_key="test")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    read.register(kernel, workspace, cwd=workspace)
    write.register(kernel, workspace, cwd=workspace)
    edit.register(kernel, workspace, cwd=workspace)
    return {"kernel": kernel, "workspace": workspace}


@given(parsers.parse('已获取 "{symbol}" 行情'))
def given_fetched(ktctx, symbol):
    ktctx["kernel"]._tools["market_ohlcv"].handler({"symbol": symbol})


@given(parsers.parse('工作区已有文件 "{path}" 内容 "{content}"'))
def given_file_exists(ktctx, path, content):
    fp = ktctx["workspace"] / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")


@given(parsers.parse('路径 "{path}" 权限为 USER_CONFIRM'))
def given_permission(ktctx, path):
    ktctx["kernel"].permission(path, Permission.USER_CONFIRM)


@given("注册了拒绝确认的回调")
def given_deny_confirm(ktctx):
    ktctx["kernel"].on_confirm(lambda _path: False)


@given("一个有 4 条消息的 Session", target_fixture="ktctx")
def given_session_4(tmp_path):
    s = Session(session_id="test-persist")
    s.history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "再见"},
        {"role": "assistant", "content": "再见！"},
    ]
    return {"session": s, "tmp_path": tmp_path}


@given("一个空工作区", target_fixture="ktctx")
def given_empty_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return {"workspace": workspace}


@given(parsers.parse('一个含 soul.md 的工作区 内容为 "{content}"'), target_fixture="ktctx")
def given_soul_workspace(tmp_path, content):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "soul.md").write_text(content, encoding="utf-8")
    return {"workspace": workspace}


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('调用 market_ohlcv symbol "{symbol}"'), target_fixture="ktctx")
def when_market(ktctx, symbol):
    ktctx["result"] = ktctx["kernel"]._tools["market_ohlcv"].handler({"symbol": symbol})
    return ktctx


@when(parsers.parse('调用 compute code "{code}"'), target_fixture="ktctx")
def when_compute(ktctx, code):
    ktctx["result"] = ktctx["kernel"]._tools["compute"].handler({"code": code})
    return ktctx


@when(parsers.parse('调用 write path "{path}" content "{content}"'), target_fixture="ktctx")
def when_write(ktctx, path, content):
    ktctx["result"] = ktctx["kernel"]._tools["write"].handler(
        {"path": path, "content": content},
    )
    return ktctx


@when(parsers.parse('调用 read path "{path}"'), target_fixture="ktctx")
def when_read(ktctx, path):
    ktctx["result"] = ktctx["kernel"]._tools["read"].handler({"path": path})
    return ktctx


@when(parsers.parse('调用 edit path "{path}" old "{old}" new "{new}"'), target_fixture="ktctx")
def when_edit(ktctx, path, old, new):
    ktctx["result"] = ktctx["kernel"]._tools["edit"].handler(
        {"path": path, "old_string": old, "new_string": new},
    )
    return ktctx


@when("保存并重新加载 Session", target_fixture="ktctx")
def when_save_load(ktctx):
    path = ktctx["tmp_path"] / "session.json"
    ktctx["session"].save(path)
    ktctx["loaded"] = Session.load(path)
    return ktctx


@when("Kernel 启动", target_fixture="ktctx")
def when_boot(ktctx):
    kernel = Kernel(api_key="test")
    kernel.boot(ktctx["workspace"])
    ktctx["kernel"] = kernel
    return ktctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("结果包含 rows 和 latest")
def then_has_rows_latest(ktctx):
    r = ktctx["result"]
    assert "rows" in r and r["rows"] > 0
    assert "latest" in r


@then(parsers.parse('DataStore 中存在 "{key}"'))
def then_datastore(ktctx, key):
    assert ktctx["kernel"].data.get(key) is not None


@then("结果 result 为正整数")
def then_positive_int(ktctx):
    assert int(ktctx["result"]["result"]) > 0


@then(parsers.parse('工作区文件 "{path}" 内容为 "{content}"'))
def then_file_content(ktctx, path, content):
    fp = ktctx["workspace"] / path
    assert fp.exists()
    assert fp.read_text(encoding="utf-8") == content


@then(parsers.parse('结果内容包含 "{content}"'))
def then_result_content(ktctx, content):
    assert content in ktctx["result"]["content"]


@then("结果包含 error")
def then_has_error(ktctx):
    assert "error" in ktctx["result"]


@then("恢复后历史有 4 条消息")
def then_restored_4(ktctx):
    assert len(ktctx["loaded"].history) == 4
    assert ktctx["loaded"].id == "test-persist"


@then("system_prompt 包含自举种子")
def then_has_seed(ktctx):
    from agent.bootstrap.seed import SEED_PROMPT
    assert ktctx["kernel"]._system_prompt == SEED_PROMPT


@then(parsers.parse('system_prompt 包含 "{text}"'))
def then_has_text(ktctx, text):
    assert text in ktctx["kernel"]._system_prompt
