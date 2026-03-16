"""
[INPUT]: pytest-bdd, athenaclaw.integrations.market.composite, athenaclaw.tools.market.schema
[OUTPUT]: market_routing.feature step definitions
[POS]: tests/ BDD 测试层，验证 CompositeMarketAdapter 路由逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenario, then, when

from athenaclaw.integrations.market.composite import CompositeMarketAdapter, is_ashare
from athenaclaw.tools.market.schema import build_market_query, make_fetch_result


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────

FEATURE = "features/market_routing.feature"


@scenario(FEATURE, "有匹配路由时走对应 adapter")
def test_route_match(): pass


@scenario(FEATURE, "无匹配路由走 fallback")
def test_route_fallback(): pass


@scenario(FEATURE, "多条路由按注册顺序 first-match-wins")
def test_first_match_wins(): pass


@scenario(FEATURE, "无匹配且无 fallback 抛异常")
def test_no_match_no_fallback(): pass


@scenario(FEATURE, "仅 fallback 处理所有 symbol")
def test_fallback_only(): pass


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-03"]),
        "open": [10.0],
        "high": [11.0],
        "low": [9.0],
        "close": [10.5],
        "volume": [1000],
    })


class FakeAdapter:
    """可追踪调用的 mock adapter"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.called_with: str | None = None

    def fetch(self, query):
        self.called_with = query.normalized_symbol
        return make_fetch_result(
            df=_sample_df(),
            query=query,
            source=self.name,
            timezone=query.timezone,
        )


@pytest.fixture
def mrctx():
    return {"composite": CompositeMarketAdapter(), "adapters": {}}


@given(parsers.parse('注册 "{name}" adapter 匹配 A 股 symbol'))
def given_ashare_route(mrctx, name):
    adapter = FakeAdapter(name)
    mrctx["adapters"][name] = adapter
    mrctx["composite"].route(is_ashare, adapter)


@given(parsers.parse('注册 "{name}" adapter 作为 fallback'))
def given_fallback(mrctx, name):
    adapter = FakeAdapter(name)
    mrctx["adapters"][name] = adapter
    mrctx["composite"].fallback(adapter)


@given(parsers.parse('注册 "{name}" adapter 匹配所有 symbol'))
def given_catch_all(mrctx, name):
    adapter = FakeAdapter(name)
    mrctx["adapters"][name] = adapter
    mrctx["composite"].route(lambda s: True, adapter)


@when(parsers.parse('composite fetch history "{symbol}" interval "{interval}"'))
def when_fetch(mrctx, symbol, interval):
    mrctx["result"] = mrctx["composite"].fetch(
        build_market_query(symbol=symbol, interval=interval, mode="history")
    )


@when(parsers.parse('composite fetch history "{symbol}" interval "{interval}" 无 fallback'))
def when_fetch_no_fallback(mrctx, symbol, interval):
    try:
        mrctx["composite"].fetch(build_market_query(symbol=symbol, interval=interval, mode="history"))
        mrctx["error"] = None
    except ValueError as exc:
        mrctx["error"] = exc


@then(parsers.parse('实际调用的 adapter 是 "{name}"'))
def then_called_adapter(mrctx, name):
    adapter = mrctx["adapters"][name]
    assert adapter.called_with is not None, f"{name} adapter was not called"


@then("抛出 ValueError")
def then_raises(mrctx):
    assert mrctx["error"] is not None
    assert isinstance(mrctx["error"], ValueError)
