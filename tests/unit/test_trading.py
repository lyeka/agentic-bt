from __future__ import annotations

from pathlib import Path

import pytest

from athenaclaw.automation.policy import AutomationToolPolicy
from athenaclaw.kernel import Kernel
from athenaclaw.trading import (
    SubmitLimitOrderIntent,
    TradeAccountDescriptor,
    TradeAccountSnapshot,
    TradeAccountSummary,
    TradeAuditLog,
    TradeCapabilities,
    TradeOpenOrder,
    TradeOrchestrator,
    TradeOrderSnapshot,
    TradePlanStore,
    TradePosition,
    TradePreview,
    TradeReceipt,
    TradeError,
    TradeErrorCode,
    encode_account_ref,
    encode_order_ref,
)
from athenaclaw.tools.trade import register as register_trade_tools


class _FakeTradeAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.account_ref = encode_account_ref(broker=self.name, env="simulate", account_id="1001")
        self.order_ref = encode_order_ref(
            broker=self.name,
            env="simulate",
            account_id="1001",
            order_id="9001",
        )
        self._submitted = False
        self.preview_calls = 0
        self.preview_error: TradeError | None = None

    def capabilities(self) -> TradeCapabilities:
        return TradeCapabilities(
            supports_account_summary=True,
            supports_preview_limit_order=True,
        )

    def list_accounts(self):
        return [
            TradeAccountDescriptor(
                account_ref=self.account_ref,
                broker=self.name,
                account_id="1001",
                env="simulate",
                display_name="fake-sim-1001",
                supported_markets=("US",),
                account_status="active",
                account_kind="stock",
                is_simulated=True,
                extra={"sim_acc_type": "STOCK", "trdmarket_auth": ["US"]},
                capabilities=self.capabilities(),
            )
        ]

    def get_positions(self, account_ref: str):
        assert account_ref == self.account_ref
        qty = 10 if self._submitted else 0
        return [TradePosition(symbol="AAPL", quantity=qty, avg_cost=180.0, currency="USD")]

    def get_open_orders(self, account_ref: str):
        assert account_ref == self.account_ref
        if not self._submitted:
            return []
        return [
            TradeOpenOrder(
                order_ref=self.order_ref,
                account_ref=self.account_ref,
                symbol="AAPL",
                side="buy",
                quantity=10,
                filled_quantity=0,
                limit_price=180.0,
                status="submitted",
                submitted_at="2026-03-28T00:00:00+00:00",
            )
        ]

    def get_order_status(self, order_ref: str):
        assert order_ref == self.order_ref
        return TradeOrderSnapshot(
            order_ref=self.order_ref,
            account_ref=self.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            filled_quantity=10 if self._submitted else 0,
            limit_price=180.0,
            status="filled" if self._submitted else "submitted",
            submitted_at="2026-03-28T00:00:00+00:00",
            updated_at="2026-03-28T00:00:05+00:00",
        )

    def submit_limit_order(self, intent: SubmitLimitOrderIntent):
        assert intent.account_ref == self.account_ref
        self._submitted = True
        return TradeReceipt(
            order_ref=self.order_ref,
            status="submitted",
            submitted_at="2026-03-28T00:00:00+00:00",
            broker_order_id="9001",
        )

    def cancel_order(self, order_ref: str):
        raise AssertionError("cancel_order should not be called in this test")

    def get_account_summary(self, account_ref: str):
        assert account_ref == self.account_ref
        return TradeAccountSummary(
            account_ref=account_ref,
            cash=1000.0,
            equity=2800.0,
            currency="USD",
            updated_at="2026-03-28T00:00:00+00:00",
        )

    def preview_limit_order(self, intent: SubmitLimitOrderIntent):
        self.preview_calls += 1
        if self.preview_error is not None:
            raise self.preview_error
        return TradePreview(warnings=("preview-ok",), max_buy=100.0, max_sell=0.0)


def _make_orchestrator(tmp_path: Path) -> tuple[TradeOrchestrator, _FakeTradeAdapter]:
    adapter = _FakeTradeAdapter()
    orchestrator = TradeOrchestrator(
        adapter=adapter,
        plan_store=TradePlanStore(tmp_path / "state"),
        audit_log=TradeAuditLog(tmp_path / "state"),
    )
    return orchestrator, adapter


def test_trade_orchestrator_plan_and_apply_submit_limit(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)

    plan = orchestrator.plan_submit_limit(
        account_ref=adapter.account_ref,
        symbol="AAPL",
        side="buy",
        quantity=10,
        limit_price=180,
    )

    assert adapter.preview_calls == 1
    assert tuple(plan.warnings) == ("preview-ok",)

    result = orchestrator.apply(plan.plan_id)

    assert result.operation == "submit_limit"
    assert result.order_status is not None
    assert result.order_status.status == "filled"
    assert result.account_snapshot is not None
    assert result.account_snapshot.positions[0].quantity == 10
    stored = orchestrator.get_plan(plan.plan_id)
    assert stored is not None
    assert stored["status"] == "applied"


def test_trade_orchestrator_rejects_expired_plan(tmp_path):
    adapter = _FakeTradeAdapter()
    orchestrator = TradeOrchestrator(
        adapter=adapter,
        plan_store=TradePlanStore(tmp_path / "state"),
        audit_log=TradeAuditLog(tmp_path / "state"),
        plan_ttl_sec=-1,
    )

    plan = orchestrator.plan_submit_limit(
        account_ref=adapter.account_ref,
        symbol="AAPL",
        side="buy",
        quantity=10,
        limit_price=180,
    )

    with pytest.raises(TradeError) as exc:
        orchestrator.apply(plan.plan_id)

    assert exc.value.code == TradeErrorCode.PLAN_EXPIRED


def test_trade_orchestrator_rejects_preview_failure_during_plan(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    adapter.preview_error = TradeError(
        TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED,
        "当前账户不支持交易 AAPL",
    )

    with pytest.raises(TradeError) as exc:
        orchestrator.plan_submit_limit(
            account_ref=adapter.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            limit_price=180,
        )

    assert adapter.preview_calls == 1
    assert exc.value.code == TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED


def test_trade_tools_inject_active_account_snapshot(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)
    kernel.on_confirm(lambda message: True)

    positions = kernel._tools["trade_account"].handler({"action": "get_positions", "account_ref": adapter.account_ref})
    assert positions["status"] == "ok"
    account = kernel.data.get("account")
    assert account["account_ref"] == adapter.account_ref
    assert account["cash"] == 1000.0
    assert account["positions"]["AAPL"]["quantity"] == 0

    plan = kernel._tools["trade_plan"].handler(
        {
            "operation": "submit_limit",
            "account_ref": adapter.account_ref,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "limit_price": 180,
        }
    )
    applied = kernel._tools["trade_apply"].handler({"plan_id": plan["plan_id"]})
    assert applied["status"] == "ok"
    account = kernel.data.get("account")
    assert account["positions"]["AAPL"]["quantity"] == 10
    assert kernel.data.get("trade:last_result")["plan_id"] == plan["plan_id"]


def test_trade_account_list_accounts_exposes_account_capabilities_and_extra(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)

    result = kernel._tools["trade_account"].handler({"action": "list_accounts"})
    assert result["status"] == "ok"
    account = result["accounts"][0]
    assert account["account_ref"] == adapter.account_ref
    assert account["supported_markets"] == ["US"]
    assert account["account_status"] == "active"
    assert account["account_kind"] == "stock"
    assert account["is_simulated"] is True
    assert account["extra"]["sim_acc_type"] == "STOCK"


def test_trade_guide_injected_when_trade_tools_registered(tmp_path):
    orchestrator, _adapter = _make_orchestrator(tmp_path)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)
    kernel.boot(tmp_path / "workspace", cwd=tmp_path)

    assert kernel._system_prompt is not None
    assert "<trade_tools>" in kernel._system_prompt
    assert "trade_apply" in kernel._system_prompt
    assert "portfolio.json" in kernel._system_prompt


def test_automation_policy_denies_trade_mutations(tmp_path):
    policy = AutomationToolPolicy(
        workspace=tmp_path / "workspace",
        task_id="task-1",
        profile="analysis",
    )

    assert policy.authorize("trade_account", {"action": "list_accounts"}) is None
    assert "禁止调用工具" in str(policy.authorize("trade_plan", {}))
    assert "禁止调用工具" in str(policy.authorize("trade_apply", {}))
