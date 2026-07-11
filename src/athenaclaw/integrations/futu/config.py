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
    """交易侧沿用的兼容别名。

    刻意不包含交易密码字段。SIMULATE/REAL 两个环境的解锁都只能在本机
    Futu OpenD 客户端手工完成（点一次，直到 OpenD 进程重启前一直有效）。
    代码侧不持有密码、不调用 unlock_trade、不做自动解锁 —— 这是设计选择，
    不是遗漏。账户处于未解锁状态时，下单/撤单会失败并返回
    TradeErrorCode.TRADE_LOCKED，错误信息里会指引去 OpenD 手工解锁。
    """

