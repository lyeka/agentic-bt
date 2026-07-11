"""
[INPUT]: typing.Protocol, athenaclaw.kernel (Kernel)
[OUTPUT]: SnapshotAdapter Protocol + register()
[POS]: 领域核心工具，与 market_ohlcv 同级；提供实时快照/报价，供下单前判断行情新鲜度，不落 DataStore 历史
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Any, Protocol


# ─────────────────────────────────────────────────────────────────────────────
# SnapshotAdapter Protocol
# ─────────────────────────────────────────────────────────────────────────────

class SnapshotAdapter(Protocol):
    """实时快照适配器接口 — 一次调用返回一批 symbol 的当前盘口，不需要订阅、不返回时间序列"""

    name: str

    def snapshot(self, symbols: list[str]) -> list[dict[str, Any]]: ...


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, adapter: SnapshotAdapter) -> None:
    """向 Kernel 注册 market_snapshot 工具"""

    def market_snapshot(args: dict) -> dict:
        symbols = args.get("symbols") or []
        if not isinstance(symbols, list) or not symbols:
            return {"error": "缺少参数: symbols（非空数组）"}
        try:
            quotes = adapter.snapshot([str(item).strip() for item in symbols])
        except Exception as exc:
            return {"error": str(exc)}
        return {"status": "ok", "quotes": quotes}

    kernel.tool(
        name="market_snapshot",
        description=(
            "获取一批 symbol 的实时快照：最新价、开高低、昨收、成交量额、买卖价等。"
            "直接来自下单 broker 的行情线路，不需要订阅，不写入 market_ohlcv 使用的 DataStore 历史，"
            "只返回当前这一个时间点，不是时间序列。"
            "何时使用: 下单前确认当前价格新鲜度、判断限价是否偏离盘口过远、撤单前重新核对最新成交价。"
            "何时不要用: 需要历史 K 线或分钟级序列时用 market_ohlcv。"
            "返回的 update_time 是 broker 侧行情时间戳，用它判断数据新鲜度，不得凭经验推断当前是否在正常交易时段。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标的代码数组，如 [\"AAPL\", \"00700.HK\", \"600519.SH\"]",
                },
            },
            "required": ["symbols"],
        },
        handler=market_snapshot,
    )
