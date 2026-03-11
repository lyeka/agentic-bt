"""
[INPUT]: pytest-bdd, core.subagent, agent.subagents, agent.kernel, unittest.mock
[OUTPUT]: subagent.feature step definitions（Sub-Agent 系统覆盖）
[POS]: tests/ BDD 测试层，验证 subagent 发现/解析/注册/调用/工具隔离/资源管控/生命周期
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pytest_bdd import given, parsers, scenario, then, when

from core.subagent import SubAgentDef, SubAgentResult, filter_schemas, run_subagent, _msg_to_dict
from agent.subagents import (
    SubAgentSystem,
    discover_subagent_files,
    load_subagents,
    parse_subagent_file,
)
from agent.kernel import Kernel, Session
from agent.runtime import _wire_trace


FEATURE = "features/subagent.feature"


# ── Scenario 注册 ────────────────────────────────────────────────────────────

@scenario(FEATURE, "从 subagents 目录发现 md 文件并加载")
def test_discover_md(): pass

@scenario(FEATURE, "frontmatter 缺少 description 时跳过并产生诊断")
def test_missing_description(): pass

@scenario(FEATURE, "名称冲突时保留先加载项并产生诊断")
def test_name_collision(): pass

@scenario(FEATURE, "body 中的 output_protocol 标签被提取为 output_guide")
def test_output_protocol_extraction(): pass

@scenario(FEATURE, "filter_schemas 白名单过滤")
def test_filter_allow(): pass

@scenario(FEATURE, "filter_schemas 黑名单过滤")
def test_filter_block(): pass

@scenario(FEATURE, "filter_schemas 白名单和黑名单同时生效")
def test_filter_both(): pass

@scenario(FEATURE, "委派任务后获得执行结果")
def test_delegate_basic(): pass

@scenario(FEATURE, "子代理使用工具完成任务后返回结果")
def test_delegate_with_tools(): pass

@scenario(FEATURE, "子代理执行轮次耗尽时返回已有结果")
def test_max_rounds_exhaust(): pass

@scenario(FEATURE, "子代理 LLM 调用失败时返回错误信息")
def test_llm_failure(): pass

@scenario(FEATURE, "output_guide 注入子代理 system prompt")
def test_output_guide_injected(): pass

@scenario(FEATURE, "无 output_guide 时 system prompt 不含 output_protocol 标签")
def test_no_output_guide(): pass

@scenario(FEATURE, "返回结果包含质量元数据")
def test_result_metadata(): pass

@scenario(FEATURE, "子代理只能使用白名单内的工具")
def test_tool_allowlist(): pass

@scenario(FEATURE, "子代理无法调用被黑名单禁止的工具")
def test_tool_blocklist(): pass

@scenario(FEATURE, "子代理无法调用 create_subagent 防递归")
def test_block_recursive(): pass

@scenario(FEATURE, "token 超预算时优雅终止并标记 budget_exhausted")
def test_budget_exhausted(): pass

@scenario(FEATURE, "执行超时时返回部分结果并标记 timed_out")
def test_timed_out(): pass

@scenario(FEATURE, "注册子代理后工具列表包含 ask 工具")
def test_register_adds_tool(): pass

@scenario(FEATURE, "移除子代理后工具从列表消失")
def test_remove_drops_tool(): pass

@scenario(FEATURE, "子代理总数超过上限时注册被拒绝")
def test_max_subagents_limit(): pass

@scenario(FEATURE, "注册子代理后 team_prompt 包含描述")
def test_team_prompt(): pass

@scenario(FEATURE, "Kernel boot 后 system prompt 包含 team 描述")
def test_kernel_team_prompt(): pass

@scenario(FEATURE, "从项目目录加载内置 technician 子代理")
def test_builtin_technician(): pass

@scenario(FEATURE, "从项目目录加载内置 researcher 子代理")
def test_builtin_researcher(): pass


# ── Mock 辅助 ────────────────────────────────────────────────────────────────

def _mock_response(finish_reason: str, content: str = "", tool_calls=None, total_tokens: int = 10):
    msg = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls or [],
    )
    choice = SimpleNamespace(finish_reason=finish_reason, message=msg)
    usage = SimpleNamespace(total_tokens=total_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_call(name: str, args: dict, call_id: str = "tc1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _make_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _simple_defn(name: str, description: str = "test agent", **kwargs) -> SubAgentDef:
    return SubAgentDef(
        name=name,
        description=description,
        system_prompt=f"You are {name}.",
        **kwargs,
    )


def _make_system(
    *,
    max_subagents: int = 10,
    mock_client: object | None = None,
) -> SubAgentSystem:
    client = mock_client or MagicMock()
    return SubAgentSystem(
        client=client,
        model="test-model",
        get_tool_schemas=lambda: [_make_schema("read"), _make_schema("write")],
        tool_executor=lambda name, args: {"ok": True, "tool": name},
        emit_fn=MagicMock(),
        max_subagents=max_subagents,
    )


# ── Background ───────────────────────────────────────────────────────────────

@given("一个临时 subagent 工作区", target_fixture="sactx")
def given_tmp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sa_root = tmp_path / "subagents"
    sa_root.mkdir()
    return {
        "tmp_path": tmp_path,
        "workspace": workspace,
        "sa_root": sa_root,
    }


# ── 文件发现 Given/When/Then ─────────────────────────────────────────────────

@given(parsers.parse('subagent 根目录存在定义 "{name}"'), target_fixture="sactx")
def given_subagent_defn(sactx, name):
    root = sactx["sa_root"]
    md = root / f"{name}.md"
    md.write_text(
        f"---\nname: {name}\ndescription: Test subagent {name}\n---\n\n"
        f"You are {name}, a helpful assistant.\n",
        encoding="utf-8",
    )
    return sactx


@given(parsers.parse('subagent 根目录存在无 description 定义 "{name}"'), target_fixture="sactx")
def given_no_desc(sactx, name):
    md = sactx["sa_root"] / f"{name}.md"
    md.write_text(f"---\nname: {name}\n---\n\nBody.\n", encoding="utf-8")
    return sactx


@given(parsers.parse('第二个根目录也存在定义 "{name}"'), target_fixture="sactx")
def given_second_root(sactx, name):
    root2 = sactx["tmp_path"] / "subagents2"
    root2.mkdir(exist_ok=True)
    md = root2 / f"{name}.md"
    md.write_text(
        f"---\nname: {name}\ndescription: Duplicate {name}\n---\n\nDup body.\n",
        encoding="utf-8",
    )
    sactx["sa_root2"] = root2
    return sactx


@given(parsers.parse('subagent 根目录存在带 output_protocol 的定义 "{name}"'), target_fixture="sactx")
def given_with_output_protocol(sactx, name):
    md = sactx["sa_root"] / f"{name}.md"
    md.write_text(
        f"---\nname: {name}\ndescription: Writer agent\n---\n\n"
        f"You are {name}.\n\n"
        f"<output_protocol>\n返回完整文档\n</output_protocol>\n",
        encoding="utf-8",
    )
    return sactx


@when("加载 subagent 文件", target_fixture="sactx")
def when_load(sactx):
    roots = [(sactx["sa_root"], "test")]
    defs, diags = load_subagents(roots)
    sactx["loaded"] = defs
    sactx["diagnostics"] = diags
    return sactx


@when("从两个根目录加载 subagent 文件", target_fixture="sactx")
def when_load_two_roots(sactx):
    roots = [(sactx["sa_root"], "test"), (sactx["sa_root2"], "test2")]
    defs, diags = load_subagents(roots)
    sactx["loaded"] = defs
    sactx["diagnostics"] = diags
    return sactx


@then(parsers.parse('加载结果包含 "{name}"'))
def then_loaded_contains(sactx, name):
    assert name in sactx["loaded"]


@then(parsers.parse('加载结果不包含 "{name}"'))
def then_loaded_not_contains(sactx, name):
    assert name not in sactx["loaded"]


@then("诊断信息为空")
def then_no_diags(sactx):
    assert sactx["diagnostics"] == []


@then(parsers.parse('诊断信息包含 code "{code}"'))
def then_diag_code(sactx, code):
    codes = [d["code"] for d in sactx["diagnostics"]]
    assert code in codes


@then(parsers.parse('"{name}" 的 output_guide 为 "{expected}"'))
def then_output_guide(sactx, name, expected):
    assert sactx["loaded"][name].output_guide == expected


# ── 纯函数 filter_schemas ───────────────────────────────────────────────────

@given(parsers.parse('工具 schemas 包含 {names}'), target_fixture="sactx")
def given_schemas(sactx, names):
    tool_names = [n.strip().strip('"') for n in names.split()]
    sactx["schemas"] = [_make_schema(n) for n in tool_names]
    return sactx


@when(parsers.parse('按白名单 {allowed} 过滤'), target_fixture="sactx")
def when_filter_allow(sactx, allowed):
    allow_list = [n.strip().strip('"') for n in allowed.split()]
    sactx["filtered"] = filter_schemas(sactx["schemas"], allowed=allow_list)
    return sactx


@when(parsers.parse('按黑名单 {blocked} 过滤'), target_fixture="sactx")
def when_filter_block(sactx, blocked):
    block_list = [n.strip().strip('"') for n in blocked.split()]
    sactx["filtered"] = filter_schemas(sactx["schemas"], blocked=block_list)
    return sactx


@when(parsers.parse('按白名单 {allowed} 黑名单 {blocked} 过滤'), target_fixture="sactx")
def when_filter_both(sactx, allowed, blocked):
    allow_list = [n.strip().strip('"') for n in allowed.split()]
    block_list = [n.strip().strip('"') for n in blocked.split()]
    sactx["filtered"] = filter_schemas(sactx["schemas"], allowed=allow_list, blocked=block_list)
    return sactx


@then(parsers.parse('过滤结果仅包含 {names}'))
def then_filtered_only(sactx, names):
    expected = {n.strip().strip('"') for n in names.split()}
    actual = {s["function"]["name"] for s in sactx["filtered"]}
    assert actual == expected


# ── 基础委派 ─────────────────────────────────────────────────────────────────

@given(parsers.parse('一个 mock LLM 返回 "{text}"'), target_fixture="sactx")
def given_mock_llm_stop(sactx, text):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response("stop", content=text)
    sactx["mock_client"] = mock_client
    return sactx


@given(parsers.parse('一个 mock LLM 先调工具再返回 "{text}"'), target_fixture="sactx")
def given_mock_llm_tool_then_stop(sactx, text):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_response(
            "tool_calls",
            tool_calls=[_tool_call("read", {"path": "test.py"})],
        ),
        _mock_response("stop", content=text),
    ]
    sactx["mock_client"] = mock_client
    return sactx


@given("一个 mock LLM 持续调用工具不停止", target_fixture="sactx")
def given_mock_llm_loop(sactx):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response(
        "tool_calls",
        tool_calls=[_tool_call("read", {"path": "x"})],
    )
    sactx["mock_client"] = mock_client
    return sactx


@given("一个 mock LLM 抛出异常", target_fixture="sactx")
def given_mock_llm_fail(sactx):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("API down")
    sactx["mock_client"] = mock_client
    return sactx


@given(parsers.parse('一个注册了 "{name}" 的 SubAgentSystem'), target_fixture="sactx")
def given_system_with_agent(sactx, name):
    system = _make_system(mock_client=sactx["mock_client"])
    system.register(_simple_defn(name))
    sactx["system"] = system
    return sactx


@given(parsers.parse('一个注册了 max_rounds 为 {n:d} 的 "{name}"'), target_fixture="sactx")
def given_system_with_max_rounds(sactx, n, name):
    system = _make_system(mock_client=sactx["mock_client"])
    system.register(_simple_defn(name, max_rounds=n))
    sactx["system"] = system
    return sactx


@when(parsers.parse('调用 "{name}" 执行任务 "{task}"'), target_fixture="sactx")
def when_invoke(sactx, name, task):
    sactx["result"] = sactx["system"].invoke(name, task)
    return sactx


@then(parsers.parse('子代理结果文本包含 "{text}"'))
def then_result_contains(sactx, text):
    assert text in sactx["result"].response


@then(parsers.parse("子代理 metadata 中 tools_used 大于 {n:d}"))
def then_tools_used_gt(sactx, n):
    assert sactx["result"].metadata.get("tools_used", 0) > n


@then(parsers.parse("子代理结果包含 rounds 等于 {n:d}"))
def then_rounds_eq(sactx, n):
    assert sactx["result"].metadata.get("rounds") == n


# ── 通信协议 ─────────────────────────────────────────────────────────────────

@given(parsers.parse('一个带 output_guide 的 SubAgentDef "{name}"'), target_fixture="sactx")
def given_defn_with_guide(sactx, name):
    sactx["defn"] = _simple_defn(name, output_guide="请返回 JSON 格式")
    return sactx


@given(parsers.parse('一个无 output_guide 的 SubAgentDef "{name}"'), target_fixture="sactx")
def given_defn_no_guide(sactx, name):
    sactx["defn"] = _simple_defn(name)
    return sactx


@given("一个捕获 LLM 调用的 mock", target_fixture="sactx")
def given_capture_mock(sactx):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response("stop", content="done")
    sactx["mock_client"] = mock_client
    return sactx


@when(parsers.parse('通过 run_subagent 执行 "{name}"'), target_fixture="sactx")
def when_run_subagent(sactx, name):
    result = run_subagent(
        definition=sactx["defn"],
        task="test task",
        client=sactx["mock_client"],
        model="test-model",
        tool_schemas=[],
        tool_executor=lambda n, a: {"ok": True},
    )
    sactx["result"] = result
    return sactx


@then(parsers.parse('LLM 收到的 system prompt 包含 "{text}"'))
def then_llm_system_contains(sactx, text):
    call_args = sactx["mock_client"].chat.completions.create.call_args
    messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
    system_msg = messages[0]["content"]
    assert text in system_msg


@then(parsers.parse('LLM 收到的 system prompt 不包含 "{text}"'))
def then_llm_system_not_contains(sactx, text):
    call_args = sactx["mock_client"].chat.completions.create.call_args
    messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
    system_msg = messages[0]["content"]
    assert text not in system_msg


@then(parsers.parse('子代理结果 metadata 包含 "{key}"'))
def then_metadata_has_key(sactx, key):
    assert key in sactx["result"].metadata


# ── 工具隔离 ─────────────────────────────────────────────────────────────────

@given(parsers.parse('父级工具集包含 {names}'), target_fixture="sactx")
def given_parent_tools(sactx, names):
    tool_names = [n.strip().strip('"') for n in names.split()]
    sactx["parent_schemas"] = [_make_schema(n) for n in tool_names]
    return sactx


@given(parsers.parse('SubAgentDef 白名单为 {names}'), target_fixture="sactx")
def given_defn_allowlist(sactx, names):
    allow_list = [n.strip().strip('"') for n in names.split()]
    sactx["defn"] = _simple_defn("test", tools=allow_list)
    return sactx


@given(parsers.parse('SubAgentDef 黑名单为 {names}'), target_fixture="sactx")
def given_defn_blocklist(sactx, names):
    block_list = [n.strip().strip('"') for n in names.split()]
    sactx["defn"] = _simple_defn("test", blocked_tools=block_list)
    return sactx


@given("SubAgentDef 未设置工具过滤", target_fixture="sactx")
def given_defn_no_filter(sactx):
    sactx["defn"] = _simple_defn("test")
    return sactx


@when("生成子代理工具 schemas", target_fixture="sactx")
def when_gen_schemas(sactx):
    defn = sactx["defn"]
    sactx["filtered"] = filter_schemas(
        sactx["parent_schemas"],
        allowed=defn.tools,
        blocked=defn.blocked_tools,
    )
    return sactx


@then(parsers.parse('子代理工具仅包含 {names}'))
def then_tools_only(sactx, names):
    expected = {n.strip().strip('"') for n in names.split()}
    actual = {s["function"]["name"] for s in sactx["filtered"]}
    assert actual == expected


@then(parsers.parse('子代理工具不包含 "{name}"'))
def then_tools_not_contain(sactx, name):
    actual = {s["function"]["name"] for s in sactx["filtered"]}
    assert name not in actual


# ── 资源管控 ─────────────────────────────────────────────────────────────────

@given(parsers.parse("一个 mock LLM 每次消耗 {n:d} tokens"), target_fixture="sactx")
def given_mock_high_tokens(sactx, n):
    mock_client = MagicMock()
    # 两轮都用工具，第二轮超预算
    mock_client.chat.completions.create.return_value = _mock_response(
        "tool_calls", tool_calls=[_tool_call("read", {})], total_tokens=n,
    )
    sactx["mock_client"] = mock_client
    return sactx


@given(parsers.parse("SubAgentDef token_budget 为 {n:d}"), target_fixture="sactx")
def given_defn_budget(sactx, n):
    sactx["defn"] = _simple_defn("budget_test", token_budget=n)
    return sactx


@given(parsers.parse("一个 mock LLM 每次延迟 {n:d} 秒"), target_fixture="sactx")
def given_mock_slow(sactx, n):
    mock_client = MagicMock()
    def slow_call(**kwargs):
        time.sleep(n)
        return _mock_response("tool_calls", tool_calls=[_tool_call("read", {})])
    mock_client.chat.completions.create.side_effect = slow_call
    sactx["mock_client"] = mock_client
    return sactx


@given(parsers.parse("SubAgentDef timeout_seconds 为 {n:d}"), target_fixture="sactx")
def given_defn_timeout(sactx, n):
    sactx["defn"] = _simple_defn("timeout_test", timeout_seconds=n)
    return sactx


@when("通过 run_subagent 执行", target_fixture="sactx")
def when_run_subagent_plain(sactx):
    result = run_subagent(
        definition=sactx["defn"],
        task="test",
        client=sactx["mock_client"],
        model="test-model",
        tool_schemas=[_make_schema("read")],
        tool_executor=lambda n, a: {"ok": True},
    )
    sactx["result"] = result
    return sactx


@then(parsers.parse("子代理结果 metadata budget_exhausted 为 true"))
def then_budget_exhausted(sactx):
    assert sactx["result"].metadata.get("budget_exhausted") is True


@then(parsers.parse("子代理结果 metadata timed_out 为 true"))
def then_timed_out(sactx):
    assert sactx["result"].metadata.get("timed_out") is True


# ── 生命周期管理 ─────────────────────────────────────────────────────────────

@given("一个空的 SubAgentSystem", target_fixture="sactx")
def given_empty_system(sactx):
    sactx["system"] = _make_system()
    return sactx


@given(parsers.parse('一个 max_subagents 为 {n:d} 的 SubAgentSystem'), target_fixture="sactx")
def given_limited_system(sactx, n):
    sactx["system"] = _make_system(max_subagents=n)
    return sactx


@given(parsers.parse('已注册 SubAgentDef "{name}"'), target_fixture="sactx")
def given_registered(sactx, name):
    sactx["system"].register(_simple_defn(name))
    return sactx


@when(parsers.parse('注册 SubAgentDef "{name}"'), target_fixture="sactx")
def when_register(sactx, name):
    sactx["register_error"] = sactx["system"].register(_simple_defn(name))
    return sactx


@when(parsers.parse('注册 SubAgentDef "{name}" 描述 "{desc}"'), target_fixture="sactx")
def when_register_with_desc(sactx, name, desc):
    sactx["system"].register(_simple_defn(name, description=desc))
    return sactx


@when(parsers.parse('移除 "{name}"'), target_fixture="sactx")
def when_remove(sactx, name):
    sactx["system"].remove(name)
    return sactx


@when(parsers.parse('尝试注册 SubAgentDef "{name}"'), target_fixture="sactx")
def when_try_register(sactx, name):
    sactx["register_error"] = sactx["system"].register(_simple_defn(name))
    return sactx


@then(parsers.parse('as_tool_defs 包含 "{name}"'))
def then_tool_defs_contain(sactx, name):
    assert name in sactx["system"].as_tool_defs()


@then(parsers.parse('as_tool_defs 不包含 "{name}"'))
def then_tool_defs_not_contain(sactx, name):
    assert name not in sactx["system"].as_tool_defs()


@then("注册结果包含错误")
def then_register_error(sactx):
    assert sactx["register_error"] is not None
    assert "error" in sactx["register_error"]


@then(parsers.parse('team_prompt 包含 "{text}"'))
def then_team_contains(sactx, text):
    assert text in sactx["system"].team_prompt()


# ── Kernel 集成 ──────────────────────────────────────────────────────────────

@when("Kernel 使用该 subagent 根目录启动", target_fixture="sactx")
def when_kernel_boot_with_subagent_root(sactx):
    kernel = Kernel(api_key="test")
    kernel.boot(
        sactx["workspace"],
        cwd=sactx["workspace"],
        subagent_roots=[sactx["sa_root"]],
    )
    sactx["kernel"] = kernel
    return sactx


@then(parsers.parse('kernel system prompt 包含 "{text}"'))
def then_kernel_prompt_contains(sactx, text):
    assert text in sactx["kernel"]._system_prompt


# ── 内置子代理 ──────────────────────────────────────────────────────────────

_PROJECT_SUBAGENT_DIR = Path(__file__).resolve().parent.parent / ".agents" / "subagents"


@given(parsers.parse('项目 subagent 目录包含 "{name}" 定义文件'), target_fixture="sactx")
def given_builtin_subagent(sactx, name):
    md = _PROJECT_SUBAGENT_DIR / f"{name}.md"
    assert md.exists(), f"内置子代理文件不存在: {md}"
    sactx["sa_root"] = _PROJECT_SUBAGENT_DIR
    return sactx


@when("加载项目 subagent 文件", target_fixture="sactx")
def when_load_project(sactx):
    roots = [(sactx["sa_root"], "project")]
    defs, diags = load_subagents(roots)
    sactx["loaded"] = defs
    sactx["diagnostics"] = diags
    return sactx


@then(parsers.parse('"{name}" 的工具白名单为 "{t1}" 和 "{t2}"'))
def then_tools_whitelist(sactx, name, t1, t2):
    defn = sactx["loaded"][name]
    assert defn.tools is not None
    assert set(defn.tools) == {t1, t2}


@then(parsers.parse('"{name}" 的 token_budget 为 {n:d}'))
def then_token_budget(sactx, name, n):
    assert sactx["loaded"][name].token_budget == n


def test_builtin_technician_prompt_teaches_compute_contract():
    defs, _ = load_subagents([(_PROJECT_SUBAGENT_DIR, "project")])
    technician = defs["technician"]

    assert "there is no `data` variable" in technician.system_prompt
    assert "Never use `close[-1]` or `date[-1]`" in technician.system_prompt
    assert "already return latest scalar tuples" in technician.system_prompt
    assert "Variables created in one call do not survive into the next call" in technician.system_prompt


def test_run_subagent_emits_namespaced_lifecycle_events_with_shared_run_id():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_response("tool_calls", tool_calls=[_tool_call("read", {"path": "x.py"})], total_tokens=11),
        _mock_response("stop", content="done", total_tokens=7),
    ]
    events: list[tuple[str, dict]] = []

    result = run_subagent(
        definition=_simple_defn("tracey"),
        task="inspect",
        client=mock_client,
        model="test-model",
        tool_schemas=[_make_schema("read")],
        tool_executor=lambda n, a: {"ok": True, "tool": n},
        emit_fn=lambda event, data: events.append((event, data)),
    )

    event_names = [event for event, _data in events]
    assert "subagent.start" in event_names
    assert "subagent.llm.call.start" in event_names
    assert "subagent.llm.call.done" in event_names
    assert "subagent.tool.call.start" in event_names
    assert "subagent.tool.call.done" in event_names
    assert "subagent.done" in event_names

    run_ids = {
        data["run_id"]
        for _event, data in events
        if isinstance(data, dict) and "run_id" in data
    }
    assert len(run_ids) == 1
    assert result.metadata["run_id"] in run_ids


def test_wire_trace_captures_subagent_events(tmp_path):
    kernel = Kernel(api_key="test")
    trace_path = tmp_path / "trace.jsonl"

    _wire_trace(kernel, trace_path)
    kernel.emit("subagent.start", {"name": "helper", "run_id": "run-1"})

    content = trace_path.read_text(encoding="utf-8")
    assert '"event": "subagent.start"' in content


def test_ask_handler_returns_subagent_run_id():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response("stop", content="ok")
    system = _make_system(mock_client=mock_client)
    system.register(_simple_defn("helper"))

    result = system.as_tool_defs()["ask_helper"]["handler"]({"task": "do it"})

    assert result["run_id"]
    assert result["metadata"]["run_id"] == result["run_id"]


def test_subagent_msg_to_dict_preserves_reasoning_content():
    msg = SimpleNamespace(
        role="assistant",
        content=None,
        tool_calls=[_tool_call("read", {"path": "x.py"})],
        reasoning_content="step-by-step",
        model_extra=None,
    )

    result = _msg_to_dict(msg)

    assert result["reasoning_content"] == "step-by-step"


def test_run_subagent_emits_llm_call_error_details_after_retries():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("provider 400")
    events: list[tuple[str, dict]] = []

    result = run_subagent(
        definition=_simple_defn("tracey"),
        task="inspect",
        client=mock_client,
        model="test-model",
        tool_schemas=[],
        tool_executor=lambda n, a: {"ok": True},
        emit_fn=lambda event, data: events.append((event, data)),
    )

    error_events = [data for event, data in events if event == "subagent.llm.call.error"]
    assert len(error_events) == 3
    assert all(evt["error_type"] == "RuntimeError" for evt in error_events)
    assert all("provider 400" in evt["error"] for evt in error_events)
    assert result.response == "[error] LLM 调用失败"
