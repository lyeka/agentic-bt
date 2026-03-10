"""
[INPUT]: openai, json, pathlib, enum, agent.skills
[OUTPUT]: Kernel — 核心协调器；Session — 会话容器（含 summary 摘要）；DataStore — 数据注册表；Permission — 文件权限级别；MemoryCompressor — 压缩策略接口；MEMORY_MAX_CHARS；WORKSPACE_GUIDE；skill_invoke
[POS]: agent 包核心，系统唯一协调中心：ReAct loop + 声明式 wire/emit + DataStore + 权限 + 自举 + Skill Engine
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable, Protocol

import openai

from agent.skills import (
    Skill,
    build_available_skills_prompt,
    expand_explicit_skill_command,
    invoke_skill,
    load_skills,
)


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

MEMORY_MAX_CHARS = 100_000

WORKSPACE_GUIDE = """\
<workspace>
你的工作区有三个区域，各有不同的用途和修改门槛：

soul.md — 你自己的人格。描述你这个 agent 是谁，用第一人称。
  ✅ 写入："我相信..."、"我的分析方法是..."、"我的行事原则是..."
  ❌ 不写："服务对象是..."、"用户喜欢..."（那是关于用户的，不是你的人格）
  修改门槛：极高。只在认知发生根本性转变时修改。需要用户确认。
  首次创建：不急。先通过自然对话形成真实的角色感知，再落笔。

memory.md — 你关于用户和世界的记忆。描述你知道的外部信息。
  ✅ 写入：用户称呼、用户投资偏好、关注标的、市场观察、研究结论
  ❌ 不写：你自己的信念或方法论（那是 soul 的内容）
  格式：newest-first 倒排，最新条目写在文件顶部。
  读取：用 read 查看最近记忆，用 bash grep 检索特定主题。
  容量：有上限，超限时系统会自动压缩旧记忆。

notebook/ — 你的工作台。研究报告、分析草稿、临时笔记。
  自由使用，无容量限制。适合阶段性产出和探索性工作。
</workspace>"""


# ─────────────────────────────────────────────────────────────────────────────
# MemoryCompressor Protocol
# ─────────────────────────────────────────────────────────────────────────────

class MemoryCompressor(Protocol):
    """记忆压缩策略接口。这一版: LLM。未来: embeddings/rules/etc."""
    def compress(self, content: str, limit: int) -> str: ...


# ─────────────────────────────────────────────────────────────────────────────
# Permission
# ─────────────────────────────────────────────────────────────────────────────

class Permission(Enum):
    """文件路径权限级别"""
    FREE = "free"
    REASON_REQUIRED = "reason_required"
    USER_CONFIRM = "user_confirm"


# ─────────────────────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────────────────────

class Session:
    """会话容器 — 维护完整消息历史 + 对话摘要 + 持久化"""

    def __init__(self, session_id: str = "default") -> None:
        self.id = session_id
        self.history: list[dict] = []
        self.summary: str | None = None

    def save(self, path: Path) -> None:
        """持久化到 JSON"""
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {"id": self.id, "history": self.history}
        if self.summary:
            data["summary"] = self.summary
        path.write_text(json.dumps(
            data, ensure_ascii=False, indent=2,
        ), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Session:
        """从 JSON 恢复（自动修复残缺历史，兼容旧格式无 summary）"""
        data = json.loads(path.read_text(encoding="utf-8"))
        session = cls(session_id=data["id"])
        session.history = data["history"]
        session.summary = data.get("summary")
        session.repair()
        return session

    def prune(self, keep_last_user_messages: int = 20) -> None:
        """保留最近 N 轮 user 消息及其后续内容，裁剪更早的历史"""
        if keep_last_user_messages <= 0 or not self.history:
            return
        user_count = 0
        cut = 0
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i].get("role") == "user":
                user_count += 1
                if user_count >= keep_last_user_messages:
                    cut = i
                    break
        if cut > 0:
            self.history = self.history[cut:]

    def repair(self) -> None:
        """修复残缺历史：移除末尾缺少 tool response 的 assistant 消息"""
        if not self.history:
            return
        last = self.history[-1]
        if last.get("role") != "assistant" or not last.get("tool_calls"):
            return
        # assistant 有 tool_calls 但后面没有 tool response → 截断
        self.history.pop()


# ─────────────────────────────────────────────────────────────────────────────
# DataStore
# ─────────────────────────────────────────────────────────────────────────────

class DataStore:
    """内核数据注册表 — key-value 存取"""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set(self, key: str, data: Any) -> None:
        self._store[key] = data

    def get(self, key: str) -> Any | None:
        return self._store.get(key)


# ─────────────────────────────────────────────────────────────────────────────
# Kernel
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolDef:
    """工具定义：名称 + OpenAI schema + 处理函数"""
    name: str
    schema: dict
    handler: Callable


class Kernel:
    """
    持久投资助手核心协调器。

    唯一协调中心：ReAct loop + 声明式 wire/emit 管道 + DataStore + 权限 + 自举。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        api_key: str | None = None,
        max_rounds: int = 15,
        context_window: int = 100_000,
        compact_recent_turns: int = 3,
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
        self.context_window = context_window
        self.compact_recent_turns = compact_recent_turns
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )
        self.data = DataStore()
        self._tools: dict[str, ToolDef] = {}
        self._wires: defaultdict[str, list[Callable]] = defaultdict(list)
        self._permissions: dict[str, Permission] = {}
        self._system_prompt: str | None = None
        self._workspace: Path | None = None
        self._confirm_handler: Callable[[str], bool] | None = None
        self._skills: dict[str, Skill] = {}
        self._skill_diagnostics: list[dict[str, str]] = []

    # ── 自举 ──────────────────────────────────────────────────────────────────

    def boot(
        self,
        workspace: Path,
        *,
        cwd: Path | None = None,
        skill_roots: list[Path] | None = None,
    ) -> None:
        """启动：soul + workspace 使用指南 → 系统提示词"""
        self._workspace = workspace
        workspace.mkdir(parents=True, exist_ok=True)
        self._load_skills(cwd=(cwd or Path.cwd()), skill_roots=skill_roots)
        self._register_skill_invoke_tool()
        self._assemble_system_prompt()

    def _assemble_system_prompt(self) -> None:
        """soul.md + WORKSPACE_GUIDE → 系统提示词。Memory 内容不进入。"""
        soul = self._workspace / "soul.md"
        if soul.exists():
            identity = soul.read_text(encoding="utf-8")
        else:
            from agent.bootstrap.seed import SEED_PROMPT
            identity = SEED_PROMPT
        parts = [identity, WORKSPACE_GUIDE]
        skills_xml = build_available_skills_prompt(self._skills)
        if skills_xml and ("read" in self._tools or "skill_invoke" in self._tools):
            parts.append(skills_xml)
        self._system_prompt = "\n\n".join(parts)

    def _load_skills(self, cwd: Path, skill_roots: list[Path] | None) -> None:
        roots: list[tuple[Path, str]]
        if skill_roots is not None:
            roots = [(Path(path).expanduser(), "path") for path in skill_roots]
        else:
            roots = self._default_skill_roots(cwd.resolve())
        self._skills, self._skill_diagnostics = load_skills(roots)
        self.emit(
            "skills.loaded",
            {
                "count": len(self._skills),
                "roots": [str(path) for path, _source in roots],
                "diagnostics": self._skill_diagnostics,
            },
        )

    def _default_skill_roots(self, cwd: Path) -> list[tuple[Path, str]]:
        roots: list[tuple[Path, str]] = []

        # 1) 显式路径（环境变量）
        env_paths = os.getenv("SKILL_PATHS", "").strip()
        if env_paths:
            for raw in env_paths.split(os.pathsep):
                raw = raw.strip()
                if raw:
                    roots.append((Path(raw).expanduser(), "path"))

        # 2) 项目级路径：从 cwd 向上直到 git root
        for base in self._project_ancestors(cwd):
            roots.append((base / ".agents" / "skills", "project"))
            roots.append((base / ".pi" / "skills", "project"))

        # 3) 用户级路径
        user_roots = [
            Path("~/.agents/skills"),
            Path("~/.pi/agent/skills"),
            Path("~/.agent/skills"),
            Path("~/.claude/skills"),
            Path("~/.codex/skills"),
            Path("~/.cursor/skills"),
        ]
        roots.extend((path.expanduser(), "user") for path in user_roots)

        # 保序去重
        unique: list[tuple[Path, str]] = []
        seen: set[Path] = set()
        for path, source in roots:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append((resolved, source))
        return unique

    def _project_ancestors(self, cwd: Path) -> list[Path]:
        git_root = self._find_git_root(cwd)
        if git_root is None:
            return [cwd]
        result: list[Path] = []
        current = cwd
        while True:
            result.append(current)
            if current == git_root:
                break
            current = current.parent
        return result

    @staticmethod
    def _find_git_root(start: Path) -> Path | None:
        current = start
        while True:
            if (current / ".git").exists():
                return current
            if current.parent == current:
                return None
            current = current.parent

    def _register_skill_invoke_tool(self) -> None:
        def skill_invoke_handler(args: dict) -> dict:
            name = str(args.get("name", "")).strip()
            if not name:
                return {"error": "缺少参数: name"}
            skill_args = str(args.get("args", "")).strip()
            result = invoke_skill(name=name, args=skill_args, skills=self._skills)
            self.emit(
                "skill.invoke",
                {"name": name, "args": skill_args, "error": result.get("error")},
            )
            return result

        self.tool(
            name="skill_invoke",
            description="加载指定 skill 的完整正文与展开内容，供后续执行该技能工作流",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "skill 名称"},
                    "args": {"type": "string", "description": "可选：用户参数或补充上下文"},
                },
                "required": ["name"],
            },
            handler=skill_invoke_handler,
        )

    # ── 工具注册 ──────────────────────────────────────────────────────────────

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
    ) -> None:
        """注册工具"""
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._tools[name] = ToolDef(name=name, schema=schema, handler=handler)

    # ── 权限 ──────────────────────────────────────────────────────────────────

    def permission(self, pattern: str, level: Permission) -> None:
        """声明路径权限级别"""
        self._permissions[pattern] = level

    def check_permission(self, path: str) -> Permission:
        """检查路径权限（fnmatch 模式匹配）"""
        for pattern, level in self._permissions.items():
            if fnmatch(path, pattern):
                return level
        return Permission.FREE

    def on_confirm(self, handler: Callable[[str], bool]) -> None:
        """注册确认回调（CLI 弹 y/n 等）"""
        self._confirm_handler = handler

    def request_confirm(self, path: str) -> bool:
        """请求用户确认。无 handler 时默认放行（yolo）"""
        if self._confirm_handler is None:
            return True
        return self._confirm_handler(path)

    # ── 声明式管道 ────────────────────────────────────────────────────────────

    def wire(self, pattern: str, handler: Callable) -> None:
        """注册管道处理器（支持 fnmatch 模式）"""
        self._wires[pattern].append(handler)

    def emit(self, event: str, data: Any = None) -> None:
        """触发匹配的管道处理器"""
        for pattern, handlers in self._wires.items():
            if fnmatch(event, pattern):
                for h in handlers:
                    h(event, data)

    # ── ReAct loop ────────────────────────────────────────────────────────────

    def turn(self, user_input: str, session: Session) -> str:
        """核心：接收用户输入 → ReAct loop → 返回回复"""
        today = datetime.now().strftime("%Y-%m-%d")
        self.emit("turn.start", {"input": user_input})
        expanded, expand_error, skill_name = expand_explicit_skill_command(
            user_input=user_input,
            skills=self._skills,
        )
        final_user_input = expanded or user_input
        dated_input = f"[{today}]\n{final_user_input}"
        session.history.append({"role": "user", "content": dated_input})

        if expand_error:
            session.history.append({"role": "assistant", "content": expand_error})
            self.emit(
                "skill.expand.error",
                {"input": user_input, "skill": skill_name, "error": expand_error},
            )
            self.emit("turn.done", {"input": user_input, "reply": expand_error})
            return expand_error

        if expanded:
            self.emit("skill.expanded", {"input": user_input, "skill": skill_name})

        tool_schemas = [t.schema for t in self._tools.values()] or None

        # prefix: system prompt + 对话摘要注入
        system_content = self._system_prompt or ""
        if session.summary:
            system_content += (
                "\n\n## 前段对话摘要\n"
                "以下是之前对话的压缩摘要，不是新消息。基于此背景继续对话：\n\n"
                f"{session.summary}"
            )
        prefix = (
            [{"role": "system", "content": system_content}]
            if system_content else []
        )

        # 自动压缩：token > 75% context window 时触发
        from agent.context_ops import estimate_tokens, compact_history

        est = estimate_tokens(prefix + session.history)
        if est > int(self.context_window * 0.75):
            result = compact_history(
                client=self.client, model=self.model,
                history=session.history, recent_turns=self.compact_recent_turns,
            )
            session.history = result.retained
            if result.summary:
                session.summary = (
                    f"{session.summary}\n\n{result.summary}" if session.summary else result.summary
                )
            self.emit("context.compacted", {
                "trigger": "auto",
                "messages_before": result.compressed_count + result.retained_count,
                "messages_after": result.retained_count,
                "messages_compressed": result.compressed_count,
                "messages_retained": result.retained_count,
                "tokens_before": est,
                "tokens_after": estimate_tokens(prefix + session.history),
                "summary_chars": len(result.summary),
                "summary": result.summary,
            })
            # 重建 prefix（摘要可能已变）
            system_content = self._system_prompt or ""
            if session.summary:
                system_content += (
                    "\n\n## 前段对话摘要\n"
                    "以下是之前对话的压缩摘要，不是新消息。基于此背景继续对话：\n\n"
                    f"{session.summary}"
                )
            prefix = (
                [{"role": "system", "content": system_content}]
                if system_content else []
            )

        reply = ""

        for i in range(self.max_rounds):
            round_num = i + 1
            self.emit("turn.round", {"round": round_num, "max": self.max_rounds})
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": prefix + session.history,
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            self.emit("llm.call.start", {"round": round_num})
            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
            self.emit(
                "llm.call.done",
                {
                    "round": round_num,
                    "finish_reason": choice.finish_reason,
                    "total_tokens": tokens,
                },
            )

            # 存储 assistant 消息
            session.history.append(_msg_to_dict(choice.message))

            if choice.finish_reason == "stop":
                reply = choice.message.content or ""
                break

            # 上下文溢出 → 压缩后重试
            if choice.finish_reason == "length":
                # 撤销刚添加的截断消息
                session.history.pop()
                result = compact_history(
                    client=self.client, model=self.model,
                    history=session.history, recent_turns=self.compact_recent_turns,
                )
                session.history = result.retained
                if result.summary:
                    session.summary = (
                        f"{session.summary}\n\n{result.summary}" if session.summary else result.summary
                    )
                self.emit("context.compacted", {
                    "trigger": "overflow",
                    "messages_compressed": result.compressed_count,
                    "messages_retained": result.retained_count,
                    "summary": result.summary,
                })
                # 重建 prefix
                system_content = self._system_prompt or ""
                if session.summary:
                    system_content += (
                        "\n\n## 前段对话摘要\n"
                        "以下是之前对话的压缩摘要，不是新消息。基于此背景继续对话：\n\n"
                        f"{session.summary}"
                    )
                prefix = (
                    [{"role": "system", "content": system_content}]
                    if system_content else []
                )
                continue

            # 工具调用
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    self.emit(
                        "tool.call.start",
                        {"name": tc.function.name, "args": args},
                    )
                    tool_def = self._tools.get(tc.function.name)
                    if tool_def:
                        try:
                            result = tool_def.handler(args)
                        except Exception as exc:
                            result = {"error": f"{type(exc).__name__}: {exc}"}
                        self.emit(f"tool:{tc.function.name}", {
                            "args": args, "result": result,
                        })
                    else:
                        result = {"error": f"未知工具: {tc.function.name}"}
                    self.emit(
                        "tool.call.done",
                        {"name": tc.function.name, "result": result},
                    )

                    session.history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    })
        else:
            # max_rounds 耗尽
            reply = f"[max_rounds={self.max_rounds} 耗尽]"
            session.history.append({"role": "assistant", "content": reply})

        self.emit("turn.done", {"input": user_input, "reply": reply})
        return reply


# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────

def _msg_to_dict(msg: Any) -> dict:
    """OpenAI message 对象 → dict"""
    d: dict[str, Any] = {"role": msg.role, "content": msg.content}
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
