"""
[INPUT]: dataclasses, enum, typing.Protocol
[OUTPUT]: RiskAction, RiskContext, RiskDecision, RiskGuard, AllowAllGuard
[POS]: 交易执行前的风控裁决单点 seam；orchestrator.execute_* 在下单前必须过 guard.evaluate
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class RiskAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"  # 契约预留：real 大额逃生口，未来风控专题落地


@dataclass(frozen=True)
class RiskContext:
    """裁决输入。intent 携带原始下单意图（symbol/side/quantity/limit_price 等），
    automation 标记该次执行是否发生在无人值守的 automation reaction 中——
    这是未来给 automation×real 做 DENY/ESCALATE 的契约点，这期只透传不使用。"""

    operation: str
    env: str
    automation: bool = False
    intent: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "env": self.env,
            "automation": self.automation,
            "intent": self.intent,
        }


@dataclass(frozen=True)
class RiskDecision:
    action: RiskAction
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action.value, "reason": self.reason}


class RiskGuard(Protocol):
    def evaluate(self, ctx: RiskContext) -> RiskDecision: ...


@dataclass
class AllowAllGuard:
    """[TODO 风控专题] 占位护栏，恒 ALLOW，不拦任何单。

    这期用户明确要求不做风控拦截——真实风控是独立的大设计（notional 上限、
    限价偏离市价保护、日内下单频率、单标的集中度、禁买清单……任何单一维度
    都无法满足真实需求），留给后续专题重新设计。

    这个类存在的意义是把 orchestrator.execute_* 里的裁决点固定下来：风控
    专题落地时只需替换这个实现（或注入另一个 RiskGuard），不改动 orchestrator
    与工具层任何一行。契约方向：对 simulate 与 real 都生效；real 大额场景走
    RiskAction.ESCALATE；automation=True（无人值守）场景应优先收紧 real。
    """

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        return RiskDecision(RiskAction.ALLOW)
