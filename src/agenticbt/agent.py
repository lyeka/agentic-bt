"""
[INPUT]: openai, agenticbt.models, agenticbt.tools
[OUTPUT]: LLMAgent — ReAct loop 实现（含指数退避重试）；AgentProtocol — 接口定义
[POS]: Agent 层，唯一直接调用 LLM API 的组件，被 runner 驱动；_call_llm() 封装重试逻辑
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Protocol, runtime_checkable

import openai

from .models import Context, Decision, ToolCall
from .tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# AgentProtocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class AgentProtocol(Protocol):
    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
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
        max_rounds: int = 15,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",  # 防止 SDK 因缺少 key 报错
        )
        self._temperature = temperature

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        """ReAct loop：工具调用 → 继续，stop → 终止"""
        t0 = time.time()
        messages = [
            {"role": "system", "content": context.playbook},
            {"role": "user",   "content": context.formatted_text},
        ]
        final_text = ""
        total_tokens = 0

        for _ in range(self.max_rounds):
            # B3: 使用带重试的 LLM 调用
            response = self._call_llm(messages, toolkit.schemas)
            if response is None:
                break
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

    def _call_llm(self, messages: list, tools: list) -> object | None:
        """B3: 带指数退避的 LLM 调用，失败 3 次后返回 None"""
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    temperature=self._temperature,
                )
            except Exception as e:
                if attempt == 2:
                    print(f"  [LLM FATAL] {type(e).__name__}: {e}", flush=True)
                    return None
                wait = 2 ** attempt
                print(f"  [LLM RETRY {attempt + 1}] {type(e).__name__}, wait {wait}s", flush=True)
                time.sleep(wait)
        return None  # unreachable

    def _build_decision(
        self,
        context: Context,
        toolkit: ToolKit,
        reasoning: str,
        tokens: int,
        latency_ms: float,
    ) -> Decision:
        # F2: 提取最后一次交易动作，填充 order_result；多笔交易补充完整链到 reasoning
        action, symbol, quantity, order_result = "hold", None, None, None
        if toolkit.trade_actions:
            last = toolkit.trade_actions[-1]
            action       = last["action"]
            symbol       = last.get("symbol")
            quantity     = last.get("quantity")
            order_result = last.get("result")
            if len(toolkit.trade_actions) > 1:
                summary = "; ".join(
                    f"{t['action']} {t.get('symbol', '?')} {t.get('quantity', '?')}股"
                    for t in toolkit.trade_actions
                )
                reasoning = reasoning + f"\n[全部交易: {summary}]"

        return Decision(
            datetime=context.datetime,
            bar_index=context.bar_index,
            action=action,
            symbol=symbol,
            quantity=quantity,
            reasoning=reasoning,
            market_snapshot=context.market,
            account_snapshot=context.account,
            indicators_used=dict(toolkit.indicator_queries),
            tool_calls=list(toolkit.call_log),
            order_result=order_result,
            model=self.model,
            tokens_used=tokens,
            latency_ms=latency_ms,
        )

