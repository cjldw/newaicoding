"""R34 runner 侧:exec_tool_cancel 对话真取消协议用例

不依赖真实连接/docker:handle_message 直驱 + manager 替身(fake ws 捕获 send)。
- exec_tool_cancel 命中在途 exec → pkill 容器(manager.cancel_claude)→ 原请求
  终态按 ok=False(error="cancelled")回报,终态后在途登记清理
- 无在途执行时幂等(不 pkill、不回任何包)
- 已取消的流式请求:零行来自取消,BUG-060 resume 降级重跑被跳过
- 未取消路径回归:终态仍 ok=True
"""
import asyncio
import json
import threading

import pytest

import main as runner_main


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class FakeManager:
    """manager 替身:claude 执行可用 gate 阻塞以模拟「在途」窗口"""

    def __init__(self):
        self.killed: list[str] = []
        self.stream_calls = 0
        self._gate = threading.Event()
        self._gate.set()  # 默认放行;hold() 才阻塞

    def hold(self):
        self._gate.clear()

    def release(self):
        self._gate.set()

    def claude_prompt(self, container_id, prompt, **kw):
        self._gate.wait(timeout=2)
        return {"result": "ok", "tokens_in": 1, "tokens_out": 1}

    def claude_prompt_stream(self, container_id, prompt, **kw):
        self.stream_calls += 1
        self._gate.wait(timeout=2)
        return {"result": "", "tokens_in": 0, "tokens_out": 0, "lines": 0}

    def cancel_claude(self, container_id):
        self.killed.append(container_id)
        return True


@pytest.fixture()
def fake_manager(monkeypatch):
    mgr = FakeManager()
    monkeypatch.setattr(runner_main, "manager", mgr)
    runner_main._active_execs.clear()
    runner_main._cancelled_execs.clear()
    yield mgr
    runner_main._active_execs.clear()
    runner_main._cancelled_execs.clear()


async def _wait_registered(req_id: str) -> None:
    """等待 exec_tool 完成在途登记(handle_message 任务调度后的窗口)"""
    for _ in range(200):
        if req_id in runner_main._active_execs:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"exec_tool 未登记在途 req_id={req_id}")


@pytest.mark.asyncio
async def test_exec_tool_cancel_kills_and_settles_cancelled(fake_manager):
    """取消在途 claude_prompt:pkill 容器 → 终态 ok=False(error=cancelled)→ 登记清理"""
    ws = FakeWS()
    fake_manager.hold()
    exec_task = asyncio.create_task(runner_main.handle_message(ws, {
        "type": "exec_tool", "req_id": "r1", "tool": "claude_prompt",
        "container_id": "c1", "args": {"prompt": "p"},
    }))
    await _wait_registered("r1")

    await runner_main.handle_message(ws, {"type": "exec_tool_cancel", "req_id": "r1"})
    assert fake_manager.killed == ["c1"]
    assert "r1" in runner_main._cancelled_execs

    fake_manager.release()
    await asyncio.wait_for(exec_task, timeout=2)

    # 终态恰一条 result:ok=False + error=cancelled;取消指令自身不回包
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["req_id"] == "r1"
    assert results[0]["ok"] is False
    assert results[0]["error"] == "cancelled"
    assert "r1" not in runner_main._active_execs
    assert "r1" not in runner_main._cancelled_execs


@pytest.mark.asyncio
async def test_exec_tool_cancel_without_active_exec_is_noop(fake_manager):
    """无在途执行:不 pkill、不回任何包(火后不理)"""
    ws = FakeWS()
    await runner_main.handle_message(ws, {"type": "exec_tool_cancel", "req_id": "ghost"})
    assert fake_manager.killed == []
    assert ws.sent == []


@pytest.mark.asyncio
async def test_cancelled_stream_skips_resume_fallback(fake_manager):
    """已取消的流式请求:零行来自取消,BUG-060 降级重跑必须被跳过"""
    ws = FakeWS()
    fake_manager.hold()
    exec_task = asyncio.create_task(runner_main.handle_message(ws, {
        "type": "exec_tool", "req_id": "r2", "tool": "claude_prompt_stream",
        "container_id": "c2", "task_id": "t1",
        "args": {"prompt": "p", "session_id": "s1", "resume": True},
    }))
    await _wait_registered("r2")

    await runner_main.handle_message(ws, {"type": "exec_tool_cancel", "req_id": "r2"})
    fake_manager.release()
    await asyncio.wait_for(exec_task, timeout=2)

    assert fake_manager.stream_calls == 1
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert results[0]["ok"] is False
    assert results[0]["error"] == "cancelled"


@pytest.mark.asyncio
async def test_exec_tool_without_cancel_reports_ok(fake_manager):
    """回归:未取消路径终态仍 ok=True,终态后在途登记清空"""
    ws = FakeWS()
    await runner_main.handle_message(ws, {
        "type": "exec_tool", "req_id": "r3", "tool": "claude_prompt",
        "container_id": "c1", "args": {"prompt": "p"},
    })
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert runner_main._active_execs == {}
