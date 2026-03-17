"""
[INPUT]: pytest-bdd, agent.kernel, unittest.mock
[OUTPUT]: skill-reliability.feature step definitions（requires 合约/降级/引用验证）
[POS]: tests/bdd 测试层，验证 skill 可靠性保障机制
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pytest_bdd import given, parsers, scenario, then, when

from athenaclaw.kernel import Kernel, Session


FEATURE = "features/skill-reliability.feature"


@scenario(FEATURE, "缺少 required-tools 的 skill 被标记 degraded")
def test_missing_required_tools(): pass


@scenario(FEATURE, "缺少 required-bins 的 skill 被标记 degraded")
def test_missing_required_bins(): pass


@scenario(FEATURE, "必需依赖齐全的 skill 正常可用")
def test_valid_skill_ready(): pass


@scenario(FEATURE, "degraded skill 被 skill_invoke 调用时返回清晰错误")
def test_degraded_skill_invoke_error(): pass


@scenario(FEATURE, "degraded skill 仍可通过显式命令调用")
def test_degraded_skill_explicit_command(): pass


@scenario(FEATURE, "boot 时 skills.loaded 事件包含降级信息")
def test_degraded_event_emitted(): pass


@scenario(FEATURE, "引用文件不存在时产生 reference_missing 诊断")
def test_reference_missing(): pass


@scenario(FEATURE, "引用文件存在时无 reference_missing 诊断")
def test_reference_exists(): pass


# ── helpers ──────────────────────────────────────────────────────────────

def _mock_response(finish_reason: str, tool_calls=None, content: str = ""):
    msg = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls or [],
    )
    choice = SimpleNamespace(finish_reason=finish_reason, message=msg)
    usage = SimpleNamespace(total_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


# ── steps ────────────────────────────────────────────────────────────────

@given("一个临时 skill 工作区", target_fixture="sctx")
def given_tmp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    return {
        "workspace": workspace,
        "skill_root": skill_root,
        "events": {},
    }


@given(parsers.parse('技能根目录存在需要工具 "{tool}" 的 skill "{name}"'), target_fixture="sctx")
def given_skill_requires_tool(sctx, tool, name):
    skill_dir = sctx["skill_root"] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill with requires.\n"
        f"requires:\n  tools: [{tool}]\n---\n\n# {name}\nBody.\n",
        encoding="utf-8",
    )
    return sctx


@given(parsers.parse('技能根目录存在需要可执行文件 "{binary}" 的 skill "{name}"'), target_fixture="sctx")
def given_skill_requires_bin(sctx, binary, name):
    skill_dir = sctx["skill_root"] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill with bin requirement.\n"
        f"requires:\n  bins: [{binary}]\n---\n\n# {name}\nBody.\n",
        encoding="utf-8",
    )
    return sctx


@given(parsers.parse('技能根目录存在引用 "{ref}" 的 skill "{name}"'), target_fixture="sctx")
def given_skill_with_reference(sctx, ref, name):
    skill_dir = sctx["skill_root"] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill with reference.\n---\n\n"
        f"# {name}\n\nSee [{ref}]({ref}) for details.\n",
        encoding="utf-8",
    )
    return sctx


@given(parsers.parse('引用文件 "{ref}" 实际存在于 "{skill_name}"'), target_fixture="sctx")
def given_reference_file_exists(sctx, ref, skill_name):
    target = sctx["skill_root"] / skill_name / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Reference\nContent here.\n", encoding="utf-8")
    return sctx


@given("Kernel 使用该 skill 根目录启动", target_fixture="sctx")
@when("Kernel 使用该 skill 根目录启动", target_fixture="sctx")
def when_kernel_boot(sctx):
    kernel = Kernel(api_key="test")
    events: dict = sctx["events"]
    kernel.wire("skills.degraded", lambda event, data: events.update({"skills.degraded": data}))
    kernel.boot(
        sctx["workspace"],
        cwd=sctx["workspace"],
        skill_roots=[sctx["skill_root"]],
    )
    sctx["kernel"] = kernel
    sctx["session"] = Session()
    return sctx


@given('LLM 返回 stop 内容 "已执行"', target_fixture="sctx")
def given_llm_stop(sctx):
    sctx["responses"] = [_mock_response("stop", content="已执行")]
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


@then(parsers.parse('诊断包含 "{code}"'))
def then_diagnostics_contain(sctx, code):
    diags = sctx["kernel"]._skill_diagnostics
    codes = [d.get("code") for d in diags]
    assert code in codes, f"期望诊断 code '{code}' 在 {codes} 中"


@then(parsers.parse('诊断不包含 "{code}"'))
def then_diagnostics_not_contain(sctx, code):
    diags = sctx["kernel"]._skill_diagnostics
    codes = [d.get("code") for d in diags]
    assert code not in codes, f"不期望诊断 code '{code}' 在 {codes} 中"


@then(parsers.parse('skill_invoke 结果包含 "{text}"'))
def then_invoke_result_contains(sctx, text):
    payload = json.dumps(sctx["invoke_result"], ensure_ascii=False)
    assert text in payload


@then(parsers.parse('历史用户消息包含 "{text}"'))
def then_last_user_contains(sctx, text):
    needle = text.replace('\\"', '"')
    users = [msg for msg in sctx["session"].history if msg.get("role") == "user"]
    assert users
    assert needle in users[-1]["content"]


@then(parsers.parse('事件 "{event_name}" 已发射'))
def then_event_emitted(sctx, event_name):
    assert event_name in sctx["events"], f"事件 '{event_name}' 未被发射"


@then(parsers.parse('降级事件包含 skill "{name}"'))
def then_degraded_event_has_skill(sctx, name):
    data = sctx["events"].get("skills.degraded", {})
    degraded_names = [d["name"] for d in data.get("degraded", [])]
    assert name in degraded_names, f"降级事件中未找到 '{name}'，实际: {degraded_names}"
