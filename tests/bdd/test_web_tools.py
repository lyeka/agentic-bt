"""
[INPUT]: pytest-bdd, agent.tools.web, unittest.mock
[OUTPUT]: web_tools.feature 的 step definitions
[POS]: 测试 web_search/web_fetch 工具的行为 + 条件注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenario, then, when


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 注册
# ─────────────────────────────────────────────────────────────────────────────

@scenario("features/web_tools.feature", "web_search 返回结构化结果")
def test_web_search_results(): pass

@scenario("features/web_tools.feature", "web_search 支持域名过滤")
def test_web_search_domains(): pass

@scenario("features/web_tools.feature", "web_search 限制最大结果数为 10")
def test_web_search_max_results(): pass

@scenario("features/web_tools.feature", "web_search 搜索失败返回 error")
def test_web_search_error(): pass

@scenario("features/web_tools.feature", "web_fetch 获取页面内容")
def test_web_fetch_content(): pass

@scenario("features/web_tools.feature", "web_fetch 超长内容自动截断")
def test_web_fetch_truncation(): pass

@scenario("features/web_tools.feature", "web_fetch 无效 URL 返回 error")
def test_web_fetch_invalid_url(): pass

@scenario("features/web_tools.feature", "web_fetch 网络错误返回 error")
def test_web_fetch_network_error(): pass

@scenario("features/web_tools.feature", "无 search adapter 时只注册 web_fetch")
def test_no_adapter_conditional_register(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Mock 基础设施
# ─────────────────────────────────────────────────────────────────────────────

class _MockKernel:
    """最小 Kernel 实现，仅支持 tool 注册与调用。"""

    def __init__(self):
        self._tools: dict = {}

    def tool(self, name: str, description: str, parameters: dict, handler) -> None:
        self._tools[name] = handler

    def call(self, name: str, args: dict) -> dict:
        handler = self._tools.get(name)
        if handler is None:
            return {"error": f"未注册工具: {name}"}
        return handler(args)

    def has_tool(self, name: str) -> bool:
        return name in self._tools


class _MockSearchAdapter:
    """可配置的 mock 搜索适配器，记录调用参数。"""

    name = "mock"

    def __init__(self, results=None, raise_error: Exception | None = None):
        self._results = results or [
            {"title": "Mock Title", "url": "https://example.com", "snippet": "摘要内容", "score": 0.9},
            {"title": "Mock Title 2", "url": "https://example2.com", "snippet": "摘要内容2", "score": 0.8},
        ]
        self._raise_error = raise_error
        self.last_call: dict = {}

    def search(self, query: str, max_results: int = 5, domains: list | None = None) -> list[dict]:
        self.last_call = {"query": query, "max_results": max_results, "domains": domains}
        if self._raise_error:
            raise self._raise_error
        return self._results[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
# Given — 初始化 Kernel
# ─────────────────────────────────────────────────────────────────────────────

@given("一个带 mock 搜索的 Kernel", target_fixture="wctx")
def given_kernel_with_mock_search():
    from athenaclaw.tools import web
    kernel = _MockKernel()
    adapter = _MockSearchAdapter()
    web.register(kernel, search_adapter=adapter)
    return {"kernel": kernel, "adapter": adapter}


@given("一个会抛异常的 mock 搜索 Kernel", target_fixture="wctx")
def given_kernel_with_failing_search():
    from athenaclaw.tools import web
    kernel = _MockKernel()
    adapter = _MockSearchAdapter(raise_error=RuntimeError("API 连接失败"))
    web.register(kernel, search_adapter=adapter)
    return {"kernel": kernel, "adapter": adapter}


@given("一个带 web_fetch 的 Kernel", target_fixture="wctx")
def given_kernel_with_fetch():
    from athenaclaw.tools import web
    kernel = _MockKernel()
    web.register(kernel, search_adapter=None)
    return {"kernel": kernel}


@given("一个无 search adapter 的 Kernel", target_fixture="wctx")
def given_kernel_no_adapter():
    from athenaclaw.tools import web
    kernel = _MockKernel()
    web.register(kernel, search_adapter=None)
    return {"kernel": kernel}


# ─────────────────────────────────────────────────────────────────────────────
# When — 工具调用
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('调用 web_search query "{query}"'), target_fixture="wctx")
def when_web_search(wctx, query):
    wctx["result"] = wctx["kernel"].call("web_search", {"query": query})
    return wctx


@when(parsers.parse('调用 web_search query "{query}" domains "{domain}"'), target_fixture="wctx")
def when_web_search_domains(wctx, query, domain):
    wctx["result"] = wctx["kernel"].call("web_search", {"query": query, "domains": [domain]})
    return wctx


@when(parsers.parse('调用 web_search query "{query}" max_results {n:d}'), target_fixture="wctx")
def when_web_search_max_results(wctx, query, n):
    wctx["result"] = wctx["kernel"].call("web_search", {"query": query, "max_results": n})
    return wctx


@when(parsers.parse('mock HTTP 返回 "{content}" 并调用 web_fetch url "{url}"'), target_fixture="wctx")
def when_web_fetch_content(wctx, content, url):
    from athenaclaw.tools import web as web_mod
    with patch.object(web_mod, "_fetch_url", return_value=content):
        wctx["result"] = wctx["kernel"].call("web_fetch", {"url": url})
    return wctx


@when(parsers.parse('mock HTTP 返回超长内容并调用 web_fetch url "{url}"'), target_fixture="wctx")
def when_web_fetch_long(wctx, url):
    from athenaclaw.tools import web as web_mod
    # 生成超过 6000 字节的内容
    long_content = "A" * 8000
    wctx["original_length"] = len(long_content)
    with patch.object(web_mod, "_fetch_url", return_value=long_content):
        wctx["result"] = wctx["kernel"].call("web_fetch", {"url": url})
    return wctx


@when(parsers.parse('调用 web_fetch url "{url}"'), target_fixture="wctx")
def when_web_fetch_url(wctx, url):
    wctx["result"] = wctx["kernel"].call("web_fetch", {"url": url})
    return wctx


@when(parsers.parse('mock HTTP 抛出网络错误并调用 web_fetch url "{url}"'), target_fixture="wctx")
def when_web_fetch_network_error(wctx, url):
    import urllib.error
    from athenaclaw.tools import web as web_mod
    with patch.object(web_mod, "_fetch_url", side_effect=RuntimeError("获取失败: urlopen error")):
        wctx["result"] = wctx["kernel"].call("web_fetch", {"url": url})
    return wctx


# ─────────────────────────────────────────────────────────────────────────────
# Then — 断言
# ─────────────────────────────────────────────────────────────────────────────

@then("返回 count 大于 0")
def then_count_positive(wctx):
    assert wctx["result"].get("count", 0) > 0


@then("每条结果包含 title url snippet")
def then_results_have_fields(wctx):
    for r in wctx["result"]["results"]:
        assert "title" in r
        assert "url" in r
        assert "snippet" in r


@then(parsers.parse('mock adapter 收到 domains 包含 "{domain}"'))
def then_adapter_received_domain(wctx, domain):
    domains = wctx["adapter"].last_call.get("domains") or []
    assert domain in domains


@then(parsers.parse("mock adapter 收到 max_results 为 {n:d}"))
def then_adapter_received_max_results(wctx, n):
    assert wctx["adapter"].last_call.get("max_results") == n


@then("返回结果包含 error")
def then_result_has_error(wctx):
    assert "error" in wctx["result"]


@then(parsers.parse('返回 content 包含 "{text}"'))
def then_content_contains(wctx, text):
    assert text in wctx["result"].get("content", "")


@then(parsers.parse('返回 url 为 "{url}"'))
def then_url_equals(wctx, url):
    assert wctx["result"].get("url") == url


@then("返回 truncated 为 True")
def then_truncated_true(wctx):
    assert wctx["result"].get("truncated") is True


@then("返回 chars 小于原始内容长度")
def then_chars_less_than_original(wctx):
    assert wctx["result"].get("chars", 0) < wctx["original_length"]


@then(parsers.parse('Kernel 已注册工具 "{name}"'))
def then_tool_registered(wctx, name):
    assert wctx["kernel"].has_tool(name), f"工具 {name!r} 未注册"


@then(parsers.parse('Kernel 未注册工具 "{name}"'))
def then_tool_not_registered(wctx, name):
    assert not wctx["kernel"].has_tool(name), f"工具 {name!r} 不应被注册"
