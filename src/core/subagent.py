"""
[INPUT]: dataclasses, json, time
[OUTPUT]: SubAgentDef, SubAgentResult, filter_schemas, run_subagent
[POS]: 领域无关的 Sub-Agent 纯函数层：数据类型 + 通用 ReAct loop + 资源管控。不依赖 agent 包
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from agent.providers import OpenAIChatProvider


# ─────────────────────────────────────────────────────────────────────────────
# 数据类型
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SubAgentDef:
    """Sub-Agent 定义——身份 + 工具约束 + 资源预算"""

    name: str
    description: str
    system_prompt: str
    output_guide: str | None = None
    tools: list[str] | None = None          # 白名单，None = 全部
    blocked_tools: list[str] | None = None  # 黑名单
    model: str | None = None                # None = 继承父级
    max_rounds: int = 10
    token_budget: int = 50_000
    timeout_seconds: int = 120
    temperature: float = 0.0


@dataclass
class SubAgentResult:
    """Sub-Agent 执行结果——回复 + 质量元数据"""

    response: str
    tool_calls: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    rounds: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 工具过滤
# ─────────────────────────────────────────────────────────────────────────────

# 子代理永远不能调用的工具（防递归）
_ALWAYS_BLOCKED = {"create_subagent", "list_subagents", "remove_subagent"}


def filter_schemas(
    schemas: list[dict],
    *,
    allowed: list[str] | None = None,
    blocked: list[str] | None = None,
) -> list[dict]:
    """
    按白名单 / 黑名单过滤 OpenAI tool schemas。

    allowed=None 表示允许全部；blocked 叠加 _ALWAYS_BLOCKED。
    ask_* 工具始终被拦截，防止子代理间递归委派。
    """
    block_set = _ALWAYS_BLOCKED | set(blocked or [])
    result = []
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        if name in block_set or name.startswith("ask_"):
            continue
        if allowed is not None and name not in allowed:
            continue
        result.append(schema)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 通用 ReAct loop
# ─────────────────────────────────────────────────────────────────────────────

def _build_system_prompt(defn: SubAgentDef) -> str:
    """组装 Sub-Agent system prompt：身份 + 可选 output_protocol"""
    parts = [defn.system_prompt]
    if defn.output_guide:
        parts.append(f"\n<output_protocol>\n{defn.output_guide}\n</output_protocol>")
    return "\n".join(parts)


def run_subagent(
    *,
    definition: SubAgentDef,
    task: str,
    context: str = "",
    provider: Any | None = None,
    client: Any | None = None,
    model: str,
    tool_schemas: list[dict],
    tool_executor: Callable[[str, dict], Any],
    emit_fn: Callable[[str, Any], None] | None = None,
) -> SubAgentResult:
    """
    执行 Sub-Agent 的独立 ReAct loop。

    保证：
    1. 始终返回 SubAgentResult（不抛异常）
    2. LLM API 异常 → 3 次指数退避
    3. token_budget / timeout / max_rounds 资源管控
    """
    defn = definition
    use_provider = provider or OpenAIChatProvider(client=client)
    use_model = defn.model or model
    system = _build_system_prompt(defn)

    # 组装 user message
    user_content = task
    if context:
        user_content = f"<context>\n{context}\n</context>\n\n{task}"

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    schemas = filter_schemas(
        tool_schemas,
        allowed=defn.tools,
        blocked=defn.blocked_tools,
    )

    total_tokens = 0
    all_tool_calls: list[dict] = []
    response_text = ""
    last_reasoning = ""
    budget_exhausted = False
    timed_out = False
    round_num = 0
    t0 = time.time()
    run_id = f"{defn.name}-{uuid4().hex[:12]}"

    if emit_fn:
        emit_fn("subagent.start", {
            "name": defn.name,
            "run_id": run_id,
            "task": task,
            "has_context": bool(context),
            "max_rounds": defn.max_rounds,
            "token_budget": defn.token_budget,
            "timeout_seconds": defn.timeout_seconds,
        })

    for round_num in range(1, defn.max_rounds + 1):
        # 超时检查
        elapsed = time.time() - t0
        if elapsed >= defn.timeout_seconds:
            timed_out = True
            response_text = last_reasoning or "[timeout]"
            break

        if emit_fn:
            emit_fn("subagent.round", {
                "name": defn.name,
                "run_id": run_id,
                "round": round_num,
                "max": defn.max_rounds,
            })
            emit_fn("subagent.llm.call.start", {
                "name": defn.name,
                "run_id": run_id,
                "round": round_num,
            })

        # LLM 调用（3 次指数退避）
        llm_response = _call_llm(
            provider=use_provider,
            model=use_model,
            messages=messages,
            tools=schemas or None,
            temperature=defn.temperature,
            emit_fn=emit_fn,
            agent_name=defn.name,
            run_id=run_id,
            round_num=round_num,
        )

        if llm_response is None:
            if emit_fn:
                emit_fn("subagent.llm.call.done", {
                    "name": defn.name,
                    "run_id": run_id,
                    "round": round_num,
                    "finish_reason": "error",
                    "total_tokens": 0,
                })
            response_text = "[error] LLM 调用失败"
            break

        total_tokens += llm_response.usage_total_tokens

        if emit_fn:
            emit_fn("subagent.llm.call.done", {
                "name": defn.name,
                "run_id": run_id,
                "round": round_num,
                "finish_reason": llm_response.finish_reason,
                "total_tokens": llm_response.usage_total_tokens,
            })

        # 捕获推理文本
        content = llm_response.assistant_message.get("content")
        if content:
            last_reasoning = str(content)

        messages.append(dict(llm_response.assistant_message))

        # token 预算检查（优先于 finish_reason，确保元数据准确）
        if total_tokens >= defn.token_budget:
            budget_exhausted = True
            response_text = last_reasoning or str(content or "") or "[budget_exhausted]"
            break

        # 正常结束
        if llm_response.finish_reason == "stop":
            response_text = str(content or "")
            break

        # 工具调用
        if llm_response.tool_calls:
            for tc in llm_response.tool_calls:
                try:
                    args = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    args = {}

                if emit_fn:
                    emit_fn("subagent.tool.call.start", {
                        "name": defn.name,
                        "run_id": run_id,
                        "round": round_num,
                        "tool": tc.name,
                        "args": args,
                    })
                tool_result = tool_executor(tc.name, args)
                all_tool_calls.append({
                    "tool": tc.name,
                    "args": args,
                    "result": tool_result,
                })

                if emit_fn:
                    emit_fn("subagent.tool.call.done", {
                        "name": defn.name,
                        "run_id": run_id,
                        "round": round_num,
                        "tool": tc.name,
                        "result": tool_result,
                    })
                    emit_fn("subagent.tool", {
                        "name": defn.name,
                        "run_id": run_id,
                        "round": round_num,
                        "tool": tc.name,
                    })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str),
                })
    else:
        # max_rounds 耗尽
        response_text = last_reasoning or "[max_rounds exhausted]"

    latency_ms = (time.time() - t0) * 1000

    result = SubAgentResult(
        response=response_text,
        tool_calls=all_tool_calls,
        tokens_used=total_tokens,
        rounds=round_num,
        latency_ms=latency_ms,
        metadata={
            "tools_used": len(all_tool_calls),
            "response_chars": len(response_text),
            "rounds": round_num,
            "timed_out": timed_out,
            "budget_exhausted": budget_exhausted,
            "run_id": run_id,
        },
    )
    if emit_fn:
        emit_fn("subagent.done", {
            "name": defn.name,
            "run_id": run_id,
            "rounds": round_num,
            "tools_used": len(all_tool_calls),
            "tokens_used": total_tokens,
            "latency_ms": latency_ms,
            "timed_out": timed_out,
            "budget_exhausted": budget_exhausted,
            "response_chars": len(response_text),
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# LLM 调用辅助
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm(
    *,
    provider: Any,
    model: str,
    messages: list,
    tools: list | None,
    temperature: float,
    emit_fn: Callable[[str, Any], None] | None = None,
    agent_name: str | None = None,
    run_id: str | None = None,
    round_num: int | None = None,
) -> Any | None:
    """带 3 次指数退避的 LLM 调用"""
    for attempt in range(3):
        try:
            return provider.complete(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )
        except Exception as exc:
            if emit_fn and agent_name and run_id and round_num is not None:
                emit_fn("subagent.llm.call.error", {
                    "name": agent_name,
                    "run_id": run_id,
                    "round": round_num,
                    "attempt": attempt + 1,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)
    return None


def _msg_to_dict(msg: Any) -> dict:
    """兼容测试：OpenAI message 对象 → dict。"""
    d: dict[str, Any] = {"role": msg.role, "content": msg.content}
    reasoning_content = getattr(msg, "reasoning_content", None)
    model_extra = getattr(msg, "model_extra", None)
    if reasoning_content is None and isinstance(model_extra, dict):
        reasoning_content = model_extra.get("reasoning_content")
    if reasoning_content is not None:
        d["reasoning_content"] = reasoning_content
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d
