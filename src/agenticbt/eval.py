"""
[INPUT]: agenticbt.models (Decision, PerformanceMetrics, ComplianceReport)
[OUTPUT]: Evaluator — 绩效与遵循度计算
[POS]: 评估层，回测结束后由 runner 调用，不依赖 Engine 或 LLM
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import math

from .models import ComplianceReport, Decision, PerformanceMetrics


class Evaluator:
    """
    两维评估：绩效 + 遵循度。

    输入均为纯数据，无副作用。
    """

    def calc_performance(
        self,
        equity_curve: list[float],
        trade_log: list[dict],          # [{"pnl": float, ...}, ...]
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
        returns = self._returns(equity_curve)
        sharpe = self._sharpe(returns)

        trade_pnls = [t["pnl"] for t in trade_log]
        total_trades = len(trade_pnls)

        if total_trades == 0:
            win_rate, profit_factor = 0.0, 0.0
            avg_trade_return, best_trade, worst_trade = 0.0, 0.0, 0.0
        else:
            winners = [p for p in trade_pnls if p > 0]
            losers  = [p for p in trade_pnls if p < 0]
            win_rate = round(len(winners) / total_trades, 3)
            gross_profit = sum(winners)
            gross_loss   = abs(sum(losers)) if losers else 0
            profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else float("inf")
            avg_trade_return = round(sum(trade_pnls) / total_trades, 4)
            best_trade = max(trade_pnls)
            worst_trade = min(trade_pnls)

        return PerformanceMetrics(
            total_return=round(total_return, 6),
            max_drawdown=round(max_drawdown, 6),
            sharpe_ratio=round(sharpe, 4),
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            equity_curve=list(equity_curve),
            sortino_ratio=round(self._sortino(returns), 4),
            calmar_ratio=round(self._calmar(total_return, max_drawdown), 4),
            volatility=round(self._volatility(returns), 4),
            max_dd_duration=self._max_dd_duration(equity_curve),
            cagr=round(self._cagr(equity_curve), 6),
            avg_trade_return=avg_trade_return,
            best_trade=best_trade,
            worst_trade=worst_trade,
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

    def _returns(self, curve: list[float]) -> list[float]:
        """权益曲线 → 逐 bar 收益率序列"""
        return [(curve[i] - curve[i - 1]) / curve[i - 1]
                for i in range(1, len(curve)) if curve[i - 1] != 0]

    def _max_drawdown(self, curve: list[float]) -> float:
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def _sharpe(self, returns: list[float], risk_free: float = 0.0) -> float:
        if not returns:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / n
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean - risk_free) / std * math.sqrt(252)

    def _sortino(self, returns: list[float], risk_free: float = 0.0) -> float:
        """(mean - rf) / downside_std * sqrt(252)"""
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        downside = [min(r - risk_free, 0) ** 2 for r in returns]
        downside_var = sum(downside) / len(downside)
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return (mean - risk_free) / downside_std * math.sqrt(252)

    def _volatility(self, returns: list[float]) -> float:
        """年化波动率 = std(returns) * sqrt(252)"""
        if not returns:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / n
        return math.sqrt(variance) * math.sqrt(252)

    def _cagr(self, curve: list[float]) -> float:
        """年化复合收益率 = (final/initial)^(1/n_years) - 1"""
        if len(curve) < 2 or curve[0] <= 0:
            return 0.0
        n_years = (len(curve) - 1) / 252
        if n_years <= 0:
            return 0.0
        ratio = curve[-1] / curve[0]
        if ratio <= 0:
            return 0.0
        return ratio ** (1 / n_years) - 1

    def _calmar(self, total_return: float, max_drawdown: float) -> float:
        """Calmar = total_return / max_drawdown"""
        if max_drawdown == 0:
            return 0.0
        return total_return / max_drawdown

    def _max_dd_duration(self, curve: list[float]) -> int:
        """从峰值到恢复的最长 bar 数"""
        peak = curve[0]
        since_peak = 0
        max_duration = 0
        for v in curve[1:]:
            since_peak += 1
            if v >= peak:
                max_duration = max(max_duration, since_peak)
                peak = v
                since_peak = 0
        return max(max_duration, since_peak)
