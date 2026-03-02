"""
[INPUT]: pytest-bdd, agent.kernel, pathlib, unittest.mock
[OUTPUT]: memory_compress.feature step definitions（fixture: mcctx，mock LLM 压缩）
[POS]: tests/ BDD 测试层，验证 memory.md 超限自动压缩机制
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from pytest_bdd import given, scenario, then, when

from agent.kernel import Kernel, MEMORY_MAX_CHARS


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/memory_compress.feature"

@scenario(FEATURE, "超限内容触发压缩")
def test_compress_triggered(): pass

@scenario(FEATURE, "未超限不触发压缩")
def test_compress_not_triggered(): pass

@scenario(FEATURE, "压缩保持 markdown 格式")
def test_compress_markdown(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_oversized_content() -> str:
    """生成超过 MEMORY_MAX_CHARS 的内容"""
    line = "## 2024-01-01 记忆条目\n- 重要市场观察数据点\n\n"
    return line * (MEMORY_MAX_CHARS // len(line) + 2)


def _make_normal_content() -> str:
    """生成未超限的内容"""
    return "## 记忆\n- 一些记忆条目\n"


def _make_on_memory_write(kernel: Kernel, workspace: Path, compressor: object):
    """构造 memory write handler（与 cli.py 逻辑一致）"""
    def handler(event: str, data: object) -> None:
        mem = workspace / "memory.md"
        if not mem.exists():
            return
        content = mem.read_text(encoding="utf-8")
        if len(content) <= MEMORY_MAX_CHARS:
            return
        compressed = compressor.compress(content, MEMORY_MAX_CHARS)
        mem.write_text(compressed, encoding="utf-8")
        kernel.emit("memory.compressed", {
            "original_chars": len(content),
            "compressed_chars": len(compressed),
        })
    return handler


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个已挂载压缩的 Kernel", target_fixture="mcctx")
def given_kernel_with_compress(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    kernel = Kernel(api_key="test")

    # Mock 压缩器：返回固定 markdown 内容（在上限内）
    mock_compressor = MagicMock()
    mock_compressor.compress.return_value = "## 压缩后记忆\n- 保留最重要的条目\n"

    # 挂载压缩 handler
    handler = _make_on_memory_write(kernel, workspace, mock_compressor)
    kernel.wire("write:memory.md", handler)

    # 追踪 memory.compressed 事件
    compressed_events: list[dict] = []
    kernel.wire("memory.compressed", lambda e, d: compressed_events.append(d))

    return {
        "kernel": kernel,
        "workspace": workspace,
        "compressor": mock_compressor,
        "compressed_events": compressed_events,
    }


@given("memory.md 内容超过上限", target_fixture="mcctx")
def given_oversized_memory(mcctx):
    content = _make_oversized_content()
    mem = mcctx["workspace"] / "memory.md"
    mem.write_text(content, encoding="utf-8")
    mcctx["original_content"] = content
    return mcctx


@given("memory.md 内容未超过上限", target_fixture="mcctx")
def given_normal_memory(mcctx):
    content = _make_normal_content()
    mem = mcctx["workspace"] / "memory.md"
    mem.write_text(content, encoding="utf-8")
    mcctx["original_content"] = content
    return mcctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when("触发 memory 写入事件", target_fixture="mcctx")
def when_trigger_write(mcctx):
    mcctx["kernel"].emit("write:memory.md", {})
    return mcctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("memory.md 字数在上限内")
def then_within_limit(mcctx):
    mem = mcctx["workspace"] / "memory.md"
    content = mem.read_text(encoding="utf-8")
    assert len(content) <= MEMORY_MAX_CHARS


@then("收到 memory.compressed 事件")
def then_compressed_event(mcctx):
    assert len(mcctx["compressed_events"]) >= 1
    event = mcctx["compressed_events"][0]
    assert "original_chars" in event
    assert "compressed_chars" in event


@then("memory.md 内容不变")
def then_content_unchanged(mcctx):
    mem = mcctx["workspace"] / "memory.md"
    current = mem.read_text(encoding="utf-8")
    assert current == mcctx["original_content"]


@then("未收到 memory.compressed 事件")
def then_no_compressed_event(mcctx):
    assert len(mcctx["compressed_events"]) == 0


@then("压缩结果是 markdown 格式")
def then_markdown_format(mcctx):
    mem = mcctx["workspace"] / "memory.md"
    content = mem.read_text(encoding="utf-8")
    # 压缩后内容包含 markdown 特征（# 标题或 - 列表）
    assert "#" in content or "-" in content
