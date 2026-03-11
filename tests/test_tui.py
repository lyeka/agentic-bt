"""
[INPUT]: pytest-bdd, asyncio, agent.adapters.tui, agent.kernel
[OUTPUT]: tui.feature step definitions（fixture: tuictx）
[POS]: tests/ BDD 测试层，验证 TUI 终端界面：消息收发/空输入/确认/进度/历史恢复/流式/会话/元数据
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections import defaultdict
from fnmatch import fnmatch

from pytest_bdd import given, parsers, scenario, then, when

from textual.widgets import TextArea

from agent.kernel import Session
from agent.runtime import KernelBundle
from agent.adapters.tui import InvestmentApp
from agent.adapters.tui.app import ChatInput
from agent.adapters.tui.screens import ConfirmScreen


FEATURE = "features/tui.feature"


@scenario(FEATURE, "发送消息获得回复")
def test_send_message(): pass


@scenario(FEATURE, "空输入不触发调用")
def test_empty_input(): pass


@scenario(FEATURE, "保护文件写入弹出确认")
def test_confirm_dialog(): pass


@scenario(FEATURE, "工具调用期间显示进度")
def test_tool_progress(): pass


@scenario(FEATURE, "恢复已有会话历史")
def test_restore_history(): pass


@scenario(FEATURE, "流式输出逐步渲染")
def test_streaming_output(): pass


@scenario(FEATURE, "新建会话清空聊天")
def test_new_session(): pass


@scenario(FEATURE, "助手回复显示耗时")
def test_reply_meta(): pass


@scenario(FEATURE, "Kernel 异常时显示错误提示")
def test_kernel_error(): pass


# ─────────────────────────────────────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────────────────────────────────────

class FakeKernel:
    def __init__(self) -> None:
        self._wires: dict[str, list] = defaultdict(list)
        self._confirm_handler = None
        self.turn_calls = 0
        self.model = "test-model"
        self.stream = False
        self.should_raise = False

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
        if self.should_raise:
            raise RuntimeError("LLM API 连接失败")
        session.history.append({"role": "user", "content": user_input})

        if user_input == "run":
            self.emit("tool.call.start", {"name": "market_ohlcv", "args": {}})
            self.emit("tool.call.done", {"name": "market_ohlcv", "result": {}})

        if user_input == "confirm":
            ok = self.request_confirm("soul.md")
            reply = "confirmed" if ok else "denied"
        else:
            reply = f"reply:{user_input}"

        session.history.append({"role": "assistant", "content": reply})
        return reply


class MemorySessionStore:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.saved: list[Session] = []

    def load(self) -> Session:
        return self.session

    def save(self, session: Session) -> None:
        self.saved.append(session)


def _make_ctx(tmp_path, session=None):
    kernel = FakeKernel()
    session = session or Session(session_id="test")
    store = MemorySessionStore(session)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    bundle = KernelBundle(
        kernel=kernel,
        workspace=workspace,
        state=state,
        session_store=store,
        session_path=tmp_path / "state" / "session.json",
        trace_path=tmp_path / "trace.jsonl",
    )
    return {
        "kernel": kernel,
        "bundle": bundle,
        "session": session,
        "store": store,
        "results": {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────────────────────

@given("TUI 使用 Mock Kernel 启动", target_fixture="tuictx")
def given_mock_tui(tmp_path):
    return _make_ctx(tmp_path)


@given("Kernel 的 confirm 回调已注册", target_fixture="tuictx")
def given_confirm_registered(tuictx):
    return tuictx


@given("一个包含 3 条用户消息的 Session", target_fixture="tuictx")
def given_session_with_history(tmp_path):
    session = Session(session_id="test")
    for i in range(3):
        session.history.append({"role": "user", "content": f"问题{i + 1}"})
        session.history.append({"role": "assistant", "content": f"回答{i + 1}"})
    return _make_ctx(tmp_path, session)


# ─────────────────────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────────────────────

@when(parsers.parse('用户输入 "{text}"'), target_fixture="tuictx")
def when_user_inputs(tuictx, text):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            text_area = app.query_one("#input", ChatInput)
            text_area.focus()
            text_area.insert(text)
            await pilot.pause()
            text_area.action_submit()
            await pilot.pause()
            await app.workers.wait_for_complete()
            tuictx["results"]["turn_calls"] = tuictx["kernel"].turn_calls
            tuictx["results"]["has_reply"] = bool(app.query(".assistant-msg"))
            tuictx["results"]["has_meta"] = bool(app.query(".msg-meta"))
            tuictx["results"]["app"] = app

    asyncio.run(_run())
    return tuictx


@when("用户发送空白消息", target_fixture="tuictx")
def when_user_sends_blank(tuictx):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            app.query_one("#input").focus()
            await pilot.press("enter")
            await pilot.pause()
            tuictx["results"]["turn_calls"] = tuictx["kernel"].turn_calls

    asyncio.run(_run())
    return tuictx


@when(parsers.parse('confirm 回调被触发路径为 "{path}"'), target_fixture="tuictx")
def when_confirm_triggered(tuictx, path):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            confirm_fn = tuictx["kernel"]._confirm_handler
            assert confirm_fn is not None, "App should register confirm on mount"
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(confirm_fn, path)
                for _ in range(30):
                    await pilot.pause()
                    if type(app.screen).__name__ == "ConfirmScreen":
                        break
                tuictx["results"]["screen_type"] = type(app.screen).__name__
                await pilot.press("y")
                future.result(timeout=10)

    asyncio.run(_run())
    return tuictx


@when(parsers.parse('Kernel 触发 tool.call.start 事件 name="{name}"'), target_fixture="tuictx")
def when_kernel_emits_tool_event(tuictx, name):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            done = threading.Event()

            def _emit():
                tuictx["kernel"].emit("tool.call.start", {"name": name, "args": {}})
                done.set()

            t = threading.Thread(target=_emit)
            t.start()
            done.wait(timeout=5)
            for _ in range(10):
                await pilot.pause()
            tool_widgets = app.query(".tool-status")
            tuictx["results"]["tool_texts"] = [
                str(w.render()) for w in tool_widgets
            ]

    asyncio.run(_run())
    return tuictx


@when("TUI 以该 Session 启动", target_fixture="tuictx")
def when_tui_starts_with_session(tuictx):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            user_msgs = app.query(".user-msg")
            tuictx["results"]["user_msg_count"] = len(user_msgs)

    asyncio.run(_run())
    return tuictx


@when(parsers.parse('Kernel 触发 llm.chunk 事件内容为 "{content}"'), target_fixture="tuictx")
def when_kernel_emits_chunk(tuictx, content):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            done = threading.Event()

            def _emit():
                tuictx["kernel"].emit("llm.chunk", {"content": content, "round": 1})
                done.set()

            t = threading.Thread(target=_emit)
            t.start()
            done.wait(timeout=5)
            for _ in range(20):
                await pilot.pause()
            streaming_widgets = app.query(".assistant-msg")
            tuictx["results"]["streaming_texts"] = [
                w.full_text if hasattr(w, "full_text") else ""
                for w in streaming_widgets
            ]

    asyncio.run(_run())
    return tuictx


@when("用户创建新会话", target_fixture="tuictx")
def when_user_creates_new_session(tuictx):
    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            text_area = app.query_one("#input", ChatInput)
            text_area.focus()
            text_area.insert("你好")
            await pilot.pause()
            text_area.action_submit()
            await pilot.pause()
            await app.workers.wait_for_complete()
            app.action_new_session()
            await pilot.pause()
            tuictx["results"]["chat_children"] = len(app.query_one("#chat").children)

    asyncio.run(_run())
    return tuictx


# ─────────────────────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────────────────────

@then(parsers.parse('Kernel.turn 被调用且参数为 "{text}"'))
def then_kernel_turn_called(tuictx, text):
    assert tuictx["results"]["turn_calls"] >= 1
    user_msgs = [m for m in tuictx["session"].history if m.get("role") == "user"]
    assert any(text in m.get("content", "") for m in user_msgs)


@then("聊天区域包含助手回复")
def then_chat_has_reply(tuictx):
    assert tuictx["results"]["has_reply"]


@then("Kernel.turn 未被调用")
def then_kernel_turn_not_called(tuictx):
    assert tuictx["results"]["turn_calls"] == 0


@then("界面出现确认对话框")
def then_confirm_dialog_shown(tuictx):
    assert tuictx["results"]["screen_type"] == "ConfirmScreen"


@then(parsers.parse('聊天区域包含 "{text}" 进度文本'))
def then_chat_has_progress(tuictx, text):
    tool_texts = tuictx["results"].get("tool_texts", [])
    assert any(text in t for t in tool_texts), f"Expected '{text}' in {tool_texts}"


@then(parsers.parse("聊天区域显示 {count:d} 条历史消息"))
def then_chat_shows_history(tuictx, count):
    assert tuictx["results"]["user_msg_count"] == count


@then(parsers.parse('聊天区域包含流式文本 "{text}"'))
def then_chat_has_streaming_text(tuictx, text):
    texts = tuictx["results"].get("streaming_texts", [])
    assert any(text in t for t in texts), f"Expected '{text}' in {texts}"


@then("聊天区域为空")
def then_chat_is_empty(tuictx):
    assert tuictx["results"]["chat_children"] == 0


@then("聊天区域包含耗时元数据")
def then_chat_has_meta(tuictx):
    assert tuictx["results"]["has_meta"]


@when("Kernel 在 turn 中抛出异常", target_fixture="tuictx")
def when_kernel_raises(tuictx):
    tuictx["kernel"].should_raise = True

    async def _run():
        app = InvestmentApp(tuictx["bundle"], tuictx["session"])
        async with app.run_test(size=(100, 30)) as pilot:
            text_area = app.query_one("#input", ChatInput)
            text_area.focus()
            text_area.insert("触发错误")
            await pilot.pause()
            text_area.action_submit()
            await pilot.pause()
            await app.workers.wait_for_complete()
            tuictx["results"]["has_error"] = bool(app.query(".error-msg"))

    asyncio.run(_run())
    return tuictx


@then("聊天区域包含错误提示")
def then_chat_has_error(tuictx):
    assert tuictx["results"]["has_error"]
