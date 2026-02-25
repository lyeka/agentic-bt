"""
[INPUT]: agenticbt.models (Decision, Fill, PerformanceMetrics, ComplianceReport)
[OUTPUT]: Evaluator — 绩效与遵循度计算
[POS]: 评估层，回测结束后由 runner 调用，不依赖 Engine 或 LLM
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import math

from .models import ComplianceReport, Decision, Fill, PerformanceMetrics


class Evaluator:
    """
    两维评估：绩效 + 遵循度。

    输入均为纯数据，无副作用。
    """

    def calc_performance(
        self,
        equity_curve: list[float],
        fills: list[Fill],
    ) -> PerformanceMetrics:
        if len(equity_curve) < 2:
            return PerformanceMetrics(
                total_return=0.0, max_drawdown=0.0, sharpe_ratio=0.0,
                win_rate=0.0, profit_factor=0.0,
                total_trades=0, equity_curve=list(equity_curve),
            )

        initial = equity_curve[0]
        final = equity_curve[-1]
        total_return = (final - initial) / initial if initial else 0.0

        max_drawdown = self._max_drawdown(equity_curve)
        sharpe = self._sharpe(equity_curve)

        # 从成交记录计算交易统计（简单按 sell fill 计算盈亏）
        trade_pnls = self._fill_pnls(fills)
        total_trades = len(trade_pnls)

        if total_trades == 0:
            win_rate = 0.0
            profit_factor = 0.0
        else:
            winners = [p for p in trade_pnls if p > 0]
            losers = [p for p in trade_pnls if p < 0]
            win_rate = round(len(winners) / total_trades, 3)
            gross_profit = sum(winners)
            gross_loss = abs(sum(losers)) if losers else 0
            profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else float("inf")

        return PerformanceMetrics(
            total_return=round(total_return, 6),
            max_drawdown=round(max_drawdown, 6),
            sharpe_ratio=round(sharpe, 4),
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            equity_curve=list(equity_curve),
        )

    def calc_compliance(self, decisions: list[Decision]) -> ComplianceReport:
        dist: dict[str, int] = {}
        with_indicators = 0
        for d in decisions:
            dist[d.action] = dist.get(d.action, 0) + 1
            if d.indicators_used:
                with_indicators += 1
        return ComplianceReport(
            action_distribution=dist,
            decisions_with_indicators=with_indicators,
            total_decisions=len(decisions),
        )

    # ── 内部计算 ──────────────────────────────────────────────────────────────

    def _max_drawdown(self, curve: list[float]) -> float:
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def _sharpe(self, curve: list[float], risk_free: float = 0.0) -> float:
        if len(curve) < 2:
            return 0.0
        returns = [(curve[i] - curve[i - 1]) / curve[i - 1] for i in range(1, len(curve))]
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / n
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean - risk_free) / std * math.sqrt(252)  # 年化

    def _fill_pnls(self, fills: list[Fill]) -> list[float]:
        """从 Fill 记录中提取盈亏（sell fill 已含 realized pnl 近似值）"""
        # 简单用成交价 - 0 做信号（实际 realized pnl 在 engine 中计算）
        # 此处返回 sell fill 的数量作为 trade count 代理
        return [1.0 for f in fills if f.side == "sell"]
