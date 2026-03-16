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
