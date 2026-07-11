# trading/
> L2 | 父级: ../CLAUDE.md

交易边界层：把 Agent 的下单/撤单意图转成确定性、经风控裁决、可执行、可回读的 canonical 流程。自主交易操作员范式——`orchestrator` 由旧的 plan/apply 二段式改为单步 `execute_limit`/`execute_cancel`，中间不经过人工确认。

## 成员清单

types.py: canonical dataclass（`TradeAccountDescriptor`/`TradeAccountSnapshot`/`TradeAccountSummary`/`TradeApplyResult`/`TradeCapabilities`/`TradeOpenOrder`/`TradeOrderSnapshot`/`TradePosition`/`TradePreview`/`TradeReceipt`/`SubmitLimitOrderIntent`）与 `account_ref`/`order_ref` 编解码。`TradeApplyResult.plan_id` 语义已从"待确认计划 id"改为"一次性执行 id"，纯审计用途
errors.py: `TradeErrorCode`/`TradeError`/`error_payload` —— 交易域统一错误语义
protocol.py: `TradeBrokerAdapter` Protocol —— broker adapter 必须实现的公共能力集合
policy.py: `RiskGuard` seam —— `RiskAction`(ALLOW/DENY/ESCALATE)/`RiskContext`(operation/env/automation/intent)/`RiskDecision`/`AllowAllGuard`（这期唯一实现，恒 ALLOW，占位 + TODO，真实风控留后续专题）
orchestrator.py: `TradeOrchestrator` —— 核心编排对象。`execute_limit`/`execute_cancel` 一次调用内完成校验+preview+`guard.evaluate`+下单/撤单+状态回读，guard 裁决与执行结果均写入 `TradeAuditLog`
store.py: `TradeAuditLog` —— 交易审计的轻量持久层（append-only jsonl）
snapshots.py: `build_kernel_account` —— `TradeAccountSnapshot` 到 `Kernel.data["account"]` 的映射

## 安全模型

确认（human-in-the-loop）与风控（risk control）是两件事：交易链路已彻底删除 `request_confirm` 依赖；`RiskGuard.evaluate` 是唯一的程序化安全边界，`orchestrator.execute_*` 在下单/撤单前必调用。这期 `AllowAllGuard` 不拦任何单——真实风控（notional/价格偏离/频率/集中度/禁买清单）是独立专题，`RiskContext.automation` 字段已为 automation×real 场景预留裁决挂钩。

详见 `docs/trading.md`。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
