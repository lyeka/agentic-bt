"""
[INPUT]: pathlib, datetime
[OUTPUT]: Memory — 文件式记忆系统；Workspace — 工作空间管理
[POS]: 记忆层，提供 log/note/recall/init_playbook 工具接口，被 tools.py 调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Workspace
# ─────────────────────────────────────────────────────────────────────────────

class Workspace:
    """
    独立工作空间。每次回测创建一个，路径唯一。

    结构：
      {root}/
        playbook.md
        journal/{date}.md
        notes/{key}.md
        decisions.jsonl
        result.json
    """

    def __init__(self, root: Path | str | None = None) -> None:
        if root is None:
            # 使用系统临时目录下的唯一子目录
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            root = Path(tempfile.gettempdir()) / "agenticbt" / f"run_{ts}"
        self.root = Path(root)
        self._init_dirs()

    def _init_dirs(self) -> None:
        for subdir in ["journal", "notes"]:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> str:
        return str(self.root)


# ─────────────────────────────────────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────────────────────────────────────

class Memory:
    """
    文件式记忆，三个核心操作：log / note / recall。

    设计哲学：文件即真理，索引是派生物。
    """

    def __init__(self, workspace: Workspace, current_date: date | None = None) -> None:
        self._ws = workspace
        self._date = current_date or date.today()

    def set_date(self, d: date) -> None:
        """回测循环推进时同步模拟日期"""
        self._date = d

    # ── 三个核心工具 ──────────────────────────────────────────────────────────

    def init_playbook(self, strategy_prompt: str) -> None:
        """初始化 playbook.md，用策略描述作为初始内容"""
        pb = self._ws.root / "playbook.md"
        pb.write_text(strategy_prompt, encoding="utf-8")

    def read_playbook(self) -> str:
        pb = self._ws.root / "playbook.md"
        return pb.read_text(encoding="utf-8") if pb.exists() else ""

    def log(self, content: str, log_date: date | None = None) -> None:
        """往当日日志 append 一条记录"""
        d = log_date or self._date
        journal_file = self._ws.root / "journal" / f"{d}.md"
        with open(journal_file, "a", encoding="utf-8") as f:
            f.write(f"\n- {content}\n")

    def note(self, key: str, content: str) -> None:
        """创建或覆盖主题笔记"""
        note_file = self._ws.root / "notes" / f"{key}.md"
        note_file.write_text(content, encoding="utf-8")

    def read_note(self, key: str) -> str | None:
        note_file = self._ws.root / "notes" / f"{key}.md"
        return note_file.read_text(encoding="utf-8") if note_file.exists() else None

    def read_position_notes(self, symbols: list[str]) -> dict[str, str]:
        """读取持仓相关笔记（key = position_{symbol}）"""
        result = {}
        for sym in symbols:
            content = self.read_note(f"position_{sym}")
            if content is not None:
                result[sym] = content
        return result

    def recall(self, query: str) -> list[dict]:
        """
        关键词检索：扫描 journal/ + notes/ + playbook.md。
        返回 [{"source": "...", "content": "..."}]
        简单实现：逐行匹配 query 中的任意词
        """
        keywords = query.strip().split()
        results = []

        # 扫描 journal/
        journal_dir = self._ws.root / "journal"
        for f in sorted(journal_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if any(kw in text for kw in keywords):
                results.append({"source": f"journal/{f.name}", "content": text.strip()})

        # 扫描 notes/
        notes_dir = self._ws.root / "notes"
        for f in sorted(notes_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if any(kw in text for kw in keywords):
                results.append({"source": f"notes/{f.name}", "content": text.strip()})

        # 扫描 playbook
        pb = self._ws.root / "playbook.md"
        if pb.exists():
            text = pb.read_text(encoding="utf-8")
            if any(kw in text for kw in keywords):
                results.append({"source": "playbook.md", "content": text.strip()})

        return results
