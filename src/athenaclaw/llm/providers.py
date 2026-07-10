"""
[INPUT]: base64, json, pathlib, typing, openai, anthropic（lazy import）, agent.messages
[OUTPUT]: LLMProvider（complete + stream Protocol）, LLMResult, OpenAIChatProvider, AnthropicProvider, provider error helpers
[POS]: LLM provider 抽象层：统一内部消息（OpenAI-shape，canonical wire format）与各 provider SDK 之间的编解码；AnthropicProvider 内部完成 OpenAI-shape ↔ Anthropic Messages API 双向转译，对 Kernel 透明
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

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
        timeout: float | None = None,
    ) -> LLMResult: ...

    def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
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
        timeout: float | None = None,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self.compile_messages(messages),
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if timeout is not None:
            kwargs["timeout"] = timeout

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

    def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResult:
        """OpenAI streaming：逐 chunk 回调 on_chunk，聚合返回统一 LLMResult（含 usage）。"""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self.compile_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if timeout is not None:
            kwargs["timeout"] = timeout

        chunks = self.client.chat.completions.create(**kwargs)
        parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_acc: dict[int, dict] = {}
        finish_reason = "stop"
        usage_total_tokens = 0

        for chunk in chunks:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                usage_total_tokens = getattr(usage, "total_tokens", 0) or usage_total_tokens
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            if getattr(delta, "content", None):
                parts.append(delta.content)
                if on_chunk is not None:
                    on_chunk(delta.content)
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if reasoning_piece is None:
                model_extra = getattr(delta, "model_extra", None)
                if isinstance(model_extra, dict):
                    reasoning_piece = model_extra.get("reasoning_content")
            if reasoning_piece:
                reasoning_parts.append(str(reasoning_piece))
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tc_acc:
                        tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tc_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tc_acc[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tc_acc[idx]["arguments"] += tc.function.arguments

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(parts) or None}
        tool_calls: list[LLMToolCall] = []
        for v in tc_acc.values():
            msg.setdefault("tool_calls", []).append({
                "id": v["id"], "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"]},
            })
            tool_calls.append(LLMToolCall(id=v["id"], name=v["name"], arguments=v["arguments"]))
        if reasoning_parts:
            msg["reasoning_content"] = "".join(reasoning_parts)
        elif tool_calls:
            # Keep streamed tool-call messages compatible with providers that
            # require reasoning_content when thinking is enabled.
            msg["reasoning_content"] = ""

        return LLMResult(
            assistant_message=msg,
            finish_reason=finish_reason,
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
                elif normalized.get("tool_calls"):
                    # Some thinking-enabled providers require every assistant
                    # tool-call message to include reasoning_content, even for
                    # old sessions created before we preserved it.
                    payload["reasoning_content"] = ""
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


_ANTHROPIC_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
}


class AnthropicProvider:
    """官方 anthropic SDK 的原生 Claude provider。

    内部 wire 格式保持 OpenAI-shape 不变——本类只负责 OpenAI-shape ↔ Anthropic
    Messages API 的编解码，Kernel/session.history 对此零感知。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: Any | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.max_tokens = max_tokens
        if client is not None:
            self.client = client
        else:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "AnthropicProvider 需要 anthropic SDK：pip install 'athenaclaw[anthropic]'"
                ) from exc
            self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> LLMResult:
        kwargs = self._build_request(
            model=model, messages=messages, tools=tools,
            temperature=temperature, timeout=timeout,
        )
        response = self.client.messages.create(**kwargs)
        return self._decode_response(response)

    def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> LLMResult:
        kwargs = self._build_request(
            model=model, messages=messages, tools=tools,
            temperature=temperature, timeout=timeout,
        )
        with self.client.messages.stream(**kwargs) as stream_ctx:
            for text in stream_ctx.text_stream:
                if on_chunk is not None:
                    on_chunk(text)
            final_message = stream_ctx.get_final_message()
        return self._decode_response(final_message)

    def _build_request(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        timeout: float | None,
    ) -> dict[str, Any]:
        system, anthropic_messages = self._encode_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._encode_tools(tools)
        if temperature is not None:
            kwargs["temperature"] = temperature
        if timeout is not None:
            kwargs["timeout"] = timeout
        return kwargs

    # ── OpenAI-shape → Anthropic 编码 ────────────────────────────────────────

    def _encode_messages(self, messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        encoded: list[dict[str, Any]] = []
        pending_tool_results: list[dict[str, Any]] = []

        def flush_tool_results() -> None:
            if pending_tool_results:
                encoded.append({"role": "user", "content": list(pending_tool_results)})
                pending_tool_results.clear()

        for message in messages:
            normalized = normalize_history_message(message)
            role = str(normalized.get("role", "")).strip()

            if role == "tool":
                pending_tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": normalized.get("tool_call_id"),
                    "content": str(normalized.get("content", "")),
                })
                continue

            flush_tool_results()

            if role == "system":
                content = normalized.get("content")
                if content:
                    system_parts.append(str(content))
                continue

            if role == "user":
                encoded.append({
                    "role": "user",
                    "content": self._encode_user_parts(normalized.get("parts", [])),
                })
                continue

            if role == "assistant":
                encoded.append({"role": "assistant", "content": self._encode_assistant_blocks(normalized)})
                continue

            # 未知 role：退化为纯文本 user 消息，不丢数据。
            encoded.append({
                "role": "user",
                "content": [{"type": "text", "text": normalized.get("content") or extract_text(normalized)}],
            })

        flush_tool_results()
        system_text = "\n\n".join(system_parts) if system_parts else None
        return system_text, encoded

    def _encode_assistant_blocks(self, normalized: dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        content = normalized.get("content")
        if content:
            blocks.append({"type": "text", "text": str(content)})
        for tc in normalized.get("tool_calls") or []:
            func = tc.get("function", {})
            try:
                tool_input = json.loads(func.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                tool_input = {}
            blocks.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": func.get("name"),
                "input": tool_input,
            })
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        return blocks

    def _encode_user_parts(self, parts: Any) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for part in normalize_parts(parts):
            part_type = str(part.get("type", "")).strip()
            if part_type == "text":
                blocks.append({"type": "text", "text": str(part.get("text", ""))})
                continue
            if part_type == "image_ref":
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": str(part.get("mime_type", "")),
                        "data": _base64_encode_file(str(part.get("path", ""))),
                    },
                })
                continue
            raise UnsupportedMediaError(f"provider 尚不支持媒体类型: {part_type}")
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        return blocks

    def _encode_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        encoded = []
        for t in tools:
            func = t.get("function", t)
            encoded.append({
                "name": func.get("name"),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters") or {"type": "object", "properties": {}},
            })
        return encoded

    # ── Anthropic → LLMResult 解码 ───────────────────────────────────────────

    def _decode_response(self, response: Any) -> LLMResult:
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        tool_call_dicts: list[dict[str, Any]] = []

        for block in getattr(response, "content", None) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                arguments = json.dumps(block.input or {})
                tool_calls.append(LLMToolCall(id=block.id, name=block.name, arguments=arguments))
                tool_call_dicts.append({
                    "id": block.id, "type": "function",
                    "function": {"name": block.name, "arguments": arguments},
                })
            elif block_type == "thinking":
                thinking_parts.append(str(getattr(block, "thinking", "") or ""))

        assistant_message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
        if tool_call_dicts:
            assistant_message["tool_calls"] = tool_call_dicts
        if thinking_parts:
            assistant_message["reasoning_content"] = "".join(thinking_parts)

        stop_reason = str(getattr(response, "stop_reason", None) or "end_turn")
        finish_reason = _ANTHROPIC_FINISH_REASON_MAP.get(stop_reason, stop_reason)

        usage = getattr(response, "usage", None)
        usage_total_tokens = 0
        if usage is not None:
            usage_total_tokens = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)

        return LLMResult(
            assistant_message=assistant_message,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage_total_tokens=int(usage_total_tokens),
        )


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


def _base64_encode_file(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


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
