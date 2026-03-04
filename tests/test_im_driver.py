"""
[INPUT]: pytest-bdd, asyncio, agent.adapters.im.driver
[OUTPUT]: im_driver.feature step definitions（fixture: imctx）
[POS]: tests/ BDD 测试层，验证 IM 通用驱动层：鉴权/进度/确认/持久化
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from pytest_bdd import given, parsers, scenario, then, when

from agent.adapters.im.backend import InboundMessage, OutboundRef
from agent.adapters.im.driver import IMDriver
from agent.kernel import Session
from agent.runtime import AgentConfig, KernelBundle


FEATURE = "features/im_driver.feature"


@scenario(FEATURE, "未授权用户被拒绝")
def test_unauthorized_rejected(): pass


@scenario(FEATURE, "正常对话返回回复并持久化")
def test_normal_chat_and_persist(): pass


@scenario(FEATURE, "工具进度会更新状态消息")
def test_tool_progress_updates_status(): pass


@scenario(FEATURE, "确认交互委托给 backend")
def test_confirm_delegates_to_backend(): pass


@scenario(FEATURE, "默认不展示过程消息")
def test_default_hide_process_messages(): pass


class FakeKernel:
    def __init__(self) -> None:
        self._wires: dict[str, list] = defaultdict(list)
        self._confirm_handler = None
        self.turn_calls = 0

    def wire(self, pattern: str, handler) -> None:
        self._wires[pattern].append(handler)

    def emit(self, event: str, data=None) -> None:
        for pattern, handlers in self._wires.items():
            if fnmatch(event, pattern):
                for h in handlers:
                    h(event, data)

    def on_confirm(self, handler) -> None:
        self._confirm_handler = handler

    def request_confirm(self, path: str) -> bool:
        if self._confirm_handler is None:
            return True
        return bool(self._confirm_handler(path))

    def turn(self, user_input: str, session: Session) -> str:
        self.turn_calls += 1
        session.history.append({"role": "user", "content": user_input})

        if user_input == "run":
            self.emit("tool.call.start", {"name": "echo", "args": {"text": user_input}})
            self.emit("tool:echo", {"args": {"text": user_input}, "result": {"echo": user_input}})

        if user_input == "confirm":
            ok = self.request_confirm("soul.md")
            reply = "confirmed" if ok else "denied"
        else:
            reply = f"reply:{user_input}"

        session.history.append({"role": "assistant", "content": reply})
        return reply


@dataclass
class MemorySessionStore:
    session: Session
    saved: list[Session]

    def load(self) -> Session:
        return self.session

    def save(self, session: Session) -> None:
        # 保存引用即可，测试只关心“被调用过”
        self.saved.append(session)


class FakeBackend:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.edited: list[tuple[OutboundRef, str]] = []
        self.typing: list[str] = []
        self.confirm_prompts: list[tuple[str, str]] = []
        self.confirm_result: bool = False
        self._msg_seq = 0

    async def send_text(self, conversation_id: str, text: str) -> OutboundRef:
        self.sent.append((conversation_id, text))
        self._msg_seq += 1
        return OutboundRef(conversation_id=conversation_id, message_id=str(self._msg_seq))

    async def edit_text(self, ref: OutboundRef, text: str) -> None:
        self.edited.append((ref, text))

    async def send_typing(self, conversation_id: str) -> None:
        self.typing.append(conversation_id)

    async def ask_confirm(self, conversation_id: str, prompt: str, *, timeout_sec: int) -> bool:
        self.confirm_prompts.append((conversation_id, prompt))
        # 模拟一次异步往返
        await asyncio.sleep(0)
        return self.confirm_result


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("一个 Fake IM backend", target_fixture="imctx")
def given_backend(tmp_path):
    backend = FakeBackend()
    config = AgentConfig(
        model="test",
        base_url=None,
        api_key="test",
        tushare_token=None,
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        enable_bash=False,
        session_keep_last_user_messages=20,
    )

    kernels: dict[str, FakeKernel] = {}
    stores: dict[str, MemorySessionStore] = {}

    def bundle_factory(conversation_id: str, _cwd: Path) -> KernelBundle:
        k = FakeKernel()
        s = Session(session_id="test")
        store = MemorySessionStore(session=s, saved=[])
        kernels[conversation_id] = k
        stores[conversation_id] = store
        return KernelBundle(
            kernel=k,  # type: ignore[arg-type]
            workspace=config.workspace_dir,
            state=config.state_dir,
            session_store=store,  # type: ignore[arg-type]
            session_path=config.state_dir / "sessions" / f"{conversation_id}.json",
            trace_path=config.state_dir / "trace.jsonl",
        )

    return {
        "backend": backend,
        "config": config,
        "kernels": kernels,
        "stores": stores,
        "bundle_factory": bundle_factory,
    }


@given(parsers.parse('一个 IM driver（allowlist 含 "{user_id}"）'), target_fixture="imctx")
def given_driver(imctx, user_id):
    driver = IMDriver(
        backend=imctx["backend"],
        adapter_name="test",
        config=imctx["config"],
        allowed_user_ids={user_id},
        confirm_timeout_sec=2,
        status_edit_throttle_sec=0.0,
        show_process_messages=True,
        bundle_factory=imctx["bundle_factory"],
    )
    imctx["driver"] = driver
    return imctx


@given(parsers.parse('一个默认 IM driver（allowlist 含 "{user_id}"）'), target_fixture="imctx")
def given_default_driver(imctx, user_id):
    driver = IMDriver(
        backend=imctx["backend"],
        adapter_name="test",
        config=imctx["config"],
        allowed_user_ids={user_id},
        confirm_timeout_sec=2,
        status_edit_throttle_sec=0.0,
        bundle_factory=imctx["bundle_factory"],
    )
    imctx["driver"] = driver
    return imctx


@given("backend 确认答案为 approve", target_fixture="imctx")
def given_confirm_answer_approve(imctx):
    imctx["backend"].confirm_result = True
    return imctx


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('用户 "{user_id}" 在会话 "{conv}" 发送 "{text}"'), target_fixture="imctx")
def when_user_sends(imctx, user_id, conv, text):
    driver: IMDriver = imctx["driver"]
    msg = InboundMessage(
        adapter="test",
        conversation_id=conv,
        user_id=user_id,
        is_private=True,
        text=text,
        message_id="m1",
        ts=datetime.now(),
    )

    async def _run() -> None:
        await driver.handle(msg)
        # 给 edit_text 的 flush task 一个 event loop tick
        await asyncio.sleep(0)

    asyncio.run(_run())
    return imctx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then("backend 发送拒绝消息")
def then_backend_rejected(imctx):
    texts = [t for _cid, t in imctx["backend"].sent]
    assert any("未授权" in t for t in texts)


@then("kernel 未被调用")
def then_kernel_not_called(imctx):
    # 未授权直接返回，不会创建 chat/kernel
    assert imctx["kernels"] == {}


@then("backend 发送状态消息")
def then_backend_sent_status(imctx):
    assert imctx["backend"].sent
    first = imctx["backend"].sent[0][1]
    assert "思考中" in first


@then(parsers.parse('backend 发送最终回复 "{text}"'))
def then_backend_sent_final_reply(imctx, text):
    texts = [t for _cid, t in imctx["backend"].sent]
    assert any(t == text for t in texts)


@then("session 被持久化")
def then_session_persisted(imctx):
    assert "c1" in imctx["stores"]
    store = imctx["stores"]["c1"]
    assert len(store.saved) >= 1


@then(parsers.parse('backend 编辑状态消息包含 "{needle}"'))
def then_backend_edited_status_contains(imctx, needle):
    edited_texts = [t for _ref, t in imctx["backend"].edited]
    assert any(needle in t for t in edited_texts)


@then("backend 收到确认请求")
def then_backend_received_confirm(imctx):
    assert len(imctx["backend"].confirm_prompts) >= 1


@then("backend 不发送状态消息")
def then_backend_not_sent_status(imctx):
    texts = [t for _cid, t in imctx["backend"].sent]
    assert all("思考中" not in t for t in texts)


@then("backend 不编辑状态消息")
def then_backend_not_edited_status(imctx):
    assert len(imctx["backend"].edited) == 0
