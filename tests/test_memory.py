"""
[INPUT]: pytest-bdd, agenticbt.memory
[OUTPUT]: memory.feature 的 step definitions
[POS]: tests/ BDD 测试层，验证 Memory 文件隔离与 CRUD 行为
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from datetime import date

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from agenticbt.memory import Memory, Workspace


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/memory.feature", "工作空间隔离")
def test_workspace_isolation(): pass

@scenario("features/memory.feature", "Playbook 初始化")
def test_playbook_init(): pass

@scenario("features/memory.feature", "日志追加")
def test_journal_append(): pass

@scenario("features/memory.feature", "笔记创建和覆盖")
def test_note_create_overwrite(): pass

@scenario("features/memory.feature", "持仓笔记条件读取")
def test_position_notes(): pass

@scenario("features/memory.feature", "关键词召回")
def test_recall(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个新工作空间", target_fixture="mctx")
def given_workspace():
    ws = Workspace()
    mem = Memory(ws, current_date=date(2024, 1, 1))
    return {"ws": ws, "mem": mem}


@given(parsers.parse('笔记 "{key}" 内容 "{content}"'), target_fixture="mctx")
def given_note(mctx, key, content):
    mctx["mem"].note(key, content)
    return mctx


@given(parsers.parse('日志 "{log_date}" 内容 "{content}"'), target_fixture="mctx")
def given_journal(mctx, log_date, content):
    d = date.fromisoformat(log_date)
    mctx["mem"].log(content, log_date=d)
    return mctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("创建两个工作空间", target_fixture="mctx")
def when_two_workspaces():
    ws1 = Workspace()
    ws2 = Workspace()
    return {"ws1": ws1, "ws2": ws2}


@when(parsers.parse('用策略描述 "{desc}" 初始化 playbook'), target_fixture="mctx")
def when_init_playbook(mctx, desc):
    mctx["mem"].init_playbook(desc)
    return mctx


@when(parsers.parse('记录日志 "{content}" 日期 "{log_date}"'), target_fixture="mctx")
def when_log(mctx, content, log_date):
    d = date.fromisoformat(log_date)
    mctx["mem"].log(content, log_date=d)
    mctx.setdefault("log_date", log_date)
    mctx.setdefault("log_count", 0)
    mctx["log_count"] += 1
    return mctx


@when(parsers.parse('创建笔记 key="{key}" content="{content}"'), target_fixture="mctx")
def when_create_note(mctx, key, content):
    mctx["mem"].note(key, content)
    mctx["last_key"] = key
    mctx["last_content"] = content
    return mctx


@when(parsers.parse('更新笔记 key="{key}" content="{content}"'), target_fixture="mctx")
def when_update_note(mctx, key, content):
    mctx["mem"].note(key, content)
    mctx["last_key"] = key
    mctx["last_content"] = content
    return mctx


@when('读取持仓笔记 持仓列表 ["AAPL"]', target_fixture="mctx")
def when_read_position_notes(mctx):
    mctx["position_notes"] = mctx["mem"].read_position_notes(["AAPL"])
    return mctx


@when(parsers.parse('召回 "{query}"'), target_fixture="mctx")
def when_recall(mctx, query):
    mctx["recall_results"] = mctx["mem"].recall(query)
    return mctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("两个工作空间路径不同")
def then_different_paths(mctx):
    assert mctx["ws1"].path != mctx["ws2"].path


@then("各自包含独立的目录结构")
def then_separate_dirs(mctx):
    import os
    assert os.path.isdir(mctx["ws1"].path)
    assert os.path.isdir(mctx["ws2"].path)


@then(parsers.parse('playbook.md 应包含 "{text}"'))
def then_playbook_contains(mctx, text):
    content = mctx["mem"].read_playbook()
    assert text in content


@then(parsers.parse('journal/{log_date}.md 应包含两条记录'))
def then_journal_two_entries(mctx, log_date):
    import os
    journal_path = os.path.join(mctx["ws"].path, "journal", f"{log_date}.md")
    text = open(journal_path, encoding="utf-8").read()
    # 两条 "- " 条目
    entries = [line for line in text.splitlines() if line.strip().startswith("-")]
    assert len(entries) >= 2


@then(parsers.parse('notes/{key}.md 内容为 "{expected}"'))
def then_note_content(mctx, key, expected):
    note = mctx["mem"].read_note(key)
    assert note == expected


@then("应返回 AAPL 的笔记")
def then_has_aapl(mctx):
    assert "AAPL" in mctx["position_notes"]


@then("不应返回 GOOGL 的笔记")
def then_no_googl(mctx):
    assert "GOOGL" not in mctx["position_notes"]


@then(parsers.parse('应返回包含 "{text}" 的结果'))
def then_recall_contains(mctx, text):
    results = mctx["recall_results"]
    all_content = " ".join(r["content"] for r in results)
    assert text in all_content
