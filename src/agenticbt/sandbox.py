"""
[INPUT]: core.sandbox
[OUTPUT]: exec_compute, HELPERS — re-export from core/sandbox
[POS]: 兼容层，实现已提取至 core/sandbox.py
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from core.sandbox import HELPERS, exec_compute  # noqa: F401

__all__ = ["exec_compute", "HELPERS"]
