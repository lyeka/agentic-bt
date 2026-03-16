"""
[INPUT]: base64, pathlib, typing, openai, agent.messages
[OUTPUT]: LLMProvider, LLMResult, OpenAIChatProvider, provider error helpers
[POS]: LLM provider 抽象层：统一内部消息与 provider SDK 之间的编解码
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import openai

from athenaclaw.llm.messages import extract_text, normalize_history_message, normalize_parts


class ProviderInputError(RuntimeError):
    """统一 provider 输入错误。"""


class UnsupportedMediaError(ProviderInputError):
    """provider 不支持当前媒体类型。"""


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResult:
    assistant_message: dict[str, Any]
    finish_reason: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    usage_total_tokens: int = 0


class LLMProvider(Protocol):
    """统一 LLM provider 最小接口。"""

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> LLMResult: ...


class OpenAIChatProvider:
    """OpenAI-compatible chat.completions provider。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        image_detail: str = "low",
        client: Any | None = None,
    ) -> None:
        self.image_detail = image_detail or "low"
        self.client = client or openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self.compile_messages(messages),
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if _looks_like_unsupported_image(exc):
                raise UnsupportedMediaError("当前 MODEL 不支持图片输入。请切换到支持 vision 的模型。") from exc
            raise

        choice = response.choices[0]
        message = getattr(choice, "message", None)
        tool_calls = [
            LLMToolCall(
                id=str(tc.id),
                name=str(tc.function.name),
                arguments=str(tc.function.arguments),
            )
            for tc in (getattr(message, "tool_calls", None) or [])
        ]
        usage_total_tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
        return LLMResult(
            assistant_message=message_to_dict(message),
            finish_reason=str(getattr(choice, "finish_reason", "") or ""),
            tool_calls=tool_calls,
            usage_total_tokens=int(usage_total_tokens),
        )

    def compile_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compiled: list[dict[str, Any]] = []
        for message in messages:
            normalized = normalize_history_message(message)
            role = str(normalized.get("role", "")).strip()

            if role == "user":
                compiled.append({
                    "role": "user",
                    "content": self._compile_user_parts(normalized.get("parts", [])),
                })
                continue

            if role == "assistant":
                payload: dict[str, Any] = {
                    "role": "assistant",
                    "content": normalized.get("content"),
                }
                if normalized.get("reasoning_content") is not None:
                    payload["reasoning_content"] = normalized["reasoning_content"]
                if normalized.get("tool_calls"):
                    payload["tool_calls"] = normalized["tool_calls"]
                compiled.append(payload)
                continue

            if role == "tool":
                compiled.append({
                    "role": "tool",
                    "tool_call_id": normalized.get("tool_call_id"),
                    "content": normalized.get("content", ""),
                })
                continue

            compiled.append({
                "role": role,
                "content": normalized.get("content", extract_text(normalized)),
            })
        return compiled

    def _compile_user_parts(self, parts: Any) -> list[dict[str, Any]]:
        compiled: list[dict[str, Any]] = []
        for part in normalize_parts(parts):
            part_type = str(part.get("type", "")).strip()
            if part_type == "text":
                compiled.append({"type": "text", "text": str(part.get("text", ""))})
                continue
            if part_type == "image_ref":
                compiled.append({
                    "type": "image_url",
                    "image_url": {
                        "url": _path_to_data_url(
                            path=str(part.get("path", "")),
                            mime_type=str(part.get("mime_type", "")),
                        ),
                        "detail": self.image_detail,
                    },
                })
                continue
            raise UnsupportedMediaError(f"provider 尚不支持媒体类型: {part_type}")
        return compiled


def message_to_dict(msg: Any) -> dict[str, Any]:
    """OpenAI message 对象 → 统一 dict。"""
    if msg is None:
        return {"role": "assistant", "content": None}
    data: dict[str, Any] = {
        "role": getattr(msg, "role", "assistant"),
        "content": getattr(msg, "content", None),
    }
    reasoning_content = getattr(msg, "reasoning_content", None)
    model_extra = getattr(msg, "model_extra", None)
    if reasoning_content is None and isinstance(model_extra, dict):
        reasoning_content = model_extra.get("reasoning_content")
    if reasoning_content is not None:
        data["reasoning_content"] = reasoning_content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
    return data


def _path_to_data_url(*, path: str, mime_type: str) -> str:
    raw = Path(path).read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _looks_like_unsupported_image(exc: Exception) -> bool:
    message = str(exc).lower()
    patterns = (
        "does not support image",
        "image input is not supported",
        "unsupported content type",
        "image_url",
        "vision",
    )
    return any(pattern in message for pattern in patterns)
