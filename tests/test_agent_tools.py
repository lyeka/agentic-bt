"""
[INPUT]: pytest-bdd, agent.tools.primitives, agent.tools.bash, agent.tools._truncate
[OUTPUT]: agent_tools.feature 的 step definitions
[POS]: 测试 read/write/edit/bash 工具的完整行为 + 路径安全
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenario, then, when


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 注册
# ─────────────────────────────────────────────────────────────────────────────

# read
@scenario("features/agent_tools.feature", "read 读取文件带行号")
def test_read_with_line_numbers(): pass

@scenario("features/agent_tools.feature", "read 分页 offset/limit")
def test_read_pagination(): pass

@scenario("features/agent_tools.feature", "read 大文件截断")
def test_read_truncation(): pass

@scenario("features/agent_tools.feature", "read 目录列表")
def test_read_directory(): pass

@scenario("features/agent_tools.feature", "read 二进制文件拒绝")
def test_read_binary(): pass

@scenario("features/agent_tools.feature", "read 文件不存在")
def test_read_not_found(): pass

# edit
@scenario("features/agent_tools.feature", "edit 精确替换并返回 diff")
def test_edit_with_diff(): pass

@scenario("features/agent_tools.feature", "edit 模糊匹配（行尾空白）")
def test_edit_fuzzy(): pass

@scenario("features/agent_tools.feature", "edit 唯一性检查")
def test_edit_uniqueness(): pass

@scenario("features/agent_tools.feature", "edit 未找到匹配")
def test_edit_not_found(): pass

# write
@scenario("features/agent_tools.feature", "write 创建文件并返回字节数")
def test_write_bytes(): pass

@scenario("features/agent_tools.feature", "write 自动创建目录")
def test_write_mkdir(): pass

# bash
@scenario("features/agent_tools.feature", "bash 执行简单命令")
def test_bash_simple(): pass

@scenario("features/agent_tools.feature", "bash 非零退出码")
def test_bash_nonzero(): pass

@scenario("features/agent_tools.feature", "bash 超时")
def test_bash_timeout(): pass

@scenario("features/agent_tools.feature", "bash 大输出截断")
def test_bash_truncation(): pass

# 路径安全
@scenario("features/agent_tools.feature", "信任区域内文件可直接操作")
def test_trusted_zone(): pass

@scenario("features/agent_tools.feature", "信任区域外文件需要确认")
def test_untrusted_zone(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Mock Kernel
# ─────────────────────────────────────────────────────────────────────────────

class _MockKernel:
    """最小 Kernel mock — 只实现工具注册和权限"""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        self._permissions: dict = {}
        self._confirm_result: bool = True

    def tool(self, name: str, description: str, parameters: dict, handler) -> None:
        self._tools[name] = {"handler": handler, "desc": description}

    def permission(self, pattern: str, level) -> None:
        from fnmatch import fnmatch
        self._permissions[pattern] = level

    def check_permission(self, path: str):
        from fnmatch import fnmatch
        from agent.kernel import Permission
        for pattern, level in self._permissions.items():
            if fnmatch(path, pattern):
                return level
        return Permission.FREE

    def request_confirm(self, path: str) -> bool:
        return self._confirm_result

    def emit(self, event: str, data=None) -> None:
        pass

    def call(self, name: str, args: dict) -> dict:
        return self._tools[name]["handler"](args)


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个临时工作区", target_fixture="atx")
def given_workspace(tmp_path):
    kernel = _MockKernel()
    from agent.kernel import Permission
    kernel.permission("__external__", Permission.USER_CONFIRM)

    from agent.tools.read import register as reg_read
    from agent.tools.write import register as reg_write
    from agent.tools.edit import register as reg_edit
    from agent.tools.bash import register as reg_bash
    reg_read(kernel, tmp_path, cwd=tmp_path)
    reg_write(kernel, tmp_path, cwd=tmp_path)
    reg_edit(kernel, tmp_path, cwd=tmp_path)
    reg_bash(kernel, cwd=tmp_path)

    return {"kernel": kernel, "workspace": tmp_path, "result": None}


@given(parsers.parse('工作区文件 "{name}" 内容为 "{content}"'), target_fixture="atx")
def given_file(atx, name, content):
    path = atx["workspace"] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # 处理转义换行
    path.write_text(content.replace("\\n", "\n"), encoding="utf-8")
    return atx


@given(parsers.parse("工作区文件 \"{name}\" 内容为 {n:d} 行"), target_fixture="atx")
def given_file_n_lines(atx, name, n):
    path = atx["workspace"] / name
    lines = [f"line{i+1}" for i in range(n)]
    path.write_text("\n".join(lines), encoding="utf-8")
    return atx


@given(parsers.parse('工作区目录 "{dirname}" 含文件 "{f1}" 和 "{f2}"'), target_fixture="atx")
def given_dir(atx, dirname, f1, f2):
    d = atx["workspace"] / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / f1).write_text("", encoding="utf-8")
    (d / f2).write_text("", encoding="utf-8")
    return atx


@given(parsers.parse('工作区二进制文件 "{name}"'), target_fixture="atx")
def given_binary(atx, name):
    path = atx["workspace"] / name
    path.write_bytes(b"\x00\x01\x02\xff")
    return atx


@given("确认回调返回拒绝", target_fixture="atx")
def given_deny_confirm(atx):
    atx["kernel"]._confirm_result = False
    return atx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('调用 read 工具 path="{path}"'), target_fixture="atx")
def when_read(atx, path):
    atx["result"] = atx["kernel"].call("read", {"path": path})
    return atx


@when(parsers.parse('调用 read 工具 path="{path}" offset={offset:d} limit={limit:d}'), target_fixture="atx")
def when_read_paged(atx, path, offset, limit):
    atx["result"] = atx["kernel"].call("read", {"path": path, "offset": offset, "limit": limit})
    return atx


@when(parsers.parse('调用 edit 工具 path="{path}" old="{old}" new="{new}"'), target_fixture="atx")
def when_edit(atx, path, old, new):
    atx["result"] = atx["kernel"].call("edit", {"path": path, "old_string": old, "new_string": new})
    return atx


@when(parsers.parse('调用 write 工具 path="{path}" content="{content}"'), target_fixture="atx")
def when_write(atx, path, content):
    atx["result"] = atx["kernel"].call("write", {"path": path, "content": content})
    return atx


@when(parsers.parse('调用 bash 工具 command="{command}"'), target_fixture="atx")
def when_bash(atx, command):
    atx["result"] = atx["kernel"].call("bash", {"command": command})
    return atx


@when(parsers.parse('调用 bash 工具 command="{command}" timeout={timeout:d}'), target_fixture="atx")
def when_bash_timeout(atx, command, timeout):
    atx["result"] = atx["kernel"].call("bash", {"command": command, "timeout": timeout})
    return atx


@when("调用 bash 工具 command 输出 3000 行", target_fixture="atx")
def when_bash_big_output(atx):
    cmd = "for i in $(seq 1 3000); do echo line$i; done"
    atx["result"] = atx["kernel"].call("bash", {"command": cmd})
    return atx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('返回 content 包含 "{text}"'))
def then_content_contains(atx, text):
    assert text in atx["result"]["content"]


@then(parsers.parse("返回 total_lines 为 {n:d}"))
def then_total_lines(atx, n):
    assert atx["result"]["total_lines"] == n


@then(parsers.parse('返回 content 首行为 "{text}"'))
def then_content_first_line(atx, text):
    first = atx["result"]["content"].split("\n")[0]
    assert first == text


@then(parsers.parse("返回 content 共 {n:d} 行"))
def then_content_line_count(atx, n):
    lines = atx["result"]["content"].strip().split("\n")
    assert len(lines) == n


@then("返回 truncated 为 true")
def then_truncated(atx):
    assert atx["result"].get("truncated") is True


@then("返回 next_offset 存在")
def then_next_offset(atx):
    assert "next_offset" in atx["result"]


@then(parsers.parse('返回 entries 包含 "{f1}" 和 "{f2}"'))
def then_entries(atx, f1, f2):
    entries = atx["result"]["entries"]
    assert f1 in entries
    assert f2 in entries


@then(parsers.parse('返回 error 包含 "{text}"'))
def then_error_contains(atx, text):
    assert text in atx["result"]["error"]


@then(parsers.parse('返回 status 为 "{status}"'))
def then_status(atx, status):
    assert atx["result"]["status"] == status


@then(parsers.parse('返回 diff 包含 "{text}"'))
def then_diff_contains(atx, text):
    assert text in atx["result"]["diff"]


@then(parsers.parse("返回 first_changed_line 为 {n:d}"))
def then_first_changed(atx, n):
    assert atx["result"]["first_changed_line"] == n


@then("返回 bytes_written 大于 0")
def then_bytes_written(atx):
    assert atx["result"]["bytes_written"] > 0


@then(parsers.parse('工作区文件 "{name}" 存在'))
def then_file_exists(atx, name):
    assert (atx["workspace"] / name).exists()


@then(parsers.parse("返回 exit_code 为 {code:d}"))
def then_exit_code(atx, code):
    assert atx["result"]["exit_code"] == code


@then(parsers.parse('返回 output 包含 "{text}"'))
def then_output_contains(atx, text):
    assert text in atx["result"]["output"]
