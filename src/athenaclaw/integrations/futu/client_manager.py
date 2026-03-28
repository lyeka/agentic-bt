"""
[INPUT]: athenaclaw.integrations.futu.config
[OUTPUT]: FutuClientManager
[POS]: 富途 OpenD 交易 context 生命周期管理
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from athenaclaw.trading.errors import TradeError, TradeErrorCode


class FutuClientManager:
    def __init__(self, config) -> None:
        self._config = config
        self._trade_context = None

    def trade_context(self):
        if self._trade_context is not None:
            return self._trade_context
        futu = _load_futu()
        kwargs = {
            "host": self._config.host,
            "port": self._config.port,
            "filter_trdmarket": futu.TrdMarket.NONE,
        }
        if self._config.security_firm:
            kwargs["security_firm"] = getattr(futu.SecurityFirm, self._config.security_firm)
        try:
            self._trade_context = futu.OpenSecTradeContext(**kwargs)
        except Exception as exc:
            raise TradeError(TradeErrorCode.BROKER_DISCONNECTED, f"无法连接 Futu OpenD: {exc}") from exc
        return self._trade_context

    def close(self) -> None:
        if self._trade_context is None:
            return
        try:
            self._trade_context.close()
        finally:
            self._trade_context = None


def _load_futu():
    try:
        import futu  # type: ignore
    except Exception as exc:  # pragma: no cover - import path only exercised with dependency installed
        raise TradeError(
            TradeErrorCode.BROKER_NOT_CONFIGURED,
            "未安装 futu SDK，无法使用富途交易适配器",
        ) from exc
    return futu
