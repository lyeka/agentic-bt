from __future__ import annotations

from pathlib import Path

import pytest

from athenaclaw.automation.policy import AutomationToolPolicy
from athenaclaw.kernel import Kernel
from athenaclaw.trading import (
    AllowAllGuard,
    RiskAction,
    RiskContext,
    RiskDecision,
    SubmitLimitOrderIntent,
    TradeAccountDescriptor,
    TradeAccountSummary,
    TradeAuditLog,
    TradeCapabilities,
    TradeOpenOrder,
    TradeOrchestrator,
    TradeOrderSnapshot,
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
        self.preview_normalized_limit_price: float | None = None
        self.preview_normalization_reason: str | None = None
        self.order_status_sequence: list[str] | None = None
        self._order_status_reads = 0

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
        status = self._current_order_status()
        if status in {"filled", "cancelled", "rejected", "expired"}:
            return []
        return [
            TradeOpenOrder(
                order_ref=self.order_ref,
                account_ref=self.account_ref,
                symbol="AAPL",
                side="buy",
                quantity=10,
                filled_quantity=10 if status == "filled" else 0,
                limit_price=180.0,
                status=status,
                submitted_at="2026-03-28T00:00:00+00:00",
            )
        ]

    def get_order_status(self, order_ref: str):
        assert order_ref == self.order_ref
        status = self._current_order_status()
        self._order_status_reads += 1
        return TradeOrderSnapshot(
            order_ref=self.order_ref,
            account_ref=self.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            filled_quantity=10 if status == "filled" else 0,
            limit_price=180.0,
            status=status,
            submitted_at="2026-03-28T00:00:00+00:00",
            updated_at="2026-03-28T00:00:05+00:00",
        )

    def submit_limit_order(self, intent: SubmitLimitOrderIntent):
        assert intent.account_ref == self.account_ref
        if self.preview_normalized_limit_price is not None:
            assert intent.limit_price == self.preview_normalized_limit_price
        self._submitted = True
        return TradeReceipt(
            order_ref=self.order_ref,
            status="submitted",
            submitted_at="2026-03-28T00:00:00+00:00",
            broker_order_id="9001",
        )

    def cancel_order(self, order_ref: str):
        assert order_ref == self.order_ref
        return TradeReceipt(
            order_ref=self.order_ref,
            status="unknown",
            submitted_at="2026-03-28T00:00:01+00:00",
            broker_order_id="9001",
        )

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
        return TradePreview(
            warnings=("order_session=RTH",),
            max_buy=100.0,
            max_sell=0.0,
            normalized_limit_price=self.preview_normalized_limit_price or intent.limit_price,
            normalization_reason=self.preview_normalization_reason,
        )

    def _current_order_status(self) -> str:
        if self.order_status_sequence:
            index = min(self._order_status_reads, len(self.order_status_sequence) - 1)
            return self.order_status_sequence[index]
        return "filled" if self._submitted else "submitted"


class _DenyGuard:
    """总是拒绝的 RiskGuard 测试替身 —— 验证 guard-gate 与审计日志的接线。"""

    def __init__(self, reason: str = "risk denied") -> None:
        self.reason = reason
        self.seen: list[RiskContext] = []

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        self.seen.append(ctx)
        return RiskDecision(RiskAction.DENY, self.reason)


def _make_orchestrator(tmp_path: Path, *, guard=None) -> tuple[TradeOrchestrator, _FakeTradeAdapter]:
    adapter = _FakeTradeAdapter()
    orchestrator = TradeOrchestrator(
        adapter=adapter,
        guard=guard or AllowAllGuard(),
        audit_log=TradeAuditLog(tmp_path / "state"),
        cancel_confirm_delays=(0.0, 0.0, 0.0),
    )
    return orchestrator, adapter


def test_trade_orchestrator_execute_limit_submits_and_finalizes(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    adapter.preview_normalized_limit_price = 174.03
    adapter.preview_normalization_reason = "fallback_us_default"

    result = orchestrator.execute_limit(
        account_ref=adapter.account_ref,
        symbol="AAPL",
        side="buy",
        quantity=10,
        limit_price=174.034,
    )

    assert adapter.preview_calls == 1
    assert result.operation == "submit_limit"
    assert result.finalized is True
    assert result.order_status is not None
    assert result.order_status.status == "filled"
    assert result.account_snapshot is not None
    assert result.account_snapshot.positions[0].quantity == 10
    assert "normalized from 174.034 to 174.03" in result.warnings[0]
    assert tuple(result.warnings[1:]) == ("order_session=RTH",)


def test_trade_orchestrator_rejects_preview_failure(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    adapter.preview_error = TradeError(
        TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED,
        "当前账户不支持交易 AAPL",
    )

    with pytest.raises(TradeError) as exc:
        orchestrator.execute_limit(
            account_ref=adapter.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            limit_price=180,
        )

    assert adapter.preview_calls == 1
    assert exc.value.code == TradeErrorCode.ACCOUNT_MARKET_UNSUPPORTED


def test_trade_orchestrator_guard_deny_blocks_submit_and_is_audited(tmp_path):
    guard = _DenyGuard("real 大额禁止裸奔")
    orchestrator, adapter = _make_orchestrator(tmp_path, guard=guard)

    with pytest.raises(TradeError) as exc:
        orchestrator.execute_limit(
            account_ref=adapter.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            limit_price=180,
        )

    assert exc.value.code == TradeErrorCode.PERMISSION_DENIED
    assert exc.value.message == "real 大额禁止裸奔"
    # DENY 时订单不应真的提交到 broker
    assert adapter._submitted is False
    # guard 收到的 RiskContext 携带了完整意图，供未来风控专题消费
    assert guard.seen[-1].operation == "submit_limit"
    assert guard.seen[-1].env == "simulate"
    assert guard.seen[-1].automation is False


def test_trade_orchestrator_guard_deny_blocks_cancel(tmp_path):
    guard = _DenyGuard()
    orchestrator, adapter = _make_orchestrator(tmp_path, guard=guard)
    adapter._submitted = True
    adapter.order_status_sequence = ["submitted"]

    with pytest.raises(TradeError) as exc:
        orchestrator.execute_cancel(order_ref=adapter.order_ref)

    assert exc.value.code == TradeErrorCode.PERMISSION_DENIED
    assert guard.seen[-1].operation == "cancel"


def test_trade_orchestrator_execute_limit_passes_automation_flag_through(tmp_path):
    guard = _DenyGuard()
    orchestrator, adapter = _make_orchestrator(tmp_path, guard=guard)

    with pytest.raises(TradeError):
        orchestrator.execute_limit(
            account_ref=adapter.account_ref,
            symbol="AAPL",
            side="buy",
            quantity=10,
            limit_price=180,
            automation=True,
        )

    assert guard.seen[-1].automation is True


def test_trade_orchestrator_execute_cancel_non_finalized_returns_warning(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    adapter._submitted = True
    adapter.order_status_sequence = ["submitted", "submitted", "submitted", "submitted"]

    result = orchestrator.execute_cancel(order_ref=adapter.order_ref)

    assert result.operation == "cancel"
    assert result.finalized is False
    assert tuple(result.warnings) == ("cancel_requested_not_finalized",)
    assert result.order_status is not None
    assert result.order_status.status == "submitted"
    assert "撤单请求已发送" in result.result_summary


def test_trade_tools_inject_active_account_snapshot(tmp_path):
    orchestrator, adapter = _make_orchestrator(tmp_path)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)

    positions = kernel._tools["trade_account"].handler({"action": "get_positions", "account_ref": adapter.account_ref})
    assert positions["status"] == "ok"
    account = kernel.data.get("account")
    assert account["account_ref"] == adapter.account_ref
    assert account["cash"] == 1000.0
    assert account["positions"]["AAPL"]["quantity"] == 0

    executed = kernel._tools["trade_execute"].handler(
        {
            "operation": "submit_limit",
            "account_ref": adapter.account_ref,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "limit_price": 180,
        }
    )
    assert executed["status"] == "ok"
    account = kernel.data.get("account")
    assert account["positions"]["AAPL"]["quantity"] == 10
    assert kernel.data.get("trade:last_result")["plan_id"] == executed["plan_id"]


def test_trade_tools_missing_refs_return_missing_error_codes(tmp_path):
    orchestrator, _adapter = _make_orchestrator(tmp_path)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)

    open_orders = kernel._tools["trade_account"].handler({"action": "get_open_orders"})
    assert open_orders["error_code"] == "missing_account_ref"

    order_status = kernel._tools["trade_account"].handler({"action": "get_order_status"})
    assert order_status["error_code"] == "missing_order_ref"

    cancel = kernel._tools["trade_execute"].handler({"operation": "cancel"})
    assert cancel["error_code"] == "missing_order_ref"


def test_trade_tools_execute_reports_permission_denied(tmp_path):
    guard = _DenyGuard("simulate 也不放行")
    orchestrator, adapter = _make_orchestrator(tmp_path, guard=guard)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)

    result = kernel._tools["trade_execute"].handler(
        {
            "operation": "submit_limit",
            "account_ref": adapter.account_ref,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "limit_price": 180,
        }
    )
    assert result["error_code"] == "permission_denied"


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
    assert "trade_execute" in kernel._system_prompt
    assert "自主交易操作员" in kernel._system_prompt
    assert "portfolio.json" in kernel._system_prompt
    assert "必须显式携带 account_ref 或 order_ref" in kernel._system_prompt
    assert "不能理解为当前市场状态" in kernel._system_prompt


def test_automation_policy_allows_trade_execute_but_denies_hard_blocked_tools(tmp_path):
    policy = AutomationToolPolicy(
        workspace=tmp_path / "workspace",
        task_id="task-1",
        profile="analysis",
    )

    assert policy.authorize("trade_account", {"action": "list_accounts"}) is None
    # 彻底自主：automation reaction 现在可以直接执行交易
    assert policy.authorize("trade_execute", {"operation": "submit_limit"}) is None
    assert "禁止调用工具" in str(policy.authorize("bash", {}))
    assert "禁止调用工具" in str(policy.authorize("create_subagent", {}))


def test_trade_execute_marks_automation_context_from_automation_tool_policy(tmp_path):
    guard = _DenyGuard()
    orchestrator, adapter = _make_orchestrator(tmp_path, guard=guard)
    kernel = Kernel(api_key="test")
    register_trade_tools(kernel, orchestrator)
    kernel.set_tool_policy(
        AutomationToolPolicy(workspace=tmp_path / "workspace", task_id="task-1", profile="analysis")
    )

    kernel._tools["trade_execute"].handler(
        {
            "operation": "submit_limit",
            "account_ref": adapter.account_ref,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "limit_price": 180,
        }
    )

    assert guard.seen[-1].automation is True
