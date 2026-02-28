"""
[INPUT]: openai, json, pathlib, enum
[OUTPUT]: Kernel — 核心协调器；Session — 会话容器；DataStore — 数据注册表；Permission — 文件权限级别
[POS]: agent 包核心，系统唯一协调中心：ReAct loop + 声明式 wire/emit + DataStore + 权限 + 自举
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable

import openai


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
    """会话容器 — 维护完整消息历史 + 持久化"""

    def __init__(self, session_id: str = "default") -> None:
        self.id = session_id
        self.history: list[dict] = []

    def save(self, path: Path) -> None:
        """持久化到 JSON"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"id": self.id, "history": self.history},
            ensure_ascii=False, indent=2,
        ), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Session:
        """从 JSON 恢复"""
        data = json.loads(path.read_text(encoding="utf-8"))
        session = cls(session_id=data["id"])
        session.history = data["history"]
        return session


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
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
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

    # ── 自举 ──────────────────────────────────────────────────────────────────

    def boot(self, workspace: Path) -> None:
        """启动：检测 soul.md → 注入系统提示词"""
        self._workspace = workspace
        workspace.mkdir(parents=True, exist_ok=True)
        soul = workspace / "soul.md"
        if soul.exists():
            self._system_prompt = soul.read_text(encoding="utf-8")
        else:
            from agent.bootstrap.seed import SEED_PROMPT
            self._system_prompt = SEED_PROMPT

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
        self.emit("turn.start", {"input": user_input})
        session.history.append({"role": "user", "content": user_input})

        tool_schemas = [t.schema for t in self._tools.values()] or None
        prefix = (
            [{"role": "system", "content": self._system_prompt}]
            if self._system_prompt else []
        )
        reply = ""

        for _ in range(self.max_rounds):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": prefix + session.history,
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # 存储 assistant 消息
            session.history.append(_msg_to_dict(choice.message))

            if choice.finish_reason == "stop":
                reply = choice.message.content or ""
                break

            # 工具调用
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    tool_def = self._tools.get(tc.function.name)
                    if tool_def:
                        result = tool_def.handler(args)
                        self.emit(f"tool:{tc.function.name}", {
                            "args": args, "result": result,
                        })
                    else:
                        result = {"error": f"未知工具: {tc.function.name}"}

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
