"""
[INPUT]: urllib.request, json
[OUTPUT]: TavilyAdapter — SearchAdapter Protocol 的 Tavily 实现
[POS]: adapters/web/ 的默认搜索后端，agent-native Tavily Search API 封装
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

_TAVILY_URL = "https://api.tavily.com/search"
_SNIPPET_MAX = 300
_TIMEOUT = 10


class TavilyAdapter:
    """Tavily Search API — agent-native 设计，搜索结果自带相关度评分"""

    name = "tavily"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(
        self,
        query: str,
        max_results: int = 5,
        domains: list[str] | None = None,
    ) -> list[dict]:
        """
        调用 Tavily Search API，返回标准化结果列表。

        返回：[{"title": str, "url": str, "snippet": str, "score": float|None}]
        """
        payload: dict = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        if domains:
            payload["include_domains"] = domains

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _TAVILY_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Tavily API 错误: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Tavily 网络错误: {e}") from e

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content", ""))[:_SNIPPET_MAX],
                "score": r.get("score"),
            }
            for r in body.get("results", [])
        ]
