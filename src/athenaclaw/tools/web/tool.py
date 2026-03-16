"""
[INPUT]: agent.tools._truncate (truncate_head), urllib.request, json, html.parser
[OUTPUT]: SearchAdapter Protocol + register() — 注册 web_search + web_fetch 工具
[POS]: 通用 Web 能力工具层；adapter pattern 解耦搜索后端，fetch 双策略（Jina + stdlib fallback）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Protocol

from athenaclaw.tools.filesystem.truncate import truncate_head

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# SearchAdapter Protocol
# ─────────────────────────────────────────────────────────────────────────────

class SearchAdapter(Protocol):
    """Web 搜索后端接口 — 返回标准化结果列表"""

    name: str

    def search(
        self,
        query: str,
        max_results: int = 5,
        domains: list[str] | None = None,
    ) -> list[dict]:
        """返回 [{"title": str, "url": str, "snippet": str, "score": float|None}]"""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# HTML → Text（stdlib fallback）
# ─────────────────────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """最小 HTML 去标签器，跳过 script/style/nav/footer/header"""

    _SKIP_TAGS = frozenset({"script", "style", "nav", "footer", "header"})

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._depth = 0  # skip 标签嵌套深度

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def text(self) -> str:
        return "\n".join(self._parts)


_FETCH_TIMEOUT = 15
_FETCH_MAX_BYTES = 6_000


def _fetch_url(url: str) -> str:
    """获取 URL 内容为纯文本。Jina Reader 优先，stdlib 降级。"""

    # 策略 1：Jina Reader（返回 clean markdown）
    jina_url = f"https://r.jina.ai/{url}"
    try:
        req = urllib.request.Request(
            jina_url,
            headers={"Accept": "text/markdown", "User-Agent": "AgenticBT/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        pass  # 静默降级

    # 策略 2：直接抓取 + HTML 去标签
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 AgenticBT/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("Content-Type", "")
            if "html" in content_type:
                extractor = _TextExtractor()
                extractor.feed(raw)
                return extractor.text()
            return raw
    except urllib.error.URLError as e:
        raise RuntimeError(f"获取失败: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

_MAX_RESULTS_CAP = 10


def register(kernel: object, search_adapter: SearchAdapter | None = None) -> None:
    """
    向 Kernel 注册 Web 工具。

    - web_fetch：始终注册（不依赖任何 API key）
    - web_search：仅当 search_adapter 非 None 时注册
    """

    # ── web_fetch（始终注册）────────────────────────────────────────────

    def web_fetch_handler(args: dict) -> dict:
        url = args.get("url", "").strip()
        if not url:
            return {"error": "缺少参数: url"}
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"error": f"无效 URL（需要 http:// 或 https://）: {url}"}
        try:
            content = _fetch_url(url)
        except RuntimeError as e:
            return {"error": str(e)}
        tr = truncate_head(content, max_bytes=_FETCH_MAX_BYTES)
        result: dict = {
            "url": url,
            "content": tr.content,
            "chars": len(tr.content),
        }
        if tr.truncated:
            result["truncated"] = True
            result["total_chars"] = len(content)
        return result

    kernel.tool(
        name="web_fetch",
        description=(
            "获取指定 URL 的页面全文（自动转为 markdown 格式）。超长内容自动截断。\n\n"
            "适用场景：\n"
            "- web_search 结果中某条值得深入阅读\n"
            "- 用户发来一个链接，需要查看其内容\n\n"
            "节制原则：每轮对话只获取最相关的 1-2 个 URL，避免批量抓取浪费上下文。\n\n"
            "返回：{url, content, chars}。截断时附加 {truncated: true, total_chars: N}。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的完整 URL（必须以 http:// 或 https:// 开头）",
                },
            },
            "required": ["url"],
        },
        handler=web_fetch_handler,
    )

    # ── web_search（条件注册）───────────────────────────────────────────

    if search_adapter is None:
        return

    def web_search_handler(args: dict) -> dict:
        query = args.get("query", "").strip()
        if not query:
            return {"error": "缺少参数: query"}
        max_results = min(int(args.get("max_results", 5)), _MAX_RESULTS_CAP)
        domains = args.get("domains") or None
        try:
            results = search_adapter.search(query, max_results, domains)
        except Exception as e:
            return {"error": f"搜索失败: {type(e).__name__}: {e}"}
        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    kernel.tool(
        name="web_search",
        description=(
            "搜索互联网，返回相关结果的标题、链接与摘要（轻量列表，不含全文）。\n\n"
            "适用场景：\n"
            "- 需要你不确定或不了解的信息\n"
            "- 用户询问近期事件、新闻、动态\n"
            "- 用户明确要求搜索某个话题\n"
            "- 需要查找特定网站、文档、资源\n\n"
            "不适用：\n"
            "- 你已有足够信息可直接回答——不要为了「确认」而搜索\n"
            "- 其他已注册工具能直接提供的数据（优先使用专用工具）\n\n"
            "查询技巧：包含关键实体和限定词（如「Next.js 15 server actions 教程」而非「Next.js」）。\n"
            "domains 参数可限定搜索范围到特定网站。\n\n"
            "工作流：搜索 → 审视摘要判断相关性 → 对最相关的 1-2 条用 web_fetch 获取全文。\n"
            "返回格式：{\"results\": [{\"title\", \"url\", \"snippet\", \"score\"}], \"count\": N}"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，包含关键实体和限定词效果更好",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数（默认 5，上限 10）",
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "限定搜索域名列表（如 [\"github.com\", \"docs.python.org\"]）",
                },
            },
            "required": ["query"],
        },
        handler=web_search_handler,
    )
