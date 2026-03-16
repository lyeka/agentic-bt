"""
[INPUT]: pytest-bdd, agent.kernel, unittest.mock
[OUTPUT]: skills.feature step definitions（Skill Engine 覆盖）
[POS]: tests/ BDD 测试层，验证 skills 发现/注入/显式展开/模型自主调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pytest_bdd import given, parsers, scenario, then, when

from athenaclaw.kernel import Kernel, Session


FEATURE = "features/skills.feature"


@scenario(FEATURE, "boot 注入 available_skills XML")
def test_boot_injects_available_skills(): pass


@scenario(FEATURE, "未注册 read 也能注入技能摘要")
def test_boot_without_read_still_injects(): pass


@scenario(FEATURE, "显式命令 /skill:name 会展开正文")
def test_explicit_command_expands_skill(): pass


@scenario(FEATURE, "未知 skill 显式命令直接报错且不调用 LLM")
def test_unknown_explicit_skill(): pass


@scenario(FEATURE, "disable-model-invocation 仅隐藏自动路由")
def test_disable_model_invocation(): pass


@scenario(FEATURE, "模型可像调用内置工具一样调用 skill_invoke")
def test_autonomous_skill_invoke(): pass


def _mock_response(finish_reason: str, tool_calls=None, content: str = ""):
    msg = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls or [],
    )
    choice = SimpleNamespace(finish_reason=finish_reason, message=msg)
    usage = SimpleNamespace(total_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


def _tool_call(name: str, args: dict, call_id: str = "tc1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


@given("一个临时 skill 工作区", target_fixture="sctx")
def given_tmp_skill_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    return {
        "workspace": workspace,
        "skill_root": skill_root,
    }


@given(parsers.parse('技能根目录存在 skill "{name}"'), target_fixture="sctx")
def given_skill_dir(sctx, name):
    skill_dir = sctx["skill_root"] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            "description: Test skill for BDD checks.\n"
            "---\n\n"
            f"# {name}\n\n"
            "Step A\n"
        ),
        encoding="utf-8",
    )
    return sctx


@given(parsers.parse('技能根目录存在隐藏 skill "{name}"'), target_fixture="sctx")
def given_hidden_skill(sctx, name):
    skill_dir = sctx["skill_root"] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            "description: Hidden skill.\n"
            "disable-model-invocation: true\n"
            "---\n\n"
            "# Hidden\n\n"
            "Only explicit command can load this.\n"
        ),
        encoding="utf-8",
    )
    return sctx


@given("Kernel 使用该 skill 根目录启动", target_fixture="sctx")
@when("Kernel 使用该 skill 根目录启动", target_fixture="sctx")
def given_kernel_boot_with_skill_root(sctx):
    kernel = Kernel(api_key="test")
    kernel.boot(
        sctx["workspace"],
        cwd=sctx["workspace"],
        skill_roots=[sctx["skill_root"]],
    )
    sctx["kernel"] = kernel
    sctx["session"] = Session()
    return sctx


@given("LLM 返回 stop 内容 \"已执行\"", target_fixture="sctx")
def given_llm_stop_executed(sctx):
    sctx["responses"] = [_mock_response("stop", content="已执行")]
    return sctx


@given("LLM 先调用 skill_invoke 再 stop", target_fixture="sctx")
def given_llm_skill_invoke_then_stop(sctx):
    sctx["responses"] = [
        _mock_response(
            "tool_calls",
            [_tool_call("skill_invoke", {"name": "alpha", "args": "请处理"})],
        ),
        _mock_response("stop", content="完成 skill"),
    ]
    return sctx


@when("Kernel 在无 read 工具时启动", target_fixture="sctx")
def when_kernel_boot_without_read(sctx):
    kernel = Kernel(api_key="test")
    kernel.boot(
        sctx["workspace"],
        cwd=sctx["workspace"],
        skill_roots=[sctx["skill_root"]],
    )
    sctx["kernel"] = kernel
    sctx["session"] = Session()
    return sctx


@when(parsers.parse('用户发送 "{text}"'), target_fixture="sctx")
def when_user_send(sctx, text):
    kernel = sctx["kernel"]
    session = sctx["session"]

    responses = sctx.get("responses")
    if responses:
        resp_iter = iter(responses)
        mock_create = MagicMock(side_effect=lambda **_: next(resp_iter))
    else:
        mock_create = MagicMock(return_value=_mock_response("stop", content="unused"))

    with patch.object(kernel.client.chat.completions, "create", mock_create):
        sctx["reply"] = kernel.turn(text, session)
    sctx["llm_calls"] = mock_create.call_count
    return sctx


@when(parsers.parse('调用 skill_invoke 名称 "{name}"'), target_fixture="sctx")
def when_call_skill_invoke(sctx, name):
    sctx["invoke_result"] = sctx["kernel"]._tools["skill_invoke"].handler({"name": name})
    return sctx


@then(parsers.parse('system prompt 包含 "{text}"'))
def then_prompt_contains(sctx, text):
    assert text in sctx["kernel"]._system_prompt


@then(parsers.parse('system prompt 不包含 "{text}"'))
def then_prompt_not_contains(sctx, text):
    assert text not in sctx["kernel"]._system_prompt


@then(parsers.parse('历史用户消息包含 "{text}"'))
def then_last_user_contains(sctx, text):
    needle = text.replace('\\"', '"')
    users = [msg for msg in sctx["session"].history if msg.get("role") == "user"]
    assert users
    assert needle in users[-1]["content"]


@then(parsers.parse('回复为 "{text}"'))
def then_reply_equals(sctx, text):
    assert sctx["reply"] == text


@then(parsers.parse('回复包含 "{text}"'))
def then_reply_contains(sctx, text):
    assert text in sctx["reply"]


@then(parsers.parse('LLM 调用次数为 {n:d}'))
def then_llm_calls(sctx, n):
    assert sctx.get("llm_calls", 0) == n


@then(parsers.parse('skill_invoke 结果包含 "{text}"'))
def then_invoke_result_contains(sctx, text):
    payload = json.dumps(sctx["invoke_result"], ensure_ascii=False)
    assert text in payload


@then(parsers.parse('工具响应包含 "{text}"'))
def then_tool_response_contains(sctx, text):
    needle = text.replace('\\"', '"')
    tools = [msg for msg in sctx["session"].history if msg.get("role") == "tool"]
    assert tools
    assert any(needle in msg["content"] for msg in tools)
