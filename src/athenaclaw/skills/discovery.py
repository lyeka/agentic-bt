"""
[INPUT]: os, re, html, pathlib, dataclasses, unicodedata, pyyaml
[OUTPUT]: Skill, load_skills, build_available_skills_prompt, parse_explicit_skill_command, expand_explicit_skill_command, build_skill_payload, invoke_skill
[POS]: Agent Skills 引擎（发现/解析/验证/注入/显式展开/模型自主调用）
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - CI/运行环境安装依赖后不会命中
    yaml = None


ROOT_MD_SUFFIX = ".md"
SKILL_MD_NAMES = {"skill.md"}
SKIP_DIR_NAMES = {"node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
EXPLICIT_SKILL_RE = re.compile(r"^/skill:([^\s]+)(?:\s+(.*))?$")


@dataclass(frozen=True)
class Skill:
    """单个 skill 的解析结果。"""

    name: str
    description: str
    file_path: Path
    base_dir: Path
    source: str
    disable_model_invocation: bool = False
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: str | list[str] | None = None
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class ParsedCommand:
    """显式 skill 命令解析结果。"""

    name: str
    args: str


def load_skills(skill_roots: list[tuple[Path, str]]) -> tuple[dict[str, Skill], list[dict[str, str]]]:
    """加载并聚合 skills。返回 name->Skill 与诊断信息。"""
    diagnostics: list[dict[str, str]] = []
    skills: dict[str, Skill] = {}
    for file_path, source in discover_skill_files(skill_roots):
        skill = _parse_skill_file(file_path, source, diagnostics)
        if skill is None:
            continue
        if skill.name in skills:
            _diag(
                diagnostics,
                code="name_collision",
                message=f"skill 名称冲突，保留先加载项: {skill.name}",
                path=str(file_path),
                name=skill.name,
            )
            continue
        skills[skill.name] = skill
    return skills, diagnostics


def discover_skill_files(skill_roots: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    """从多个根目录发现 skill markdown 文件。"""
    discovered: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for raw_root, source in skill_roots:
        root = raw_root.expanduser()
        if not root.exists():
            continue
        if root.is_file():
            _add_md_file(root, source, discovered, seen)
            continue

        # 根目录直接 .md 文件作为 skill 候选
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_file() and child.suffix.lower() == ROOT_MD_SUFFIX:
                _add_md_file(child, source, discovered, seen)

        # 子目录递归仅识别 SKILL.md / skill.md
        for curr, dirnames, filenames in os.walk(root, topdown=True, followlinks=True):
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not d.startswith(".") and d not in SKIP_DIR_NAMES
            )
            curr_path = Path(curr)
            if curr_path == root:
                continue
            for filename in sorted(filenames):
                if filename.lower() in SKILL_MD_NAMES:
                    _add_md_file(curr_path / filename, source, discovered, seen)
    return discovered


def parse_explicit_skill_command(user_input: str) -> ParsedCommand | None:
    """解析 /skill:name args 命令。非显式 skill 命令返回 None。"""
    stripped = user_input.strip()
    match = EXPLICIT_SKILL_RE.match(stripped)
    if not match:
        return None
    name = match.group(1)
    args = (match.group(2) or "").strip()
    return ParsedCommand(name=name, args=args)


def expand_explicit_skill_command(
    user_input: str,
    skills: dict[str, Skill],
) -> tuple[str | None, str | None, str | None]:
    """
    显式命令展开。
    返回: (expanded_text, error, skill_name)
    """
    parsed = parse_explicit_skill_command(user_input)
    if parsed is None:
        return None, None, None
    skill = skills.get(parsed.name)
    if skill is None:
        names = ", ".join(sorted(skills.keys()))
        return None, f"未知 skill: {parsed.name}。可用 skills: {names or '(无)'}", parsed.name
    expanded = build_skill_payload(skill, parsed.args)
    return expanded, None, parsed.name


def build_available_skills_prompt(skills: dict[str, Skill]) -> str:
    """生成注入 system prompt 的 <available_skills> XML 片段。"""
    visible = [skill for skill in skills.values() if not skill.disable_model_invocation]
    if not visible:
        return ""
    visible.sort(key=lambda skill: skill.name)

    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "Call the skill_invoke tool when a task matches a skill description,",
        "or use the read tool to load a skill file by its location.",
        "When a skill file references a relative path, resolve it against the skill",
        "directory (parent of SKILL.md) and use that absolute path in tool commands.",
        "",
        "<available_skills>",
    ]
    for skill in visible:
        lines.extend(
            [
                "  <skill>",
                f"    <name>{escape(skill.name, quote=True)}</name>",
                f"    <description>{escape(skill.description, quote=True)}</description>",
                f"    <location>{escape(str(skill.file_path), quote=True)}</location>",
                "  </skill>",
            ],
        )
    lines.append("</available_skills>")
    return "\n".join(lines)


def build_skill_payload(skill: Skill, args: str = "") -> str:
    """将 skill body 与参数包装成显式展开文本。"""
    body = _read_skill_body(skill.file_path)
    open_tag = (
        f'<skill name="{escape(skill.name, quote=True)}" '
        f'location="{escape(str(skill.file_path), quote=True)}">'
    )
    lines = [
        open_tag,
        f"References are relative to {skill.base_dir}.",
        "",
        body,
        "</skill>",
    ]
    if args:
        lines.extend(["", args])
    return "\n".join(lines)


def invoke_skill(name: str, args: str, skills: dict[str, Skill]) -> dict[str, Any]:
    """供 tool handler 使用：返回 skill 正文与展开内容。"""
    skill = skills.get(name)
    if skill is None:
        return {
            "error": f"未知 skill: {name}",
            "available_names": sorted(skills.keys()),
        }
    if skill.disable_model_invocation:
        return {
            "error": f"skill 已禁用模型自主调用: {name}",
            "name": name,
        }
    body = _read_skill_body(skill.file_path)
    return {
        "name": skill.name,
        "description": skill.description,
        "location": str(skill.file_path),
        "base_dir": str(skill.base_dir),
        "args": args,
        "body": body,
        "expanded": build_skill_payload(skill, args),
    }


def _add_md_file(
    file_path: Path,
    source: str,
    discovered: list[tuple[Path, str]],
    seen: set[Path],
) -> None:
    if not file_path.exists() or not file_path.is_file():
        return
    if file_path.suffix.lower() != ROOT_MD_SUFFIX:
        return
    real = file_path.resolve()
    if real in seen:
        return
    seen.add(real)
    discovered.append((real, source))


def _parse_skill_file(
    file_path: Path,
    source: str,
    diagnostics: list[dict[str, str]],
) -> Skill | None:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        _diag(
            diagnostics,
            code="read_failed",
            message=f"读取 skill 失败: {exc}",
            path=str(file_path),
        )
        return None

    frontmatter, _ = _split_frontmatter(raw, file_path, diagnostics)

    raw_name = frontmatter.get("name")
    fallback_name = file_path.parent.name if file_path.name.lower() in SKILL_MD_NAMES else file_path.stem
    name = _normalize_name(raw_name if isinstance(raw_name, str) and raw_name.strip() else fallback_name)

    raw_description = frontmatter.get("description")
    description = raw_description.strip() if isinstance(raw_description, str) else ""
    if not description:
        _diag(
            diagnostics,
            code="missing_description",
            message="缺少 description，已跳过 skill",
            path=str(file_path),
            name=name,
        )
        return None

    _validate_name(name, file_path, diagnostics)
    _validate_description(description, file_path, name, diagnostics)

    metadata = frontmatter.get("metadata")
    normalized_metadata: dict[str, str] | None = None
    if isinstance(metadata, dict):
        normalized_metadata = {
            str(key): str(value)
            for key, value in metadata.items()
        }

    return Skill(
        name=name,
        description=description,
        file_path=file_path.resolve(),
        base_dir=file_path.resolve().parent,
        source=source,
        disable_model_invocation=_as_bool(
            frontmatter.get("disable-model-invocation", frontmatter.get("disable_model_invocation", False)),
        ),
        license=_as_optional_str(frontmatter.get("license")),
        compatibility=_as_optional_str(frontmatter.get("compatibility")),
        allowed_tools=frontmatter.get("allowed-tools"),
        metadata=normalized_metadata,
    )


def _split_frontmatter(
    content: str,
    file_path: Path,
    diagnostics: list[dict[str, str]],
) -> tuple[dict[str, Any], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        _diag(
            diagnostics,
            code="frontmatter_unterminated",
            message="frontmatter 缺少结束分隔符，按无 frontmatter 处理",
            path=str(file_path),
        )
        return {}, content

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    if not frontmatter_text.strip():
        return {}, body

    try:
        parsed = _yaml_safe_load(frontmatter_text)
    except Exception as exc:
        _diag(
            diagnostics,
            code="frontmatter_parse_failed",
            message=f"frontmatter YAML 解析失败: {exc}",
            path=str(file_path),
        )
        return {}, body

    if parsed is None:
        return {}, body
    if not isinstance(parsed, dict):
        _diag(
            diagnostics,
            code="frontmatter_not_mapping",
            message="frontmatter 不是键值对象，按空配置处理",
            path=str(file_path),
        )
        return {}, body
    return parsed, body


def _read_skill_body(file_path: Path) -> str:
    raw = file_path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw, file_path, [])
    return body.strip("\n")


def _normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip())


def _validate_name(name: str, file_path: Path, diagnostics: list[dict[str, str]]) -> None:
    if not name:
        _diag(
            diagnostics,
            code="invalid_name",
            message="name 为空",
            path=str(file_path),
        )
        return

    if len(name) > 64:
        _diag(
            diagnostics,
            code="invalid_name_length",
            message=f"name 超过 64 字符: {name}",
            path=str(file_path),
            name=name,
        )

    if name.startswith("-") or name.endswith("-") or "--" in name:
        _diag(
            diagnostics,
            code="invalid_name_hyphen",
            message=f"name 连字符规则不合法: {name}",
            path=str(file_path),
            name=name,
        )

    allowed = True
    for ch in name:
        if ch == "-":
            continue
        if ch.isdigit():
            continue
        if ch.isalpha() and ch == ch.lower():
            continue
        allowed = False
        break
    if not allowed:
        _diag(
            diagnostics,
            code="invalid_name_charset",
            message=f"name 仅允许小写字母/数字/连字符: {name}",
            path=str(file_path),
            name=name,
        )

    if file_path.name.lower() in SKILL_MD_NAMES and file_path.parent.name != name:
        _diag(
            diagnostics,
            code="name_parent_mismatch",
            message=f"name 与父目录名不一致: {name} != {file_path.parent.name}",
            path=str(file_path),
            name=name,
        )


def _validate_description(
    description: str,
    file_path: Path,
    name: str,
    diagnostics: list[dict[str, str]],
) -> None:
    if len(description) > 1024:
        _diag(
            diagnostics,
            code="description_too_long",
            message="description 超过 1024 字符",
            path=str(file_path),
            name=name,
        )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _as_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _yaml_safe_load(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text)

    # 依赖缺失时的最小回退解析，仅覆盖简单 key:value 场景
    parsed: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {raw_line}")
        key, value = line.split(":", 1)
        parsed[key.strip()] = _coerce_scalar(value.strip())
    return parsed


def _coerce_scalar(raw: str) -> Any:
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        raw = raw[1:-1]
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        raw = raw[1:-1]
    lower = raw.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    return raw


def _diag(
    diagnostics: list[dict[str, str]],
    *,
    code: str,
    message: str,
    path: str | None = None,
    name: str | None = None,
) -> None:
    record: dict[str, str] = {
        "level": "warning",
        "code": code,
        "message": message,
    }
    if path:
        record["path"] = path
    if name:
        record["name"] = name
    diagnostics.append(record)
