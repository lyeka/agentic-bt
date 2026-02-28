"""
[INPUT]: core.indicators
[OUTPUT]: IndicatorEngine, AVAILABLE_INDICATORS — re-export from core/indicators
[POS]: 兼容层，实现已提取至 core/indicators.py
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from core.indicators import AVAILABLE_INDICATORS, IndicatorEngine  # noqa: F401

__all__ = ["IndicatorEngine", "AVAILABLE_INDICATORS"]
