"""
[INPUT]: pytest-bdd, agent.kernel, shutil
[OUTPUT]: skill-lifecycle.feature step definitions（reload 热重载验证）
[POS]: tests/bdd 测试层，验证 skill 生命周期管理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import shutil

from pytest_bdd import given, parsers, scenario, then, when

from athenaclaw.kernel import Kernel, Session


FEATURE = "features/skill-lifecycle.feature"


@scenario(FEATURE, "reload_skills 工具重新扫描并更新 system prompt")
def test_reload_adds_new_skill(): pass


@scenario(FEATURE, "删除 skill 文件后 reload 移除")
def test_reload_removes_deleted_skill(): pass


@scenario(FEATURE, "reload 后新 skill 降级检查仍然生效")
def test_reload_validates_new_skill(): pass


# ── steps ────────────────────────────────────────────────────────────────

@given("一个临时 skill 工作区", target_fixture="sctx")
def given_tmp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    return {"workspace": workspace, "skill_root": skill_root}


def _write_skill(skill_root, name, extra_frontmatter=""):
    skill_dir = skill_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Skill {name}.\n{extra_frontmatter}---\n\n# {name}\nBody.\n",
        encoding="utf-8",
    )


@given(parsers.parse('技能根目录存在 skill "{name}"'), target_fixture="sctx")
def given_skill_exists(sctx, name):
    _write_skill(sctx["skill_root"], name)
    return sctx


@given("Kernel 使用该 skill 根目录启动", target_fixture="sctx")
def given_kernel_boot(sctx):
    kernel = Kernel(api_key="test")
    kernel.boot(
        sctx["workspace"],
        cwd=sctx["workspace"],
        skill_roots=[sctx["skill_root"]],
    )
    sctx["kernel"] = kernel
    sctx["session"] = Session()
    return sctx


@given(parsers.parse('技能根目录新增 skill "{name}"'), target_fixture="sctx")
def given_add_new_skill(sctx, name):
    _write_skill(sctx["skill_root"], name)
    return sctx


@given(parsers.parse('技能根目录新增需要工具 "{tool}" 的 skill "{name}"'), target_fixture="sctx")
def given_add_new_degraded_skill(sctx, tool, name):
    _write_skill(sctx["skill_root"], name, f"requires:\n  tools: [{tool}]\n")
    return sctx


@given(parsers.parse('技能根目录删除 skill "{name}"'), target_fixture="sctx")
def given_delete_skill(sctx, name):
    skill_dir = sctx["skill_root"] / name
    shutil.rmtree(skill_dir, ignore_errors=True)
    return sctx


@when("调用 reload_skills 工具", target_fixture="sctx")
def when_reload_skills(sctx):
    sctx["reload_result"] = sctx["kernel"]._tools["reload_skills"].handler({})
    return sctx


@then(parsers.parse('system prompt 包含 "{text}"'))
def then_prompt_contains(sctx, text):
    assert text in sctx["kernel"]._system_prompt


@then(parsers.parse('system prompt 不包含 "{text}"'))
def then_prompt_not_contains(sctx, text):
    assert text not in sctx["kernel"]._system_prompt


@then(parsers.parse('reload 结果包含新增 "{name}"'))
def then_reload_added(sctx, name):
    assert name in sctx["reload_result"]["added"]


@then(parsers.parse('reload 结果包含移除 "{name}"'))
def then_reload_removed(sctx, name):
    assert name in sctx["reload_result"]["removed"]
