"""
[INPUT]: pytest-bdd, athenaclaw.kernel, athenaclaw.tools, athenaclaw.integrations.market.csv
[OUTPUT]: kernel_tools.feature step definitions（直接调用工具 handler）
[POS]: tests/ BDD 测试层，验证 Kernel 工具/权限/Session/自举
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pandas as pd
from pytest_bdd import given, parsers, scenario, then, when

from athenaclaw.integrations.market.csv import CsvAdapter
from athenaclaw.kernel import Kernel, Permission, Session
from athenaclaw.tools import compute, edit, market, read, write


FEATURE = "features/kernel_tools.feature"


@scenario(FEATURE, "market_ohlcv 返回带元数据的 OHLCV 数据")
def test_market_ohlcv(): pass


@scenario(FEATURE, "market_ohlcv 可只入管道不回显 data")
def test_market_ohlcv_without_result_data(): pass


@scenario(FEATURE, "market_ohlcv 透传 interval/mode/start/end 参数")
def test_market_ohlcv_selector_passthrough(): pass


@scenario(FEATURE, "compute 默认使用最近一次行情数据计算")
def test_compute_default(): pass


@scenario(FEATURE, "compute 可按 selector 选择不同数据集")
def test_compute_selector(): pass


@scenario(FEATURE, "compute 显式提供 symbol 时不会跨 symbol 回退")
def test_compute_symbol_scoped_lookup(): pass


@scenario(FEATURE, "market_ohlcv latest 不接受 start/end")
def test_market_latest_rejects_range(): pass


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


def _sample_daily_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "open": [10.0, 11.0, 12.0, 11.5, 12.5],
        "high": [11.0, 12.0, 13.0, 12.5, 13.5],
        "low": [9.5, 10.5, 11.5, 11.0, 12.0],
        "close": [10.5, 11.5, 12.5, 12.0, 13.0],
        "volume": [1000, 1100, 1200, 900, 1300],
    })


def _sample_minute_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02 09:31:00", "2024-01-02 09:32:00"]),
        "open": [13.0, 13.2],
        "high": [13.3, 13.4],
        "low": [12.9, 13.1],
        "close": [13.1, 13.3],
        "volume": [500, 700],
    })


def _sample_latest_df() -> pd.DataFrame:
    return _sample_minute_df().tail(1).reset_index(drop=True)


@given("一个带市场工具的 Kernel", target_fixture="ktctx")
def given_kernel_with_market():
    kernel = Kernel(api_key="test")
    adapter = CsvAdapter({
        "TEST": {
            ("1d", "history"): _sample_daily_df(),
            ("1m", "history"): _sample_minute_df(),
            ("1m", "latest"): _sample_latest_df(),
        }
    })
    market.register(kernel, adapter)
    compute.register(kernel)
    return {"kernel": kernel}


@given("一个带多周期市场工具的 Kernel", target_fixture="ktctx")
def given_kernel_with_multi_market():
    return given_kernel_with_market()


@given("一个带跨 symbol 数据的 Kernel", target_fixture="ktctx")
def given_kernel_with_cross_symbol_market():
    kernel = Kernel(api_key="test")
    adapter = CsvAdapter({
        "TEST": {("1d", "history"): _sample_daily_df()},
        "OTHER": {("1m", "latest"): _sample_latest_df()},
    })
    market.register(kernel, adapter)
    compute.register(kernel)
    return {"kernel": kernel}


def test_compute_schema_explains_series_and_market_handoff():
    kernel = Kernel(api_key="test")
    compute.register(kernel)

    desc = kernel._tools["compute"].schema["function"]["description"]

    assert "不会把其返回 JSON 中的 data 变量带进来" in desc
    assert "include_data_in_result=false" in desc
    assert "每次调用独立命名空间" in desc
    assert "latest(close) 或 close.iloc[-1]" in desc
    assert "不要写 close[-1]/date[-1]" in desc
    assert "多个 symbol/interval/mode/start/end 组合" in desc
    assert "date 在分钟数据中会包含时分秒" in desc


def test_market_schema_explains_compute_handoff():
    kernel = Kernel(api_key="test")
    adapter = CsvAdapter({"TEST": {("1d", "history"): _sample_daily_df()}})
    market.register(kernel, adapter)

    desc = kernel._tools["market_ohlcv"].schema["function"]["description"]
    params = kernel._tools["market_ohlcv"].schema["function"]["parameters"]["properties"]

    assert "无论是否回显 data" in desc
    assert "latest 不是交易所实时流" in desc
    assert "compute 必须复用同一组 selector" in desc
    assert "不会以 data 变量自动注入 compute" in desc
    assert "不影响 fetch/DataStore/compute" in desc
    assert "include_data_in_result" in params


@given("一个带市场工具的 Kernel（记录 fetch 参数）", target_fixture="ktctx")
def given_kernel_with_spy_market():
    kernel = Kernel(api_key="test")
    call_log: list[dict] = []

    class SpyAdapter:
        name = "spy"

        def fetch(self, query):
            from athenaclaw.tools.market.schema import make_fetch_result

            call_log.append({
                "symbol": query.normalized_symbol,
                "interval": query.interval,
                "mode": query.mode,
                "start": query.start,
                "end": query.end,
            })
            return make_fetch_result(
                df=_sample_daily_df(),
                query=query,
                source=self.name,
                timezone=query.timezone,
            )

    market.register(kernel, SpyAdapter())
    return {"kernel": kernel, "call_log": call_log}


@given("一个带文件工具的 Kernel", target_fixture="ktctx")
def given_kernel_with_files(tmp_path):
    kernel = Kernel(api_key="test")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    read.register(kernel, workspace, cwd=workspace)
    write.register(kernel, workspace, cwd=workspace)
    edit.register(kernel, workspace, cwd=workspace)
    return {"kernel": kernel, "workspace": workspace}


@given(parsers.parse('已获取 "{symbol}" interval "{interval}" mode "{mode}" 行情'))
def given_fetched(ktctx, symbol, interval, mode):
    ktctx["kernel"]._tools["market_ohlcv"].handler(
        {"symbol": symbol, "interval": interval, "mode": mode}
    )


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
    session = Session(session_id="test-persist")
    session.history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "再见"},
        {"role": "assistant", "content": "再见！"},
    ]
    return {"session": session, "tmp_path": tmp_path}


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


@when(parsers.parse('调用 market_ohlcv symbol "{symbol}" interval "{interval}" mode "{mode}"'), target_fixture="ktctx")
def when_market(ktctx, symbol, interval, mode):
    ktctx["result"] = ktctx["kernel"]._tools["market_ohlcv"].handler(
        {"symbol": symbol, "interval": interval, "mode": mode}
    )
    return ktctx


@when(parsers.parse('调用 market_ohlcv symbol "{symbol}" interval "{interval}" mode "{mode}" include_data_in_result "{flag}"'), target_fixture="ktctx")
def when_market_with_data_visibility(ktctx, symbol, interval, mode, flag):
    ktctx["result"] = ktctx["kernel"]._tools["market_ohlcv"].handler(
        {
            "symbol": symbol,
            "interval": interval,
            "mode": mode,
            "include_data_in_result": flag.lower() == "true",
        }
    )
    return ktctx


@when(parsers.parse('调用 market_ohlcv symbol "{symbol}" interval "{interval}" mode "{mode}" start "{start}" end "{end}"'), target_fixture="ktctx")
def when_market_with_range(ktctx, symbol, interval, mode, start, end):
    ktctx["result"] = ktctx["kernel"]._tools["market_ohlcv"].handler(
        {"symbol": symbol, "interval": interval, "mode": mode, "start": start, "end": end}
    )
    return ktctx


@when(parsers.parse('调用 market_ohlcv symbol "{symbol}" interval "{interval}" mode "{mode}" start "{start}" end "{end}" 期待异常'), target_fixture="ktctx")
def when_market_with_error(ktctx, symbol, interval, mode, start, end):
    try:
        ktctx["kernel"]._tools["market_ohlcv"].handler(
            {"symbol": symbol, "interval": interval, "mode": mode, "start": start, "end": end}
        )
        ktctx["error"] = None
    except Exception as exc:
        ktctx["error"] = exc
    return ktctx


@when(parsers.parse('调用 compute code "{code}"'), target_fixture="ktctx")
def when_compute(ktctx, code):
    ktctx["result"] = ktctx["kernel"]._tools["compute"].handler({"code": code})
    return ktctx


@when(parsers.parse('调用 compute code "{code}" symbol "{symbol}" interval "{interval}" mode "{mode}"'), target_fixture="ktctx")
def when_compute_with_selector(ktctx, code, symbol, interval, mode):
    ktctx["result"] = ktctx["kernel"]._tools["compute"].handler({
        "code": code,
        "symbol": symbol,
        "interval": interval,
        "mode": mode,
    })
    return ktctx


@when(parsers.parse('先后调用 compute code "{code}" 选择 "{symbol}" 的 "{first}" 与 "{second}"'), target_fixture="ktctx")
def when_compute_two_selectors(ktctx, code, symbol, first, second):
    first_interval, first_mode = first.split("/")
    second_interval, second_mode = second.split("/")
    tool = ktctx["kernel"]._tools["compute"].handler
    ktctx["results"] = [
        tool({"code": code, "symbol": symbol, "interval": first_interval, "mode": first_mode}),
        tool({"code": code, "symbol": symbol, "interval": second_interval, "mode": second_mode}),
    ]
    return ktctx


@when(parsers.parse('调用 write path "{path}" content "{content}"'), target_fixture="ktctx")
def when_write(ktctx, path, content):
    ktctx["result"] = ktctx["kernel"]._tools["write"].handler({"path": path, "content": content})
    return ktctx


@when(parsers.parse('调用 read path "{path}"'), target_fixture="ktctx")
def when_read(ktctx, path):
    ktctx["result"] = ktctx["kernel"]._tools["read"].handler({"path": path})
    return ktctx


@when(parsers.parse('调用 edit path "{path}" old "{old}" new "{new}"'), target_fixture="ktctx")
def when_edit(ktctx, path, old, new):
    ktctx["result"] = ktctx["kernel"]._tools["edit"].handler(
        {"path": path, "old_string": old, "new_string": new}
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
    kernel.boot(ktctx["workspace"], skill_roots=[])
    ktctx["kernel"] = kernel
    return ktctx


@then("结果包含 data 列表和 total_rows")
def then_has_data_and_total(ktctx):
    result = ktctx["result"]
    assert "data" in result and isinstance(result["data"], list)
    assert "total_rows" in result and result["total_rows"] > 0
    assert result["data_in_result"] is True


@then("结果标记 data 未回显但 total_rows 保留")
def then_data_hidden_with_total(ktctx):
    result = ktctx["result"]
    assert result["data"] == []
    assert result["total_rows"] > 0
    assert result["data_in_result"] is False


@then("结果包含 market 元数据")
def then_has_market_meta(ktctx):
    for key in ("normalized_symbol", "source", "interval", "mode", "timezone", "as_of"):
        assert key in ktctx["result"], f"缺少字段: {key}"


@then("data 每条记录含 date/open/high/low/close/volume")
def then_data_has_ohlcv_fields(ktctx):
    for record in ktctx["result"]["data"]:
        for key in ("date", "open", "high", "low", "close", "volume"):
            assert key in record, f"缺少字段: {key}"


@then(parsers.parse('adapter 收到 interval "{interval}" mode "{mode}" start "{start}" end "{end}"'))
def then_adapter_received_selector(ktctx, interval, mode, start, end):
    log = ktctx["call_log"]
    assert len(log) >= 1
    assert log[-1]["interval"] == interval
    assert log[-1]["mode"] == mode
    assert log[-1]["start"] == start
    assert log[-1]["end"] == end


@then(parsers.parse('DataStore 中存在 "{key}"'))
def then_datastore(ktctx, key):
    assert ktctx["kernel"].data.get(key) is not None


@then("结果 result 为正整数")
def then_positive_int(ktctx):
    assert int(ktctx["result"]["result"]) > 0


@then(parsers.parse('结果 result 等于 {value:d}'))
def then_result_equals(ktctx, value):
    assert int(ktctx["result"]["result"]) == value


@then(parsers.parse('第一次结果 result 等于 {value:d}'))
def then_first_result_equals(ktctx, value):
    assert int(ktctx["results"][0]["result"]) == value


@then(parsers.parse('第二次结果 result 等于 {value:d}'))
def then_second_result_equals(ktctx, value):
    assert int(ktctx["results"][1]["result"]) == value


@then(parsers.parse('捕获到错误包含 "{text}"'))
def then_error_contains(ktctx, text):
    assert text in str(ktctx["error"])


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


@then(parsers.parse('结果中的 error 包含 "{text}"'))
def then_result_error_contains(ktctx, text):
    assert text in ktctx["result"]["error"]


@then("恢复后历史有 4 条消息")
def then_restored_4(ktctx):
    assert len(ktctx["loaded"].history) == 4
    assert ktctx["loaded"].id == "test-persist"


@then("system_prompt 包含自举种子")
def then_has_seed(ktctx):
    from athenaclaw.kernel.seed import SEED_PROMPT

    assert SEED_PROMPT in ktctx["kernel"]._system_prompt


@then(parsers.parse('system_prompt 包含 "{text}"'))
def then_has_text(ktctx, text):
    assert text in ktctx["kernel"]._system_prompt
