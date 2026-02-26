"""
[INPUT]: agenticbt.engine, agenticbt.memory, agenticbt.tools, agenticbt.models, agenticbt.eval, agenticbt.context, agenticbt.tracer
[OUTPUT]: Runner — 回测主循环编排器
[POS]: 顶层编排器，连接 Engine/Memory/Agent/Eval；_trigger_memory_moments() 在成交时写入记忆；内置 TraceWriter 追踪
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .agent import AgentProtocol
from .context import ContextManager
from .engine import Engine
from .eval import Evaluator
from .memory import Memory, Workspace
from .models import BacktestConfig, BacktestResult, Decision
from .tools import ToolKit
from .tracer import TraceWriter, decision_to_dict


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
        ctx_mgr = ContextManager(config.context_config)
        decisions: list[Decision] = []
        t0 = datetime.now()
        trace = TraceWriter(ws.root / "trace.jsonl")
        if hasattr(agent, "trace"):
            agent.trace = trace

        decision_start_bar = config.decision_start_bar
        if decision_start_bar < 0:
            raise ValueError("decision_start_bar 必须 >= 0")

        pending_events: list[dict] = []

        while engine.has_next():
            bar = engine.advance()

            # 撮合上一轮提交的订单；Engine 自产事件，Runner 透传
            engine.match_orders(bar)
            engine_events = engine.drain_events()
            events = [
                {"type": e.type, "order_id": e.order_id, "symbol": e.symbol, **e.detail}
                for e in engine_events
            ] + pending_events
            pending_events = []

            bar_dt = str(bar.datetime)[:10]
            if engine._bar_index < decision_start_bar:
                self._trigger_memory_moments(memory, events, engine._bar_index, bar_dt)
                continue

            # 追踪：agent_step
            trace.set_bar(engine._bar_index)
            trace.write({"type": "agent_step", "dt": bar_dt})

            # 组装上下文（传入已积累的决策历史）
            context = ctx_mgr.assemble(engine, memory, engine._bar_index, events, decisions)

            # 追踪：context
            trace.write({
                "type": "context",
                "formatted_text": context.formatted_text,
                "market": context.market,
                "account": context.account,
            })

            # 工具包（每次决策独立实例）
            toolkit = ToolKit(engine=engine, memory=memory)

            # Agent 决策
            print(f"  bar {engine._bar_index:>3} {bar_dt} ...", end=" ", flush=True)
            decision = agent.decide(context, toolkit)
            print(f"{decision.action:<5}  tokens={decision.tokens_used}", flush=True)
            decisions.append(decision)

            # 追踪：decision
            trace.write({"type": "decision", **decision_to_dict(decision)})

            # F1: 成交事件驱动记忆写入
            self._trigger_memory_moments(memory, events, engine._bar_index, bar_dt)

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

    def _trigger_memory_moments(
        self,
        memory: Memory,
        events: list[dict],
        bar_index: int,
        bar_dt: str,
    ) -> None:
        """F1: 成交事件自动写入记忆日志，帮助 Agent 从历史成交中学习"""
        for e in events:
            if e["type"] == "fill":
                memory.log(
                    f"[bar={bar_index} {bar_dt}] "
                    f"成交: {e['side']} {e['symbol']} {e['quantity']}股 @ {e['price']:.2f}"
                )

    def _record_decision(self, ws: Workspace, decision: Decision) -> None:
        jsonl_path = ws.root / "decisions.jsonl"
        record = decision_to_dict(decision)
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

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
