from __future__ import annotations

import importlib
import sys
from types import ModuleType


def test_build_kernel_bundle_allows_soul_growth_edits(tmp_path, monkeypatch):
    # pandas_ta 是可选依赖；这个测试只验证 runtime 权限，不需要真实实现。
    monkeypatch.setitem(sys.modules, "pandas_ta", ModuleType("pandas_ta"))

    runtime_mod = importlib.import_module("athenaclaw.runtime")

    class DummyAdapter:
        name = "dummy"

        def fetch(self, query):  # pragma: no cover - should not be called
            raise AssertionError("unexpected market fetch")

    monkeypatch.setattr(runtime_mod, "_build_market_adapter", lambda _config: DummyAdapter())

    config = runtime_mod.AgentConfig(
        model="test",
        base_url=None,
        api_key="test",
        tushare_token=None,
        finnhub_api_key=None,
        market_cn="yfinance",
        market_us="yfinance",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        enable_bash=False,
    )

    bundle = runtime_mod.build_kernel_bundle(
        config=config,
        adapter_name="cli",
        conversation_id="demo",
        cwd=tmp_path,
    )

    assert bundle.kernel.check_permission("soul.md").value == "free"
    assert bundle.kernel.check_permission("memory.md").value == "free"


def test_build_kernel_bundle_boots_kernel_from_detected_repo_root(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas_ta", ModuleType("pandas_ta"))

    runtime_mod = importlib.import_module("athenaclaw.runtime")
    bundle_mod = importlib.import_module("athenaclaw.runtime.bundle")

    class DummyAdapter:
        name = "dummy"

        def fetch(self, query):  # pragma: no cover - should not be called
            raise AssertionError("unexpected market fetch")

    repo_root = tmp_path / "host-repo"
    repo_root.mkdir()

    monkeypatch.setattr(runtime_mod, "_build_market_adapter", lambda _config: DummyAdapter())
    monkeypatch.setattr(bundle_mod, "_build_market_adapter", lambda _config: DummyAdapter())
    monkeypatch.setattr(bundle_mod, "_detect_repo_root", lambda _cwd: repo_root)

    config = runtime_mod.AgentConfig(
        model="test",
        base_url=None,
        api_key="test",
        tushare_token=None,
        finnhub_api_key=None,
        market_cn="yfinance",
        market_us="yfinance",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        enable_bash=False,
    )

    bundle = runtime_mod.build_kernel_bundle(
        config=config,
        adapter_name="cli",
        conversation_id="demo",
        cwd=tmp_path / "external-repo",
    )

    assert bundle.kernel._cwd == repo_root
    assert bundle.kernel.data.get("_runtime_paths")["repo_root"] == str(repo_root)


def test_build_kernel_bundle_registers_trade_tools_and_trade_guide(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas_ta", ModuleType("pandas_ta"))

    runtime_mod = importlib.import_module("athenaclaw.runtime")
    bundle_mod = importlib.import_module("athenaclaw.runtime.bundle")

    class DummyMarketAdapter:
        name = "dummy-market"

        def fetch(self, query):  # pragma: no cover - should not be called
            raise AssertionError("unexpected market fetch")

    class DummyTradeAdapter:
        name = "dummy-trade"

        def capabilities(self):
            from athenaclaw.trading import TradeCapabilities

            return TradeCapabilities()

        def list_accounts(self):
            return []

        def get_positions(self, account_ref):
            raise AssertionError("unexpected get_positions")

        def get_open_orders(self, account_ref):
            raise AssertionError("unexpected get_open_orders")

        def get_order_status(self, order_ref):
            raise AssertionError("unexpected get_order_status")

        def submit_limit_order(self, intent):
            raise AssertionError("unexpected submit_limit_order")

        def cancel_order(self, order_ref):
            raise AssertionError("unexpected cancel_order")

        def get_account_summary(self, account_ref):
            return None

        def preview_limit_order(self, intent):
            return None

    monkeypatch.setattr(runtime_mod, "_build_market_adapter", lambda _config: DummyMarketAdapter())
    monkeypatch.setattr(bundle_mod, "_build_market_adapter", lambda _config: DummyMarketAdapter())
    monkeypatch.setattr(runtime_mod, "_build_trade_adapter", lambda _config: DummyTradeAdapter())
    monkeypatch.setattr(bundle_mod, "_build_trade_adapter", lambda _config: DummyTradeAdapter())

    config = runtime_mod.AgentConfig(
        model="test",
        base_url=None,
        api_key="test",
        tushare_token=None,
        finnhub_api_key=None,
        market_cn="yfinance",
        market_us="yfinance",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        enable_bash=False,
        trade_broker="futu",
    )

    bundle = runtime_mod.build_kernel_bundle(
        config=config,
        adapter_name="cli",
        conversation_id="demo",
        cwd=tmp_path,
    )

    assert "trade_account" in bundle.kernel._tools
    assert "trade_plan" in bundle.kernel._tools
    assert "trade_apply" in bundle.kernel._tools
    assert "<trade_tools>" in (bundle.kernel._system_prompt or "")
