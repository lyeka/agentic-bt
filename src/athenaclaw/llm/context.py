"""
[INPUT]: json, dataclasses, typing, agent.messages, agent.providers
[OUTPUT]: estimate_tokens, ContextInfo, context_info, CompactResult, compact_history
[POS]: 上下文管理纯函数层，零框架依赖，被 Kernel 和适配器调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from athenaclaw.llm.messages import count_attachment_tokens, extract_text, normalize_history
from athenaclaw.llm.providers import OpenAIChatProvider

# ─────────────────────────────────────────────────────────────────────────────
# Token 估算
# ─────────────────────────────────────────────────────────────────────────────

def estimate_tokens(messages: list[dict]) -> int:
    """粗估 token 数：json 序列化字节数 // 4"""
    if not messages:
        return 0
    normalized = normalize_history(messages)
    text_like = [
        {**m, "content": extract_text(m)} if m.get("role") == "user" else m
        for m in normalized
    ]
    text_tokens = len(json.dumps(text_like, ensure_ascii=False).encode("utf-8")) // 4
    attachment_tokens = sum(count_attachment_tokens(m) for m in normalized)
    return text_tokens + attachment_tokens


# ─────────────────────────────────────────────────────────────────────────────
# 上下文统计
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContextInfo:
    message_count: int
    user_message_count: int
    estimated_tokens: int
    context_window: int
    usage_pct: float


def context_info(history: list[dict], context_window: int) -> ContextInfo:
    """计算上下文统计信息"""
    est = estimate_tokens(history)
    user_count = sum(1 for m in history if m.get("role") == "user")
    return ContextInfo(
        message_count=len(history),
        user_message_count=user_count,
        estimated_tokens=est,
        context_window=context_window,
        usage_pct=round(est / context_window * 100, 1) if context_window > 0 else 0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 压缩
# ─────────────────────────────────────────────────────────────────────────────

_COMPRESS_PROMPT = """\
你是对话压缩器。将以下对话历史压缩为结构化摘要，供后续对话中恢复上下文。

严格按以下格式输出，空段落可省略：

## 会话意图
一句话说明用户的核心目标。

## 关键数据
- 保留所有精确的标识符、股票代码、数值、路径、配置、错误消息
- 格式：`标签: 值`

## 进展
- 已完成的事项和关键决策，每项一行

## 当前状态
最后一步在做什么，结果是什么。

## 用户偏好
- 用户表达的偏好、纠正、反馈

规则：
- 每个段落简洁有力，不超过 3 行
- 丢弃寒暄、确认、中间试错过程、已持久化的工具输出详情
- 保留所有数值和标识符原样（verbatim）
- 优先保留最近的内容
- 工具调用结果只保留结论，丢弃原始数据"""


@dataclass(frozen=True)
class CompactResult:
    summary: str
    retained: list[dict]
    compressed_count: int
    retained_count: int


def compact_history(
    *,
    provider: object | None = None,
    client: object | None = None,
    model: str,
    history: list[dict],
    recent_turns: int = 3,
) -> CompactResult:
    """
    压缩对话历史：旧消息→结构化摘要，保留最近 N 个 user turn 原样。

    "user turn" = 一条 user 消息 + 其后所有非 user 消息，直到下一条 user 消息。
    按 user 消息位置切分，天然保证不从 tool_calls/tool_responses 中间切断。
    """
    # 找出所有 user 消息的位置
    user_idxs = [i for i, m in enumerate(history) if m.get("role") == "user"]

    # 不够切分 → 全部保留，无压缩
    if len(user_idxs) <= recent_turns:
        return CompactResult(
            summary="",
            retained=list(history),
            compressed_count=0,
            retained_count=len(history),
        )

    # 切分点：倒数第 recent_turns 条 user 消息
    cut = user_idxs[-recent_turns]
    to_compress = history[:cut]
    retained = history[cut:]

    # LLM 压缩（含 fallback）
    use_provider = provider or OpenAIChatProvider(client=client)
    summary = _llm_compress(use_provider, model, to_compress)

    return CompactResult(
        summary=summary,
        retained=list(retained),
        compressed_count=len(to_compress),
        retained_count=len(retained),
    )


def _llm_compress(provider: object, model: str, messages: list[dict]) -> str:
    """调用 LLM 压缩消息段，失败时退化为空摘要（等同截断）"""
    conversation_text = "\n".join(
        f"[{m.get('role', '?')}]: {extract_text(m)}" for m in normalize_history(messages)
    )
    try:
        response = provider.complete(  # type: ignore[union-attr]
            model=model,
            messages=[
                {"role": "system", "content": _COMPRESS_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
        )
        return str(response.assistant_message.get("content") or "")
    except Exception:
        # LLM 失败 → 退化为截断，丢弃旧消息
        return ""
