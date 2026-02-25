"""
[INPUT]: agenticbt.engine, agenticbt.memory, agenticbt.tools, agenticbt.models, agenticbt.eval
[OUTPUT]: Runner — 回测主循环编排器；ContextManager — 上下文组装
[POS]: 顶层编排器，连接 Engine/Memory/Agent/Eval，被用户直接调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .agent import AgentProtocol
from .engine import Engine
from .eval import Evaluator
from .memory import Memory, Workspace
from .models import BacktestConfig, BacktestResult, Decision
from .tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# ContextManager
# ─────────────────────────────────────────────────────────────────────────────

class ContextManager:
    """组装 Agent 决策所需的上下文（六层注入的简化版）"""

    def assemble(
        self,
        engine: Engine,
        memory: Memory,
        bar_index: int,
        events: list[dict],
    ) -> dict:
        snap = engine.market_snapshot()
        acc = engine.account_snapshot()
        playbook = memory.read_playbook()
        position_notes = memory.read_position_notes(list(acc.positions.keys()))

        return {
            "datetime": snap.datetime,
            "bar_index": bar_index,
            "playbook": playbook,
            "market": {
                "symbol": snap.symbol,
                "open": snap.open,
                "high": snap.high,
                "low": snap.low,
                "close": snap.close,
                "volume": snap.volume,
            },
            "account": {
                "cash": acc.cash,
                "equity": acc.equity,
                "positions": {
                    sym: {"size": p.size, "avg_price": p.avg_price}
                    for sym, p in acc.positions.items()
                },
            },
            "position_notes": position_notes,
            "events": events,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

class Runner:
    """
    回测主循环编排器。

    循环流程：advance → match_orders → assemble_context → agent.decide → record
    """

    def run(self, config: BacktestConfig, agent: AgentProtocol) -> BacktestResult:
        ws = Workspace()
        engine = Engine(
            data=config.data,
            symbol=config.symbol,
            initial_cash=config.initial_cash,
            risk=config.risk,
            commission=config.commission,
            slippage=config.slippage,
        )
        memory = Memory(ws)
        memory.init_playbook(config.strategy_prompt)
        ctx_mgr = ContextManager()
        decisions: list[Decision] = []
        t0 = datetime.now()

        pending_events: list[dict] = []

        while engine.has_next():
            bar = engine.advance()

            # 撮合上一轮提交的订单
            fills = engine.match_orders(bar)
            events = [
                {"type": "fill", "symbol": f.symbol, "side": f.side,
                 "quantity": f.quantity, "price": f.price}
                for f in fills
            ] + pending_events
            pending_events = []

            # 组装上下文
            context = ctx_mgr.assemble(engine, memory, engine._bar_index, events)

            # 工具包（每次决策独立实例）
            toolkit = ToolKit(engine=engine, memory=memory)

            # Agent 决策
            bar_dt = str(context["datetime"])[:10]
            print(f"  bar {engine._bar_index:>3} {bar_dt} ...", end=" ", flush=True)
            decision = agent.decide(context, toolkit)
            print(f"{decision.action:<5}  tokens={decision.tokens_used}", flush=True)
            decisions.append(decision)

            # 持久化决策
            self._record_decision(ws, decision)

        duration = (datetime.now() - t0).total_seconds()

        # 评估
        evaluator = Evaluator()
        performance = evaluator.calc_performance(engine.equity_curve(), engine.trade_log())
        compliance = evaluator.calc_compliance(decisions)

        result = BacktestResult(
            performance=performance,
            compliance=compliance,
            decisions=decisions,
            workspace_path=ws.path,
            config=config,
            duration=duration,
            total_llm_calls=len(decisions),
            total_tokens=sum(d.tokens_used for d in decisions),
        )

        self._save_result(ws, result)
        return result

    def _record_decision(self, ws: Workspace, decision: Decision) -> None:
        jsonl_path = ws.root / "decisions.jsonl"
        record = {
            "datetime": decision.datetime.isoformat() if isinstance(decision.datetime, datetime) else str(decision.datetime),
            "bar_index": decision.bar_index,
            "action": decision.action,
            "symbol": decision.symbol,
            "quantity": decision.quantity,
            "reasoning": decision.reasoning,
            "tokens_used": decision.tokens_used,
        }
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save_result(self, ws: Workspace, result: BacktestResult) -> None:
        result_path = ws.root / "result.json"
        summary = {
            "total_return": result.performance.total_return,
            "max_drawdown": result.performance.max_drawdown,
            "sharpe_ratio": result.performance.sharpe_ratio,
            "total_trades": result.performance.total_trades,
            "workspace_path": result.workspace_path,
            "duration": result.duration,
        }
        result_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
