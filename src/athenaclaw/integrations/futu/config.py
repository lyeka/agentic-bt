"""
[INPUT]: dataclasses
[OUTPUT]: FutuConfig, FutuTradeConfig
[POS]: 富途 provider 配置对象
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FutuConfig:
    host: str = "127.0.0.1"
    port: int = 11111
    security_firm: str | None = None


@dataclass(frozen=True)
class FutuTradeConfig(FutuConfig):
    """交易侧沿用的兼容别名。"""
