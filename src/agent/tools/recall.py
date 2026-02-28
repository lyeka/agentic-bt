"""
[INPUT]: agent.kernel (Kernel), pathlib
[OUTPUT]: register()
[POS]: 领域增强工具，全文搜索 workspace 中的 .md 文件；Phase 1 用简单文本匹配，后续可升级 FTS5
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, workspace: Path) -> None:
    """向 Kernel 注册 recall 工具"""

    def recall_handler(args: dict) -> dict:
        query = args["query"]
        results = []
        for md in workspace.rglob("*.md"):
            content = md.read_text(encoding="utf-8")
            if query not in content:
                continue
            rel = str(md.relative_to(workspace))
            # 提取匹配段落（前后各 1 行）
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if query in line:
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    snippet = "\n".join(lines[start:end])
                    results.append({"path": rel, "snippet": snippet})
                    break
        return {"results": results, "count": len(results)}

    kernel.tool(
        name="recall",
        description="搜索工作区文件（memory + notebook），返回匹配段落",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
        handler=recall_handler,
    )
