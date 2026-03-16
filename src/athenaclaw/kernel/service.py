"""
[INPUT]: json, pathlib, enum, agent.skills, agent.subagents, agent.messages, agent.providers (LLMProvider/LLMResult/LLMToolCall/OpenAIChatProvider)
[OUTPUT]: Kernel — 核心协调器（_do_llm_call 统一入口 + _stream_complete 流式 + tool policy + per-turn execution context）；Session — 会话容器（含 summary 摘要）；DataStore — 数据注册表；Permission — 文件权限级别；MemoryCompressor — 压缩策略接口；MEMORY_MAX_CHARS；WORKSPACE_GUIDE；skill_invoke
[POS]: agent 包核心，系统唯一协调中心：ReAct loop + 声明式 wire/emit + DataStore + 权限 + 自举 + Skill Engine + SubAgent System + stream/非 stream 双轨 LLM 调用
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

from athenaclaw.llm.messages import ContextRef, TurnInput, build_user_message, ensure_turn_input, normalize_history, render_turn_input
from athenaclaw.llm.providers import LLMProvider, LLMResult, LLMToolCall, OpenAIChatProvider
from athenaclaw.skills import (
    Skill,
    build_available_skills_prompt,
    expand_explicit_skill_command,
    invoke_skill,
    load_skills,
)
from athenaclaw.subagents.loader import load_subagents
from athenaclaw.subagents.models import SubAgentDef
from athenaclaw.subagents.system import SubAgentSystem


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

MEMORY_MAX_CHARS = 100_000

WORKSPACE_GUIDE = """\
<workspace>
你的工作区是你长期成长的外部器官。你不只是完成当前这次回复，也要在反复协作中越来越懂这位用户，越来越贴合他的需求。

<growth>
你是主动成长型 agent。
- 你珍惜用户的纠正、偏好、标准和长期反馈，把它们视为训练信号。
- 你看到值得长期保留的信息时，会主动写入 memory.md 或 soul.md；不会只口头说“记住了”。
- 成长不是过度记录。只有长期、可复用、会影响未来行为的信息才值得沉淀。
</growth>

soul.md — 你自己的人格，用第一人称写成自然、自洽的自述。
  ✅ 写入：你是谁、你如何分析、你坚持什么边界、你现在更重视什么
  ✅ 当用户长期纠正你的行为原则时：在 memory.md 记录这次反馈，并在 soul.md 内化成你自己的长期原则
  ❌ 不写：用户档案、用户持仓、用户偏好、一次性任务
  写法：保持 prose；优先局部改写，必要时整篇润色，避免补丁感。

memory.md — 你关于用户和世界的长期记忆。
  ✅ 写入：用户称呼、投资偏好、风险偏好、关注市场、关注方向、长期计划、研究结论、教练式反馈事件
  ✅ 投资场景重点关注：当用户说出自己的持仓、成本、仓位、关注方向、风险边界或长期目标时，默认先判断是否该写入 portfolio.json；memory.md 只保留高层背景和长期偏好
  ❌ 不写：你自己的信念或方法论（那是 soul 的内容）
  组织：单文件，newest-first 倒排。不要把详细持仓表写进 memory.md。
  读取：按需主动读取。当任务涉及个性化建议、历史延续、风格匹配、矛盾纠偏时，先读最近记忆。

portfolio.json — 用户的结构化当前持仓快照。
  ✅ 写入：账户、币种现金、当前持仓、更新时间
  ✅ 触发：用户发完整持仓截图、直接给出当前持仓，或明确说某笔已执行交易后当前仓位变了
  ❌ 不写：想买/想卖的计划、watchlist、模糊推测、不完整截图
  组织：单文件 JSON，按账户维护当前状态，不记录交易历史。
  读取：当任务涉及仓位分析、风险分析、集中度、相关性、个性化建议时，优先调用 portfolio 工具读取。

notebook/ — 你的工作台。研究报告、分析草稿、临时笔记。
  自由使用，无容量限制。适合阶段性产出和探索性工作。

耐久信号：
- 用户明确说“记住”“以后注意”“设为重要提醒”
- 用户透露持仓、成本、仓位、关注方向、风险偏好、投资目标
- 用户发送完整持仓截图或明确给出当前账户持仓
- 用户给出会长期影响你工作方式的纠正
- 你产出了之后还会复用的研究结论

动作规则：
- 识别到耐久信号后，优先在当前轮落盘，再继续回复。
- “记住 / 以后注意 / 重要提醒”是强触发器：只要内容有长期价值，就必须同轮写入。
- 如果 memory.md 或 soul.md 还不存在，而你刚遇到第一个明确耐久信号，就应该立即创建。
- 投资相关高价值信息默认主动落到正确的地方：详细当前持仓进 portfolio.json，高层偏好和长期背景进 memory.md。
- 未验证事实、临时任务、一次性要求、闲聊情绪，不写长期文件。

失败示例：
- 口头说“我记住了”，但没有落盘
- 把用户信息写进 soul.md
- 把你的行为原则写进 memory.md
- 把详细持仓表继续塞进 memory.md，而不是用 portfolio 工具
- 把未核实的数据写入长期记忆
</workspace>"""

AUTOMATION_GUIDE = """\
<automation_tools>
当你要创建自动化任务时，严格遵循以下规则：

1. 先调用 task_plan，拿到 draft_id 之后，再调用 task_apply。不要直接调用 task_apply。
   task_plan 的结果有三种：
   - 返回 draft_id：表示可以继续 task_apply
   - 返回 status='needs_clarification'：表示现在不能 task_apply，必须先向用户澄清
   - 返回 error：表示参数不合法，应修正后重新 task_plan
   只有第一种情况才能调用 task_apply。
2. 调用 task_apply 时，只能使用 task_plan 刚刚返回的原始 draft_id。
   不要从任务名猜 draft_id，不要自己拼接 draft-xxx，不要把 task_id/name 当 draft_id。
3. task_plan 的 task 必须使用 canonical 字段：
   - 顶层：name / description / trigger / reaction / delivery
   - 不要使用：schedule / steps / output / pipeline / action
4. cron 任务的 trigger 写法固定为：
   {
     "type": "cron",
     "cron_expr": "53 21 * * 0-4",
     "timezone": "Asia/Shanghai"
   }
   不要写 trigger.cron，不要写 schedule.at/days。
5. 价格监控任务的 trigger 写法固定为：
   {
     "type": "price_threshold",
     "symbol": "AAPL",
     "interval": "1m",
     "condition": "cross_above",
     "threshold": 220,
     "poll_sec": 60
   }
6. reaction 不是 step workflow。不要写一串 tools/steps。
   只写：
   - executor.type: main_agent / skill / subagent
   - executor.name: 仅 skill/subagent 需要
   - prompt_template: 触发后要 agent 做什么
   如果触发后需要 market_ohlcv、compute、research 等能力，让 reaction 里的 agent 自己决定调用。
7. delivery 只描述投递，不描述分析流程。
   如果当前是在 Telegram 或 Discord 会话里，并且任务要推送到当前会话：
   - 可以完全省略 delivery
   - 或只写 channel.type 为当前 IM 渠道
   - 不要自己填写当前 IM 渠道的 target，系统会自动绑定当前 conversation_id
8. 如果 task_plan 报字段错误，优先检查：
   - 是否误写了 schedule 而不是 trigger
   - 是否误写了 cron 而不是 cron_expr
   - 是否误写了 steps/output
9. 如果 task_plan 返回 needs_clarification 或 error，不要改去调用 bash/read/task_context/market_ohlcv 来“补救创建任务”。
   此时正确动作是：
   - needs_clarification：向用户提出一个简短澄清问题，或说明当前 v1 限制
   - error：修正 task 参数后重新 task_plan
10. 只有在 task_apply 返回 status='ok' 之后，才能告诉用户“任务已创建/已生效”。
11. 如果用户要求“把某个现有任务现在立刻跑一次 / 临时触发一次”，使用 task_control：
   {
     "task_id": "...",
     "action": "trigger"
   }
   这会按当前任务定义立即执行一次，不会修改原定时计划。
</automation_tools>"""


# ─────────────────────────────────────────────────────────────────────────────
# MemoryCompressor Protocol
# ─────────────────────────────────────────────────────────────────────────────

class MemoryCompressor(Protocol):
    """记忆压缩策略接口。这一版: LLM。未来: embeddings/rules/etc."""
    def compress(self, content: str, limit: int) -> str: ...


class ToolAccessPolicy(Protocol):
    """工具访问控制。返回错误字符串表示拒绝。"""

    def authorize(self, name: str, args: dict[str, Any]) -> str | None: ...


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
        data: dict = {"version": 2, "id": self.id, "history": normalize_history(self.history)}
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
        session.history = normalize_history(data["history"])
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


@dataclass(frozen=True)
class ExecutionContext:
    """单轮执行上下文。"""

    refs: tuple[ContextRef, ...] = ()

    def first_ref(self, kind: str) -> ContextRef | None:
        for ref in self.refs:
            if ref.kind == kind:
                return ref
        return None


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
        provider: LLMProvider | None = None,
        max_rounds: int = 15,
        context_window: int = 100_000,
        compact_recent_turns: int = 3,
    ) -> None:
        self.model = model
        self.max_rounds = max_rounds
        self.context_window = context_window
        self.compact_recent_turns = compact_recent_turns
        self.provider = provider or OpenAIChatProvider(
            base_url=base_url,
            api_key=api_key,
        )
        self.client = getattr(self.provider, "client", None)
        self.stream = False
        self.data = DataStore()
        self._tools: dict[str, ToolDef] = {}
        self._wires: defaultdict[str, list[Callable]] = defaultdict(list)
        self._permissions: dict[str, Permission] = {}
        self._system_prompt: str | None = None
        self._workspace: Path | None = None
        self._confirm_handler: Callable[[str], bool] | None = None
        self._skills: dict[str, Skill] = {}
        self._skill_diagnostics: list[dict[str, str]] = []
        self._subagent_system: SubAgentSystem | None = None
        self._tool_policy: ToolAccessPolicy | None = None
        self._execution_context = ExecutionContext()

    @property
    def client(self) -> Any | None:
        return getattr(self, "_client", None)

    @client.setter
    def client(self, value: Any | None) -> None:
        self._client = value
        if hasattr(self, "provider") and hasattr(self.provider, "client"):
            self.provider.client = value

    # ── 自举 ──────────────────────────────────────────────────────────────────

    def boot(
        self,
        workspace: Path,
        *,
        cwd: Path | None = None,
        skill_roots: list[Path] | None = None,
        subagent_roots: list[Path] | None = None,
    ) -> None:
        """启动：soul + workspace 使用指南 → 系统提示词"""
        self._workspace = workspace
        workspace.mkdir(parents=True, exist_ok=True)
        self._load_skills(cwd=(cwd or Path.cwd()), skill_roots=skill_roots)
        self._register_skill_invoke_tool()
        self._load_subagents(cwd=(cwd or Path.cwd()), subagent_roots=subagent_roots)
        self._assemble_system_prompt()

    def _assemble_system_prompt(self) -> None:
        """soul.md + WORKSPACE_GUIDE + skills + team → 系统提示词"""
        soul = self._workspace / "soul.md"
        if soul.exists():
            identity = soul.read_text(encoding="utf-8")
        else:
            from athenaclaw.kernel.seed import SEED_PROMPT
            identity = SEED_PROMPT
        parts = [identity, WORKSPACE_GUIDE, AUTOMATION_GUIDE]
        skills_xml = build_available_skills_prompt(self._skills)
        if skills_xml and ("read" in self._tools or "skill_invoke" in self._tools):
            parts.append(skills_xml)
        if self._subagent_system:
            team_xml = self._subagent_system.team_prompt()
            if team_xml:
                parts.append(team_xml)
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

    # ── SubAgent 加载 ─────────────────────────────────────────────────────────

    def _load_subagents(self, cwd: Path, subagent_roots: list[Path] | None) -> None:
        roots: list[tuple[Path, str]]
        if subagent_roots is not None:
            roots = [(Path(p).expanduser(), "path") for p in subagent_roots]
        else:
            roots = self._default_subagent_roots(cwd.resolve())
        definitions, diagnostics = load_subagents(roots)

        if not roots:
            return

        # 初始化 SubAgentSystem
        self._subagent_system = SubAgentSystem(
            provider=self.provider,
            model=self.model,
            get_tool_schemas=lambda: [t.schema for t in self._tools.values()],
            tool_executor=self._execute_tool,
            emit_fn=self.emit,
            max_subagents=10,
        )

        # 注册发现的定义
        for defn in definitions.values():
            self._subagent_system.register(defn)

        # 注入工具
        self._inject_subagent_tools()

        self.emit("subagents.loaded", {
            "count": len(definitions),
            "roots": [str(p) for p, _ in roots],
            "diagnostics": diagnostics,
        })

    def _default_subagent_roots(self, cwd: Path) -> list[tuple[Path, str]]:
        roots: list[tuple[Path, str]] = []
        for base in self._project_ancestors(cwd):
            roots.append((base / ".agents" / "subagents", "project"))
        user_roots = [
            Path("~/.agents/subagents"),
            Path("~/.agent/subagents"),
        ]
        roots.extend((p.expanduser(), "user") for p in user_roots)

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

    def _execute_tool(self, name: str, args: dict) -> Any:
        """工具执行器——供 SubAgent 调用父级工具"""
        tool_def = self._tools.get(name)
        if tool_def is None:
            return {"error": f"未知工具: {name}"}
        return self._call_tool(name, tool_def, args)

    def _inject_subagent_tools(self) -> None:
        """将 SubAgentSystem 生成的工具注入 Kernel"""
        if not self._subagent_system:
            return
        for name, tool_info in self._subagent_system.as_tool_defs().items():
            self._tools[name] = ToolDef(
                name=name,
                schema=tool_info["schema"],
                handler=tool_info["handler"],
            )

    def subagent(self, defn: SubAgentDef) -> dict[str, str] | None:
        """API 入口：程序化注册 SubAgent。返回 None 成功，dict 失败"""
        if self._subagent_system is None:
            self._subagent_system = SubAgentSystem(
                provider=self.provider,
                model=self.model,
                get_tool_schemas=lambda: [t.schema for t in self._tools.values()],
                tool_executor=self._execute_tool,
                emit_fn=self.emit,
            )
        err = self._subagent_system.register(defn)
        if err:
            return err
        self._inject_subagent_tools()
        self._assemble_system_prompt()
        return None

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

    def set_tool_policy(self, policy: ToolAccessPolicy | None) -> None:
        """设置当前 Kernel 的工具访问策略。"""
        self._tool_policy = policy

    def execution_context(self) -> ExecutionContext:
        """返回当前单轮执行上下文。"""
        return self._execution_context

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

    # ── LLM 调用 ─────────────────────────────────────────────────────────────

    def _do_llm_call(
        self,
        *,
        round_num: int,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> LLMResult:
        """LLM 调用统一入口：stream / 非 stream 双轨，返回统一 LLMResult。"""
        self.emit("llm.call.start", {"round": round_num})

        try:
            if self.stream and self.client is not None:
                result = self._stream_complete(
                    model=model, messages=messages,
                    tools=tools, round_num=round_num,
                )
            else:
                result = self.provider.complete(
                    model=model, messages=messages, tools=tools,
                )
        except Exception as exc:
            self.emit("llm.call.error", {
                "round": round_num,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise

        self.emit("llm.call.done", {
            "round": round_num,
            "finish_reason": result.finish_reason,
            "total_tokens": result.usage_total_tokens,
        })
        return result

    def _stream_complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        round_num: int,
    ) -> LLMResult:
        """OpenAI streaming：逐 chunk 推送 llm.chunk 事件，返回统一 LLMResult。"""
        compiled = (
            self.provider.compile_messages(messages)
            if hasattr(self.provider, "compile_messages")
            else messages
        )
        kwargs: dict[str, Any] = {"model": model, "messages": compiled, "stream": True}
        if tools:
            kwargs["tools"] = tools

        chunks = self.client.chat.completions.create(**kwargs)
        parts: list[str] = []
        tc_acc: dict[int, dict] = {}
        finish_reason = "stop"

        for chunk in chunks:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            if getattr(delta, "content", None):
                parts.append(delta.content)
                self.emit("llm.chunk", {"content": delta.content, "round": round_num})
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

        return LLMResult(
            assistant_message=msg,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage_total_tokens=0,
        )

    def _call_tool(self, name: str, tool_def: ToolDef, args: dict) -> Any:
        if self._tool_policy is not None:
            denied = self._tool_policy.authorize(name, args)
            if denied:
                return {"error": denied}
        try:
            return tool_def.handler(args)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ── ReAct loop ────────────────────────────────────────────────────────────

    def turn(self, user_input: str | TurnInput, session: Session) -> str:
        """核心：接收用户输入 → ReAct loop → 返回回复"""
        previous_ctx = self._execution_context
        turn_input = ensure_turn_input(user_input)
        self._execution_context = ExecutionContext(refs=turn_input.refs)
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            self.emit("turn.start", {"input": render_turn_input(turn_input)})
            expanded, expand_error, skill_name = expand_explicit_skill_command(
                user_input=turn_input.text,
                skills=self._skills,
            )
            final_turn_input = TurnInput(
                text=expanded or turn_input.text,
                attachments=turn_input.attachments,
                refs=turn_input.refs,
            )
            session.history.append(build_user_message(final_turn_input, date_str=today))

            if expand_error:
                session.history.append({"role": "assistant", "content": expand_error})
                self.emit(
                    "skill.expand.error",
                    {"input": turn_input.text, "skill": skill_name, "error": expand_error},
                )
                self.emit("turn.done", {"input": render_turn_input(turn_input), "reply": expand_error})
                return expand_error

            if expanded:
                self.emit("skill.expanded", {"input": turn_input.text, "skill": skill_name})

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
            from athenaclaw.llm.context import estimate_tokens, compact_history

            est = estimate_tokens(prefix + session.history)
            if est > int(self.context_window * 0.75):
                result = compact_history(
                    provider=self.provider, model=self.model,
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

                response = self._do_llm_call(
                    round_num=round_num,
                    model=self.model,
                    messages=prefix + session.history,
                    tools=tool_schemas,
                )

                # 存储 assistant 消息
                session.history.append(response.assistant_message)

                if response.finish_reason == "stop":
                    reply = str(response.assistant_message.get("content") or "")
                    break

                # 上下文溢出 → 压缩后重试
                if response.finish_reason == "length":
                    # 撤销刚添加的截断消息
                    session.history.pop()
                    result = compact_history(
                        provider=self.provider, model=self.model,
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
                if response.tool_calls:
                    for tc in response.tool_calls:
                        try:
                            args = json.loads(tc.arguments)
                        except json.JSONDecodeError:
                            args = {}
                        self.emit(
                            "tool.call.start",
                            {"name": tc.name, "args": args},
                        )
                        tool_def = self._tools.get(tc.name)
                        if tool_def:
                            result = self._call_tool(tc.name, tool_def, args)
                            self.emit(f"tool:{tc.name}", {
                                "args": args, "result": result,
                            })
                        else:
                            result = {"error": f"未知工具: {tc.name}"}
                        self.emit(
                            "tool.call.done",
                            {"name": tc.name, "result": result},
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

            self.emit("turn.done", {"input": render_turn_input(turn_input), "reply": reply})
            return reply
        finally:
            self._execution_context = previous_ctx
