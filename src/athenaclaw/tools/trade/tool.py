"""
[INPUT]: athenaclaw.kernel, athenaclaw.trading
[OUTPUT]: register()
[POS]: 交易工具层；暴露 trade_account/trade_plan/trade_apply 给 LLM
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from typing import Any

from athenaclaw.trading import TradeError, TradeErrorCode, error_payload
from athenaclaw.trading.snapshots import build_kernel_account


def register(kernel: object, orchestrator: object) -> None:
    def _missing_account_ref() -> dict[str, Any]:
        return error_payload(TradeError(TradeErrorCode.MISSING_ACCOUNT_REF, "缺少参数: account_ref"))

    def _missing_order_ref() -> dict[str, Any]:
        return error_payload(TradeError(TradeErrorCode.MISSING_ORDER_REF, "缺少参数: order_ref"))

    def trade_account_handler(args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").strip().lower()
        try:
            if action == "list_accounts":
                accounts = orchestrator.list_accounts()
                return {"status": "ok", "accounts": [item.to_dict() for item in accounts]}
            if action == "get_positions":
                account_ref = str(args.get("account_ref") or "").strip()
                if not account_ref:
                    return _missing_account_ref()
                snapshot = orchestrator.get_positions(account_ref)
                kernel.data.set("account", build_kernel_account(snapshot))
                kernel.data.set(f"account:{account_ref}", snapshot.to_dict())
                return {"status": "ok", "account_snapshot": snapshot.to_dict(), "active_account_ref": account_ref}
            if action == "get_open_orders":
                account_ref = str(args.get("account_ref") or "").strip()
                if not account_ref:
                    return _missing_account_ref()
                orders = orchestrator.get_open_orders(account_ref)
                return {"status": "ok", "account_ref": account_ref, "orders": [item.to_dict() for item in orders]}
            if action == "get_order_status":
                order_ref = str(args.get("order_ref") or "").strip()
                if not order_ref:
                    return _missing_order_ref()
                order = orchestrator.get_order_status(order_ref)
                return {"status": "ok", "order": order.to_dict()}
            if action == "get_summary":
                account_ref = str(args.get("account_ref") or "").strip()
                if not account_ref:
                    return _missing_account_ref()
                summary = orchestrator.get_summary(account_ref)
                if summary is None:
                    return {"status": "unsupported", "error": "当前 broker 不支持账户摘要"}
                current = kernel.data.get("account")
                if isinstance(current, dict) and current.get("account_ref") == account_ref:
                    current["cash"] = summary.cash
                    current["equity"] = summary.equity
                    current["updated_at"] = summary.updated_at
                    kernel.data.set("account", current)
                return {"status": "ok", "account_ref": account_ref, "summary": summary.to_dict()}
        except TradeError as exc:
            return error_payload(exc)
        return {"error": "未知 action，可用值: list_accounts/get_positions/get_open_orders/get_order_status/get_summary"}

    def trade_plan_handler(args: dict[str, Any]) -> dict[str, Any]:
        operation = str(args.get("operation") or "").strip().lower()
        try:
            if operation == "submit_limit":
                account_ref = str(args.get("account_ref") or "").strip()
                if not account_ref:
                    return _missing_account_ref()
                plan = orchestrator.plan_submit_limit(
                    account_ref=account_ref,
                    symbol=str(args.get("symbol") or "").strip(),
                    side=str(args.get("side") or "").strip(),
                    quantity=float(args.get("quantity")),
                    limit_price=float(args.get("limit_price")),
                )
                return {"status": "ok", **plan.to_dict()}
            if operation == "cancel":
                order_ref = str(args.get("order_ref") or "").strip()
                if not order_ref:
                    return _missing_order_ref()
                plan = orchestrator.plan_cancel(order_ref=order_ref)
                return {"status": "ok", **plan.to_dict()}
        except (TypeError, ValueError):
            return {"error": "trade_plan 参数不合法"}
        except TradeError as exc:
            return error_payload(exc)
        return {"error": "未知 operation，可用值: submit_limit/cancel"}

    def trade_apply_handler(args: dict[str, Any]) -> dict[str, Any]:
        plan_id = str(args.get("plan_id") or "").strip()
        if not plan_id:
            return {"error": "缺少参数: plan_id"}
        record = orchestrator.get_plan(plan_id)
        if record is None:
            return {"error": f"未找到 plan: {plan_id}", "error_code": "plan_not_found"}
        plan = record["plan"]
        confirm_text = str(plan.get("confirm_text") or f"确认执行 {plan_id} 吗？")
        if not kernel.request_confirm(confirm_text):
            return {"status": "cancelled", "plan_id": plan_id, "message": "用户取消确认"}
        try:
            result = orchestrator.apply(plan_id)
        except TradeError as exc:
            return error_payload(exc)

        if result.account_snapshot is not None:
            kernel.data.set("account", build_kernel_account(result.account_snapshot))
            kernel.data.set(f"account:{result.account_snapshot.account_ref}", result.account_snapshot.to_dict())
        if result.order_status is not None:
            kernel.data.set("trade:last_order", result.order_status.to_dict())
        kernel.data.set("trade:last_result", result.to_dict())
        return {"status": "ok", **result.to_dict()}

    kernel.tool(
        name="trade_account",
        description=(
            "读取远端 broker 账户状态。支持列可用账户、读取当前持仓、未完成订单、单个订单当前状态。"
            "何时使用: 用户要看远端交易账户状态、下单前确认账户、成交后刷新活动账户。"
            "何时不要用: 维护本地 portfolio.json/watchlist.json、讨论交易计划但尚未操作远端账户时。"
            "list_accounts 会返回账户的 supported_markets、account_status、account_kind 以及 provider extra，"
            "用于判断哪个账户支持目标市场、是否可交易、以及 provider 特有的限制信息。"
            "重要限制: 除 list_accounts 外，查询具体账户或订单时必须显式携带 account_ref 或 order_ref；"
            "不会自动承接最近账户、最近订单，也不会给 suggestion。"
            "重要语义: get_positions 成功后，会把该账户快照写入当前会话的 Kernel.data['account']，供后续 compute 使用；"
            "这个 account 只代表当前活动账户，不是多账户容器。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_accounts", "get_positions", "get_open_orders", "get_order_status", "get_summary"],
                },
                "account_ref": {"type": "string", "description": "由 list_accounts 返回的账户引用"},
                "order_ref": {"type": "string", "description": "由订单查询或下单结果返回的订单引用"},
            },
            "required": ["action"],
        },
        handler=trade_account_handler,
    )

    kernel.tool(
        name="trade_plan",
        description=(
            "创建交易执行计划，不直接产生外部副作用。只支持股票/ETF 的 LIMIT 限价单与撤单。"
            "先调用 trade_plan，再调用 trade_apply。不要跳过 plan。"
            "plan 返回的 plan_id 是一次性短期令牌；不要伪造或猜测。"
            "submit_limit 必须显式提供 account_ref，cancel 必须显式提供 order_ref。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["submit_limit", "cancel"]},
                "account_ref": {"type": "string", "description": "submit_limit 使用；由 list_accounts 返回"},
                "symbol": {"type": "string", "description": "submit_limit 使用；标准 symbol，如 AAPL / 00700.HK / 600519.SH"},
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "submit_limit 使用"},
                "quantity": {"type": "number", "description": "submit_limit 使用；必须大于 0"},
                "limit_price": {"type": "number", "description": "submit_limit 使用；必须大于 0"},
                "order_ref": {"type": "string", "description": "cancel 使用；由订单查询或下单结果返回"},
            },
            "required": ["operation"],
        },
        handler=trade_plan_handler,
    )

    kernel.tool(
        name="trade_apply",
        description=(
            "执行 trade_plan 生成的计划。只接受 plan_id，执行前会请求用户确认。"
            "不要把原始下单参数直接传给 trade_apply。"
            "执行成功后会自动刷新订单当前状态；若订单已部分或全部成交，会刷新当前活动账户快照。"
            "status=ok 只表示工具执行成功，不表示订单动作已进入终态；请结合 finalized 与 order_status 判断。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "trade_plan 返回的一次性 plan_id"},
            },
            "required": ["plan_id"],
        },
        handler=trade_apply_handler,
    )
