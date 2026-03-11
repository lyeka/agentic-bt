"""
[INPUT]: os, re, pathlib, html, agent.skills（发现模式复用）, core.subagent
[OUTPUT]: discover_subagent_files, parse_subagent_file, load_subagents, SubAgentSystem
[POS]: Sub-Agent 集成子系统——发现/解析/注册/调用/工具生成/团队描述。类比 skills.py
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import os
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from core.subagent import SubAgentDef, SubAgentResult, filter_schemas, run_subagent


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,60}$")
MD_SUFFIX = ".md"
OUTPUT_PROTOCOL_RE = re.compile(
    r"<output_protocol>\s*(.*?)\s*</output_protocol>",
    re.DOTALL,
)


# ─────────────────────────────────────────────────────────────────────────────
# 文件发现
# ─────────────────────────────────────────────────────────────────────────────

def discover_subagent_files(
    roots: list[tuple[Path, str]],
) -> list[tuple[Path, str]]:
    """从多个根目录发现 subagent markdown 文件"""
    discovered: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for raw_root, source in roots:
        root = raw_root.expanduser()
        if not root.exists():
            continue
        if root.is_file():
            _add_md(root, source, discovered, seen)
            continue
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_file() and child.suffix.lower() == MD_SUFFIX:
                _add_md(child, source, discovered, seen)
    return discovered


def _add_md(
    path: Path,
    source: str,
    discovered: list[tuple[Path, str]],
    seen: set[Path],
) -> None:
    if not path.is_file() or path.suffix.lower() != MD_SUFFIX:
        return
    real = path.resolve()
    if real in seen:
        return
    seen.add(real)
    discovered.append((real, source))


# ─────────────────────────────────────────────────────────────────────────────
# 解析
# ─────────────────────────────────────────────────────────────────────────────

def parse_subagent_file(
    file_path: Path,
    source: str,
    diagnostics: list[dict[str, str]],
) -> SubAgentDef | None:
    """解析单个 subagent md 文件 → SubAgentDef"""
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        _diag(diagnostics, code="read_failed", message=f"读取失败: {exc}", path=str(file_path))
        return None

    frontmatter, body = _split_frontmatter(raw, file_path, diagnostics)

    # name
    raw_name = frontmatter.get("name")
    fallback_name = file_path.stem
    name = _normalize_name(raw_name if isinstance(raw_name, str) and raw_name.strip() else fallback_name)

    # description（必需）
    raw_desc = frontmatter.get("description")
    description = raw_desc.strip() if isinstance(raw_desc, str) else ""
    if not description:
        _diag(diagnostics, code="missing_description", message="缺少 description", path=str(file_path), name=name)
        return None

    # system_prompt = body（去掉 output_protocol 标签后的完整内容）
    output_guide = None
    match = OUTPUT_PROTOCOL_RE.search(body)
    if match:
        output_guide = match.group(1).strip()
        body = OUTPUT_PROTOCOL_RE.sub("", body)
    system_prompt = body.strip()

    # 工具配置
    tools = _as_str_list(frontmatter.get("tools"))
    blocked_tools = _as_str_list(frontmatter.get("blocked_tools", frontmatter.get("blocked-tools")))

    return SubAgentDef(
        name=name,
        description=description,
        system_prompt=system_prompt,
        output_guide=output_guide,
        tools=tools,
        blocked_tools=blocked_tools,
        model=_as_optional_str(frontmatter.get("model")),
        max_rounds=max(1, _as_int(frontmatter.get("max_rounds", frontmatter.get("max-rounds")), 10)),
        token_budget=max(1000, _as_int(frontmatter.get("token_budget", frontmatter.get("token-budget")), 50_000)),
        timeout_seconds=max(1, _as_int(frontmatter.get("timeout_seconds", frontmatter.get("timeout-seconds")), 120)),
        temperature=max(0.0, min(2.0, _as_float(frontmatter.get("temperature"), 0.0))),
    )


def load_subagents(
    roots: list[tuple[Path, str]],
) -> tuple[dict[str, SubAgentDef], list[dict[str, str]]]:
    """加载并聚合 subagents。返回 name→SubAgentDef 与诊断信息"""
    diagnostics: list[dict[str, str]] = []
    subagents: dict[str, SubAgentDef] = {}
    for file_path, source in discover_subagent_files(roots):
        defn = parse_subagent_file(file_path, source, diagnostics)
        if defn is None:
            continue
        if defn.name in subagents:
            _diag(diagnostics, code="name_collision",
                  message=f"名称冲突，保留先加载项: {defn.name}", path=str(file_path), name=defn.name)
            continue
        subagents[defn.name] = defn
    return subagents, diagnostics


# ─────────────────────────────────────────────────────────────────────────────
# SubAgentSystem
# ─────────────────────────────────────────────────────────────────────────────

class SubAgentSystem:
    """
    Sub-Agent 管理子系统。

    向 Kernel 暴露 ToolDef 描述 + team_prompt 片段。
    Kernel.turn() 零改动——子代理对主循环完全透明。
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        get_tool_schemas: Callable[[], list[dict]],
        tool_executor: Callable[[str, dict], Any],
        emit_fn: Callable[[str, Any], None] | None = None,
        max_subagents: int = 10,
    ) -> None:
        self._client = client
        self._model = model
        self._get_tool_schemas = get_tool_schemas
        self._tool_executor = tool_executor
        self._emit_fn = emit_fn
        self._max_subagents = max_subagents
        self._registry: dict[str, SubAgentDef] = {}

    # ── 注册与生命周期 ────────────────────────────────────────────────────────

    def register(self, defn: SubAgentDef) -> dict[str, str] | None:
        """注册 SubAgent。成功返回 None，失败返回 error dict"""
        if len(self._registry) >= self._max_subagents and defn.name not in self._registry:
            return {"error": f"子代理数量已达上限 ({self._max_subagents})"}
        self._registry[defn.name] = defn
        if self._emit_fn:
            self._emit_fn("subagent.registered", {"name": defn.name})
        return None

    def remove(self, name: str) -> None:
        self._registry.pop(name, None)
        if self._emit_fn:
            self._emit_fn("subagent.removed", {"name": name})

    def list_agents(self) -> list[dict[str, str]]:
        return [
            {"name": d.name, "description": d.description}
            for d in self._registry.values()
        ]

    # ── 调用 ──────────────────────────────────────────────────────────────────

    def invoke(self, name: str, task: str, context: str = "") -> SubAgentResult:
        defn = self._registry.get(name)
        if defn is None:
            return SubAgentResult(
                response=f"[error] 未知子代理: {name}",
                metadata={"error": f"unknown subagent: {name}"},
            )
        return run_subagent(
            definition=defn,
            task=task,
            context=context,
            client=self._client,
            model=self._model,
            tool_schemas=self._get_tool_schemas(),
            tool_executor=self._tool_executor,
            emit_fn=self._emit_fn,
        )

    # ── 工具生成 ──────────────────────────────────────────────────────────────

    def as_tool_defs(self) -> dict[str, dict]:
        """
        生成所有 SubAgent 的工具定义。

        每个注册的 SubAgent → ask_{name} 工具。
        系统工具：create_subagent + list_subagents。
        """
        tools: dict[str, dict] = {}

        # ask_{name} 工具
        for name, defn in self._registry.items():
            tool_name = f"ask_{name}"
            tools[tool_name] = {
                "name": tool_name,
                "schema": _ask_schema(name, defn.description),
                "handler": self._make_ask_handler(name),
            }

        # 管理工具
        tools["create_subagent"] = {
            "name": "create_subagent",
            "schema": _create_schema(),
            "handler": self._handle_create,
        }
        tools["list_subagents"] = {
            "name": "list_subagents",
            "schema": _list_schema(),
            "handler": self._handle_list,
        }

        return tools

    def _make_ask_handler(self, name: str) -> Callable:
        def handler(args: dict) -> dict:
            task = str(args.get("task", "")).strip()
            context = str(args.get("context", "")).strip()
            if not task:
                return {"error": "缺少参数: task"}
            result = self.invoke(name, task, context)
            return {
                "response": result.response,
                "run_id": result.metadata.get("run_id"),
                "metadata": result.metadata,
            }
        return handler

    def _handle_create(self, args: dict) -> dict:
        name = str(args.get("name", "")).strip()
        description = str(args.get("description", "")).strip()
        system_prompt = str(args.get("system_prompt", "")).strip()
        if not name or not description or not system_prompt:
            return {"error": "缺少必要参数: name, description, system_prompt"}
        if not VALID_NAME_RE.match(name):
            return {"error": f"无效名称: '{name}'。只允许字母/数字/下划线/连字符，1-60 字符"}

        defn = SubAgentDef(
            name=name,
            description=description,
            system_prompt=system_prompt,
            output_guide=_as_optional_str(args.get("output_guide")),
            tools=_as_str_list(args.get("tools")),
            blocked_tools=_as_str_list(args.get("blocked_tools")),
        )
        err = self.register(defn)
        if err:
            return err
        return {"created": name, "description": description}

    def _handle_list(self, args: dict) -> dict:
        return {"subagents": self.list_agents()}

    # ── Prompt 生成 ───────────────────────────────────────────────────────────

    def team_prompt(self) -> str:
        """生成注入 system prompt 的 <team> XML"""
        if not self._registry:
            return ""
        lines = [
            "You have access to a team of sub-agents. Delegate tasks when their expertise matches.",
            "Use the ask_{name} tool to delegate. Provide task and context.",
            "",
            "<team>",
        ]
        for defn in sorted(self._registry.values(), key=lambda d: d.name):
            lines.extend([
                "  <agent>",
                f"    <name>{escape(defn.name, quote=True)}</name>",
                f"    <description>{escape(defn.description, quote=True)}</description>",
                f"    <tool>ask_{escape(defn.name, quote=True)}</tool>",
                "  </agent>",
            ])
        lines.append("</team>")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Schema 构造
# ─────────────────────────────────────────────────────────────────────────────

def _ask_schema(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"ask_{name}",
            "description": (
                f"委派任务给 {name}（{description}）。"
                "在 context 中提供相关背景，子代理基于 context 给出增量成果。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "要执行的具体任务"},
                    "context": {"type": "string", "description": "相关背景信息：已知结论、当前状态、约束条件"},
                },
                "required": ["task"],
            },
        },
    }


def _create_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "create_subagent",
            "description": "动态创建一个子代理。需要 name、description、system_prompt。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "子代理标识符"},
                    "description": {"type": "string", "description": "能力描述"},
                    "system_prompt": {"type": "string", "description": "子代理的 system prompt"},
                    "output_guide": {"type": "string", "description": "可选：输出格式指引"},
                    "tools": {
                        "type": "array", "items": {"type": "string"},
                        "description": "可选：工具白名单",
                    },
                    "blocked_tools": {
                        "type": "array", "items": {"type": "string"},
                        "description": "可选：工具黑名单",
                    },
                },
                "required": ["name", "description", "system_prompt"],
            },
        },
    }


def _list_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": "列出当前所有可用的子代理。",
            "parameters": {"type": "object", "properties": {}},
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter 解析辅助
# ─────────────────────────────────────────────────────────────────────────────

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
        _diag(diagnostics, code="frontmatter_unterminated",
              message="frontmatter 缺少结束符", path=str(file_path))
        return {}, content

    fm_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])
    if not fm_text.strip():
        return {}, body

    try:
        parsed = _yaml_safe_load(fm_text)
    except Exception as exc:
        _diag(diagnostics, code="frontmatter_parse_failed",
              message=f"YAML 解析失败: {exc}", path=str(file_path))
        return {}, body

    if not isinstance(parsed, dict):
        return {}, body
    return parsed, body


def _yaml_safe_load(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text)
    # 最小回退
    parsed: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid line: {raw_line}")
        key, value = line.split(":", 1)
        parsed[key.strip()] = _coerce(value.strip())
    return parsed


def _coerce(raw: str) -> Any:
    if raw.startswith("[") and raw.endswith("]"):
        items = raw[1:-1].split(",")
        return [s.strip().strip("'\"") for s in items if s.strip()]
    for quote in ('"', "'"):
        if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2:
            raw = raw[1:-1]
    lower = raw.lower()
    if lower in ("true", "false"):
        return lower == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip())


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return None


def _as_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    return default


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    return default


def _diag(
    diagnostics: list[dict[str, str]],
    *,
    code: str,
    message: str,
    path: str | None = None,
    name: str | None = None,
) -> None:
    record: dict[str, str] = {"level": "warning", "code": code, "message": message}
    if path:
        record["path"] = path
    if name:
        record["name"] = name
    diagnostics.append(record)
