"""
[INPUT]: agent.adapters.telegram helpers
[OUTPUT]: Telegram adapter helper tests（渲染/配置解析）
[POS]: tests/ 单测层，验证 Telegram 渲染与 env 解析基础逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from agent.adapters.telegram import (
    _markdown_to_html,
    _normalize_render_mode,
    _parse_allowed_user_ids,
    _parse_bool,
)


def test_parse_allowed_user_ids():
    assert _parse_allowed_user_ids("1, 2,3") == {"1", "2", "3"}
    assert _parse_allowed_user_ids("") == set()
    assert _parse_allowed_user_ids(None) == set()


def test_parse_bool_default():
    assert _parse_bool(None, default=False) is False
    assert _parse_bool(None, default=True) is True
    assert _parse_bool("true", default=False) is True
    assert _parse_bool("0", default=True) is False


def test_normalize_render_mode():
    assert _normalize_render_mode(None) == "html"
    assert _normalize_render_mode("markdown") == "markdown"
    assert _normalize_render_mode("plain") == "none"
    assert _normalize_render_mode("text") == "none"
    assert _normalize_render_mode("unknown") == "html"


def test_markdown_to_html_basic():
    text = (
        "## Title\n\n"
        "- item1\n"
        "- item2\n\n"
        "normal **bold** and *italic* and `code`\n\n"
        "```python\n"
        "print('x')\n"
        "```\n"
    )
    html = _markdown_to_html(text)
    assert "<b>Title</b>" in html
    assert "• item1" in html
    assert "<b>bold</b>" in html
    assert "<i>italic</i>" in html
    assert "<code>code</code>" in html
    assert "<pre><code>" in html and "</code></pre>" in html

