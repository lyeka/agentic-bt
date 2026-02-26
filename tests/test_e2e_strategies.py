"""
[INPUT]: pytest, agenticbt, examples.strategies
[OUTPUT]: E2E 自动化测试 — 参数化验证 5 个 mock 策略完整回测
[POS]: tests/ 顶层 E2E 测试，不依赖 BDD，直接验证策略端到端可运行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pytest

from agenticbt import BacktestConfig, run
from agenticbt.data import make_sample_data
from agenticbt.models import CommissionConfig
from examples.strategies import STRATEGIES, StrategyDef


# ─────────────────────────────────────────────────────────────────────────────
# 参数化：只测有 mock_cls 的策略
# ─────────────────────────────────────────────────────────────────────────────

MOCK_STRATEGIES = [
    (name, strat)
    for name, strat in STRATEGIES.items()
    if strat.mock_cls is not None
]


def _build_data(strat: StrategyDef):
    """构建策略所需数据"""
    if strat.extra_symbols:
        data = {strat.symbol: make_sample_data(
            strat.symbol, periods=strat.bars,
            seed=strat.seed, regime=strat.regime,
        )}
        for sym, seed in strat.extra_symbols:
            data[sym] = make_sample_data(
                sym, periods=strat.bars,
                seed=seed, regime=strat.regime,
            )
        return data
    return make_sample_data(
        strat.symbol, periods=strat.bars,
        seed=strat.seed, regime=strat.regime,
    )


@pytest.mark.parametrize("name,strat", MOCK_STRATEGIES, ids=[n for n, _ in MOCK_STRATEGIES])
def test_mock_strategy_e2e(name: str, strat: StrategyDef):
    """每个 mock 策略跑完整回测：不崩溃、decisions 非空、performance 字段合理"""
    data = _build_data(strat)
    agent = strat.mock_cls()

    config = BacktestConfig(
        data=data,
        symbol=strat.symbol,
        strategy_prompt=strat.llm_prompt,
        risk=strat.risk,
        commission=CommissionConfig(rate=0.001),
        decision_start_bar=strat.decision_start_bar,
    )

    result = run(config, agent=agent)

    # 基本断言
    assert result.decisions, f"{name}: decisions 不应为空"
    assert result.performance is not None
    assert result.compliance is not None

    # 绩效字段合理性
    p = result.performance
    assert -1.0 <= p.total_return <= 10.0, f"{name}: total_return={p.total_return} 不合理"
    assert 0.0 <= p.max_drawdown <= 1.0, f"{name}: max_drawdown={p.max_drawdown} 不合理"
    assert p.total_trades >= 0

    # 遵循度
    c = result.compliance
    assert c.total_decisions == len(result.decisions)
    assert c.total_decisions > 0


@pytest.mark.parametrize("name,strat", [
    (n, s) for n, s in STRATEGIES.items() if s.mock_cls is None
], ids=[n for n, s in STRATEGIES.items() if s.mock_cls is None])
def test_llm_only_strategy_has_no_mock(name: str, strat: StrategyDef):
    """LLM-only 策略确认无 mock_cls，且有 llm_prompt"""
    assert strat.mock_cls is None
    assert strat.llm_prompt, f"{name}: llm_prompt 不应为空"
