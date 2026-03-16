"""
[INPUT]: dataclasses, pathlib, typing
[OUTPUT]: TurnInput, AttachmentRef, history normalization/render helpers
[POS]: agent 内部消息模型：统一文本/附件输入，隔离 provider payload
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_ATTACHMENT_KINDS = {"image", "audio", "file"}
SUPPORTED_REF_KINDS = {"automation_run", "automation_task"}
TEXT_PART_TYPE = "text"


@dataclass(frozen=True)
class AttachmentRef:
    """统一附件引用。当前主流程仅实现 image，audio/file 预留类型位。"""

    kind: str
    path: str
    mime_type: str
    size_bytes: int | None = None
    source_id: str | None = None
    width: int | None = None
    height: int | None = None
    original_name: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_ATTACHMENT_KINDS:
            raise ValueError(f"unsupported attachment kind: {self.kind}")


@dataclass(frozen=True)
class ContextRef:
    """单轮上下文引用。当前用于自动化 task/run 的默认选择器绑定。"""

    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_REF_KINDS:
            raise ValueError(f"unsupported ref kind: {self.kind}")
        if not str(self.value or "").strip():
            raise ValueError("ref value cannot be empty")


@dataclass(frozen=True)
class TurnInput:
    """单轮输入：文本 + 附件。"""

    text: str = ""
    attachments: tuple[AttachmentRef, ...] = ()
    refs: tuple[ContextRef, ...] = ()

    def has_attachments(self) -> bool:
        return bool(self.attachments)

    def is_empty(self) -> bool:
        return not (self.text or self.attachments)


def ensure_turn_input(value: str | TurnInput) -> TurnInput:
    if isinstance(value, TurnInput):
        return value
    return TurnInput(text=value)


def text_part(text: str) -> dict[str, str]:
    return {"type": TEXT_PART_TYPE, "text": text}


def attachment_to_part(attachment: AttachmentRef) -> dict[str, Any]:
    part: dict[str, Any] = {
        "type": f"{attachment.kind}_ref",
        "path": attachment.path,
        "mime_type": attachment.mime_type,
    }
    if attachment.size_bytes is not None:
        part["size_bytes"] = attachment.size_bytes
    if attachment.source_id:
        part["source_id"] = attachment.source_id
    if attachment.width is not None:
        part["width"] = attachment.width
    if attachment.height is not None:
        part["height"] = attachment.height
    if attachment.original_name:
        part["original_name"] = attachment.original_name
    return part


def part_to_attachment(part: dict[str, Any]) -> AttachmentRef | None:
    raw_type = str(part.get("type", "")).strip()
    if not raw_type.endswith("_ref"):
        return None
    kind = raw_type[:-4]
    if kind not in SUPPORTED_ATTACHMENT_KINDS:
        return None
    path = str(part.get("path", "")).strip()
    mime_type = str(part.get("mime_type", "")).strip()
    if not path or not mime_type:
        return None
    return AttachmentRef(
        kind=kind,
        path=path,
        mime_type=mime_type,
        size_bytes=_as_optional_int(part.get("size_bytes")),
        source_id=_as_optional_str(part.get("source_id")),
        width=_as_optional_int(part.get("width")),
        height=_as_optional_int(part.get("height")),
        original_name=_as_optional_str(part.get("original_name")),
    )


def build_user_message(turn: TurnInput, *, date_str: str) -> dict[str, Any]:
    body = turn.text.strip()
    dated_text = f"[{date_str}]\n{body}" if body else f"[{date_str}]"
    parts: list[dict[str, Any]] = [text_part(dated_text)]
    parts.extend(attachment_to_part(attachment) for attachment in turn.attachments)
    return {"role": "user", "parts": parts, "content": render_user_parts(parts)}


def normalize_history_message(message: dict[str, Any]) -> dict[str, Any]:
    role = str(message.get("role", "")).strip()
    if role == "user":
        parts = normalize_parts(message.get("parts"))
        if parts:
            return {"role": "user", "parts": parts, "content": render_user_parts(parts)}

        content = message.get("content")
        if content is None:
            return {"role": "user", "parts": [], "content": ""}
        parts = [text_part(str(content))]
        return {"role": "user", "parts": parts, "content": render_user_parts(parts)}

    normalized = dict(message)
    if role in ("system", "assistant", "tool") and "content" in normalized and normalized["content"] is not None:
        normalized["content"] = str(normalized["content"])
    return normalized


def normalize_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_history_message(message) for message in history]


def normalize_parts(raw_parts: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_parts, list):
        return []

    parts: list[dict[str, Any]] = []
    for item in raw_parts:
        if not isinstance(item, dict):
            continue
        part_type = str(item.get("type", "")).strip()
        if part_type == TEXT_PART_TYPE:
            parts.append(text_part(str(item.get("text", ""))))
            continue
        attachment = part_to_attachment(item)
        if attachment is not None:
            parts.append(attachment_to_part(attachment))
    return parts


def extract_text(message: dict[str, Any]) -> str:
    role = str(message.get("role", "")).strip()
    if role == "user":
        return render_user_parts(message.get("parts"))

    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_coerce_text(item) for item in content if _coerce_text(item))
    return str(content)


def render_turn_input(turn: TurnInput) -> str:
    parts: list[str] = []
    if turn.text:
        parts.append(turn.text)
    for attachment in turn.attachments:
        parts.append(render_attachment(attachment_to_part(attachment)))
    return "\n".join(part for part in parts if part)


def render_user_parts(parts: Any) -> str:
    normalized = normalize_parts(parts)
    rendered: list[str] = []
    for part in normalized:
        if part.get("type") == TEXT_PART_TYPE:
            rendered.append(str(part.get("text", "")))
            continue
        rendered.append(render_attachment(part))
    return "\n".join(part for part in rendered if part)


def user_attachments(message: dict[str, Any]) -> tuple[AttachmentRef, ...]:
    if str(message.get("role", "")).strip() != "user":
        return ()
    attachments: list[AttachmentRef] = []
    for part in normalize_parts(message.get("parts")):
        attachment = part_to_attachment(part)
        if attachment is not None:
            attachments.append(attachment)
    return tuple(attachments)


def render_attachment(part: dict[str, Any]) -> str:
    part_type = str(part.get("type", "")).strip()
    kind = part_type[:-4] if part_type.endswith("_ref") else part_type or "attachment"
    path = str(part.get("path", "")).strip()
    dims = ""
    width = _as_optional_int(part.get("width"))
    height = _as_optional_int(part.get("height"))
    if width and height:
        dims = f" {width}x{height}"
    mime_type = str(part.get("mime_type", "")).strip()
    detail = f" mime={mime_type}" if mime_type else ""
    source_id = _as_optional_str(part.get("source_id"))
    source = f" source={source_id}" if source_id else ""
    return f"[{kind} path={path}{dims}{detail}{source}]".strip()


def count_attachment_tokens(message: dict[str, Any], *, image_budget: int = 3000) -> int:
    total = 0
    if str(message.get("role", "")).strip() != "user":
        return total
    for part in normalize_parts(message.get("parts")):
        part_type = str(part.get("type", "")).strip()
        if part_type == "image_ref":
            total += image_budget
    return total


def _coerce_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if item.get("type") == TEXT_PART_TYPE:
            return str(item.get("text", ""))
    return ""


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
