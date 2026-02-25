"""
[INPUT]: openai, agenticbt.models, agenticbt.tools
[OUTPUT]: LLMAgent — ReAct loop 实现；AgentProtocol — 接口定义
[POS]: Agent 层，唯一直接调用 LLM API 的组件，被 runner 驱动
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Protocol, runtime_checkable

import openai

from .models import Decision, ToolCall
from .tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# AgentProtocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class AgentProtocol(Protocol):
    def decide(self, context: dict, toolkit: ToolKit) -> Decision:
        """核心决策方法：给定上下文和工具包，返回决策记录"""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# LLMAgent
# ─────────────────────────────────────────────────────────────────────────────

class LLMAgent:
    """
    OpenAI SDK 兼容模式 ReAct loop。

    换提供商 = 改两个参数（base_url + api_key），零代码变更。
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
        api_key: str | None = None,
        max_rounds: int = 5,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",  # 防止 SDK 因缺少 key 报错
        )
        self._temperature = temperature

    def decide(self, context: dict, toolkit: ToolKit) -> Decision:
        """ReAct loop：工具调用 → 继续，stop → 终止"""
        t0 = time.time()
        messages = [{"role": "user", "content": self._format_context(context)}]
        final_text = ""
        total_tokens = 0

        for _ in range(self.max_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=toolkit.schemas,
                temperature=self._temperature,
            )
            choice = response.choices[0]
            total_tokens += response.usage.total_tokens if response.usage else 0
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                final_text = choice.message.content or ""
                break

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    result = toolkit.execute(
                        tc.function.name,
                        json.loads(tc.function.arguments),
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    })
        else:
            # max_rounds 耗尽，强制 hold
            final_text = "超过最大轮次，强制 hold"

        latency_ms = (time.time() - t0) * 1000
        return self._build_decision(context, toolkit, final_text, total_tokens, latency_ms)

    def _format_context(self, context: dict) -> str:
        return json.dumps(context, ensure_ascii=False, default=str, indent=2)

    def _build_decision(
        self,
        context: dict,
        toolkit: ToolKit,
        reasoning: str,
        tokens: int,
        latency_ms: float,
    ) -> Decision:
        # 从 trade_actions 中提取最后一次交易动作
        action, symbol, quantity = "hold", None, None
        if toolkit.trade_actions:
            last = toolkit.trade_actions[-1]
            action = last["action"]
            symbol = last.get("symbol")
            quantity = last.get("quantity")

        return Decision(
            datetime=context.get("datetime", datetime.now()),
            bar_index=context.get("bar_index", 0),
            action=action,
            symbol=symbol,
            quantity=quantity,
            reasoning=reasoning,
            market_snapshot=context.get("market", {}),
            account_snapshot=context.get("account", {}),
            indicators_used=dict(toolkit.indicator_queries),
            tool_calls=list(toolkit.call_log),
            model=self.model,
            tokens_used=tokens,
            latency_ms=latency_ms,
        )
