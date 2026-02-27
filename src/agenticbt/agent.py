"""
[INPUT]: openai, agenticbt.models, agenticbt.tools, agenticbt.tracer
[OUTPUT]: LLMAgent — ReAct loop 实现（含三层 System Prompt 架构 + 指数退避重试 + trace 写入）；AgentProtocol — 接口定义
[POS]: Agent 层，唯一直接调用 LLM API 的组件，被 runner 驱动；_build_system_prompt() 组装框架模板+策略；_call_llm() 封装重试逻辑
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
from .tracer import TraceWriter


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
        trace: TraceWriter | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",  # 防止 SDK 因缺少 key 报错
        )
        self._temperature = temperature
        self.trace = trace
        self._custom_system_prompt = system_prompt

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        """ReAct loop：工具调用 → 继续，stop → 终止"""
        t0 = time.time()
        system = self._build_system_prompt(context.playbook)
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": context.formatted_text},
        ]
        final_text = ""
        total_tokens = 0
        last_reasoning = ""

        for round_num in range(1, self.max_rounds + 1):
            t_llm = time.time()
            response = self._call_llm(messages, toolkit.schemas)
            llm_ms = (time.time() - t_llm) * 1000
            if response is None:
                break
            choice = response.choices[0]
            round_tokens = response.usage.total_tokens if response.usage else 0
            total_tokens += round_tokens
            messages.append(choice.message)

            # 捕获 LLM 推理文本（tool_calls 轮次也可能带 content）
            if choice.message.content:
                last_reasoning = choice.message.content

            # 追踪：LLM 调用
            if self.trace:
                self.trace.write({
                    "type": "llm_call",
                    "round": round_num,
                    "model": self.model,
                    "input_messages": _safe_messages(messages[:-1]),
                    "output_content": choice.message.content,
                    "output_tool_calls": _safe_tool_calls(choice.message.tool_calls),
                    "finish_reason": choice.finish_reason,
                    "tokens": {
                        "input": response.usage.prompt_tokens if response.usage else 0,
                        "output": response.usage.completion_tokens if response.usage else 0,
                        "total": round_tokens,
                    },
                    "duration_ms": llm_ms,
                })

            if choice.finish_reason == "stop":
                final_text = choice.message.content or ""
                break

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    t_tool = time.time()
                    result = toolkit.execute(tc.function.name, args)
                    tool_ms = (time.time() - t_tool) * 1000

                    # 追踪：工具调用
                    if self.trace:
                        self.trace.write({
                            "type": "tool_call",
                            "round": round_num,
                            "tool": tc.function.name,
                            "input": args,
                            "output": result,
                            "duration_ms": tool_ms,
                        })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    })
        else:
            # max_rounds 耗尽，用最后一次 LLM 推理；无推理则标记强制 hold
            final_text = (
                f"[max_rounds={self.max_rounds} 耗尽，强制 hold] {last_reasoning}"
                if last_reasoning
                else f"超过最大轮次（{self.max_rounds}轮），强制 hold"
            )

        latency_ms = (time.time() - t0) * 1000
        return self._build_decision(context, toolkit, final_text, total_tokens, latency_ms)

    # ─────────────────────────────────────────────────────────────────────────
    # System Prompt 构建
    # ─────────────────────────────────────────────────────────────────────────

    def _build_system_prompt(self, strategy: str) -> str:
        """三级自定义：默认框架模板 / 自定义含 {strategy} 占位 / 完全覆盖"""
        if self._custom_system_prompt:
            if "{strategy}" in self._custom_system_prompt:
                return self._custom_system_prompt.replace("{strategy}", strategy)
            return self._custom_system_prompt
        return self._build_framework_prompt() + f"\n\n<strategy>\n{strategy}\n</strategy>"

    @staticmethod
    def _build_framework_prompt() -> str:
        """框架级 system prompt 模板 — 策略无关的通用基础设施"""
        return """\
<identity>
你是一位专业的 AI 交易员。
你根据交易策略分析市场、做出交易决策。
你的每个决策都会被完整记录和评估。
</identity>

<environment>
- 每根 K 线你会被要求做一次决策
- 你的交易指令由执行引擎处理，受风控规则约束
- 风控拒绝时会返回原因和建议，据此调整即可
- 你只能基于当前和历史数据做决策
</environment>

<context_awareness>
- 当前行情和账户数据已在下方提供，无需调用 market_observe 和 account_status 重复获取
- compute 工具中 df 已包含截止当前 bar 的完整 OHLCV 数据
- 不要在一次决策中反复调用同一工具获取相同数据
</context_awareness>

<tools_guide>
分析阶段：
  compute — Python 计算终端，推荐一次性计算多个指标（每次调用独立沙箱，变量不跨调用保留）
  indicator_calc — 单指标快捷计算（适合只需一个指标的场景）
  market_history — 完整 OHLCV 历史（仅当需要比 df 更细粒度分析时使用）

执行阶段：
  trade_execute — 执行交易（buy/sell/close），支持 market/limit/stop/bracket
  观望时不要调用此工具，直接输出分析即可

记忆阶段：
  memory_log — 记录决策日志
  memory_note — 创建/更新主题笔记（如持仓理由）
  memory_recall — 检索历史记忆

管理工具：
  order_query / order_cancel — 管理挂单
  market_observe — 查询指定 symbol 行情（仅多资产场景需要）
  account_status — 查询最新账户状态（仅需确认最新变化时使用）
</tools_guide>

<decision_protocol>
1. 分析：用工具获取关键指标，结合策略规则判断
2. 决策：明确 buy/sell/close/hold，给出理由
3. 执行：交易则调用 trade_execute，观望则直接输出分析
4. 记录：交易后用 memory_log 记录理由

先分析，再决策。不确定时观望优于盲目交易。
不要编造数据，所有数值必须来自工具返回或上下文注入。
</decision_protocol>"""

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


# ─────────────────────────────────────────────────────────────────────────────
# Trace 序列化辅助
# ─────────────────────────────────────────────────────────────────────────────

def _safe_messages(messages: list) -> list[dict]:
    """将 messages 列表转为 JSON-safe dict（处理 OpenAI 对象）"""
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        else:
            result.append({"role": getattr(m, "role", "?"),
                           "content": getattr(m, "content", "")})
    return result


def _safe_tool_calls(tool_calls: list | None) -> list[dict] | None:
    """将 OpenAI tool_call 对象转为 JSON-safe list"""
    if not tool_calls:
        return None
    return [
        {"id": getattr(tc, "id", ""),
         "name": tc.function.name,
         "args": tc.function.arguments}
        for tc in tool_calls
    ]

