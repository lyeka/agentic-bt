"""
[INPUT]: 所有 agenticbt 子模块
[OUTPUT]: 公共 API: run, BacktestConfig, BacktestResult, LLMAgent, AgentProtocol
[POS]: 包入口，用户唯一需要 import 的模块
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from .agent import AgentProtocol, LLMAgent
from .data import load_csv, make_sample_data
from .models import BacktestConfig, BacktestResult
from .runner import Runner


def run(config: BacktestConfig, agent=None) -> BacktestResult:
    """
    一行启动完整回测。

    Example::

        result = run(BacktestConfig(
            data=df, symbol="AAPL",
            strategy_prompt="RSI < 30 买入, RSI > 70 卖出",
            model="claude-sonnet-4-20250514",
            base_url="https://api.anthropic.com/v1/",
        ))
        print(result.performance)
    """
    if agent is None:
        agent = LLMAgent(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            max_rounds=config.max_agent_rounds,
        )
    return Runner().run(config, agent)


__all__ = [
    "run",
    "BacktestConfig",
    "BacktestResult",
    "LLMAgent",
    "AgentProtocol",
    "Runner",
    "load_csv",
    "make_sample_data",
]
