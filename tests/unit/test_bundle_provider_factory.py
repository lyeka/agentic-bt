"""
[INPUT]: pathlib, athenaclaw.runtime.bundle
[OUTPUT]: _build_provider 工厂单测（openai 默认 / anthropic 选择）
[POS]: tests/ 单测层，验证 ATHENACLAW_PROVIDER 驱动的 provider 工厂选择
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from pathlib import Path

from athenaclaw.llm.providers import AnthropicProvider, OpenAIChatProvider
from athenaclaw.runtime.bundle import AgentConfig, _build_provider


def _base_config(**overrides) -> AgentConfig:
    fields = dict(
        model="test-model",
        base_url=None,
        api_key="test-key",
        tushare_token=None,
        finnhub_api_key=None,
        market_cn="yfinance",
        market_us="yfinance",
        workspace_dir=Path("/tmp/workspace"),
        state_dir=Path("/tmp/state"),
    )
    fields.update(overrides)
    return AgentConfig(**fields)


def test_build_provider_defaults_to_openai():
    provider = _build_provider(_base_config())
    assert isinstance(provider, OpenAIChatProvider)


def test_build_provider_selects_anthropic_when_configured():
    provider = _build_provider(_base_config(provider="anthropic"))
    assert isinstance(provider, AnthropicProvider)
