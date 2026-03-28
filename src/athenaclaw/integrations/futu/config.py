"""
[INPUT]: dataclasses
[OUTPUT]: FutuTradeConfig
[POS]: 富途交易 provider 配置对象
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FutuTradeConfig:
    host: str = "127.0.0.1"
    port: int = 11111
    security_firm: str | None = None
