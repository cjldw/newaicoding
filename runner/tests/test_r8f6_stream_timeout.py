"""R8.F6 runner 侧:claude_prompt_stream 超时守卫用例

挂点:--session-id 被容器内交互 claude 占用 + --permission-prompt-tool 下
bridge.py 阻塞 stdin → sock.recv 无限挂死(详见 hang-analysis.md)。
修复:首趟/降级重跑均套 asyncio.wait_for(timeout=STREAM_TIMEOUT);
超时 → cancel_claude(container_id) + error="stream_timeout" 回报。

用例:
- 首趟挂起(超时)→ 断言 cancel 被调、回报 error="stream_timeout"
- 正常返回不触发 cancel
"""
import asyncio
import json
import threading
import time

import pytest

import main as runner_main


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class HangingManager:
    """manager 替身:claude_prompt_stream 长时间阻塞(模拟 sock.recv 挂死)。
    用短 sleep 循环而非 Event.wait,使线程可在超时后快速退出(不阻塞 pytest 收尾)。"""

    def __init__(self):
        self.killed: list[str] = []
        self.stream_calls = 0

    def claude_prompt_stream(self, container_id, prompt, **kw):
        self.stream_calls += 1
        # 模拟无限挂死 —— 50ms 步进 sleep 总计 30s,足够触发 0.3s 超时
        # 循环退出后线程自然结束,不阻塞 pytest 事件循环收尾
        for _ in range(600):
            time.sleep(0.05)
        return {"result": "", "tokens_in": 0, "tokens_out": 0, "lines": 0}

    def cancel_claude(self, container_id):
        self.killed.append(container_id)
        return True

    def setup_permission_bridge(self, container_id):
        return True

    def cleanup_permission_bridge(self, container_id):
        pass


class NormalManager:
    """manager 替身:claude_prompt_stream 正常返回"""

    def __init__(self):
        self.killed: list[str] = []
        self.stream_calls = 0

    def claude_prompt_stream(self, container_id, prompt, **kw):
        self.stream_calls += 1
        return {"result": "pong", "tokens_in": 1, "tokens_out": 1, "lines": 2}

    def cancel_claude(self, container_id):
        self.killed.append(container_id)
        return True

    def setup_permission_bridge(self, container_id):
        return True

    def cleanup_permission_bridge(self, container_id):
        pass


@pytest.fixture()
def fake_manager(monkeypatch):
    runner_main._active_execs.clear()
    runner_main._cancelled_execs.clear()
    yield None
    runner_main._active_execs.clear()
    runner_main._cancelled_execs.clear()


@pytest.mark.asyncio
async def test_stream_timeout_kills_and_reports(monkeypatch, fake_manager):
    """首趟挂起(超时)→ cancel 被调 + 回报 error=stream_timeout"""
    mgr = HangingManager()
    monkeypatch.setattr(runner_main, "manager", mgr)
    # 缩短超时窗口使测试快速完成
    monkeypatch.setattr(runner_main, "STREAM_TIMEOUT", 0.3)

    ws = FakeWS()
    await runner_main.handle_message(ws, {
        "type": "exec_tool", "req_id": "r1", "tool": "claude_prompt_stream",
        "container_id": "c1", "task_id": "t1",
        "args": {"prompt": "p", "session_id": "s1"},
    })

    # cancel_claude 被调(杀容器内 claude 进程树)
    assert mgr.killed == ["c1"]
    # 回报 error="stream_timeout"(不是 cancelled,不是 ok)
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["req_id"] == "r1"
    assert results[0]["ok"] is False
    assert results[0]["error"] == "stream_timeout"
    # 在途登记已清理
    assert "r1" not in runner_main._active_execs


@pytest.mark.asyncio
async def test_stream_normal_return_no_cancel(monkeypatch, fake_manager):
    """正常返回不触发 cancel,终态 ok=True"""
    mgr = NormalManager()
    monkeypatch.setattr(runner_main, "manager", mgr)
    monkeypatch.setattr(runner_main, "STREAM_TIMEOUT", 5.0)

    ws = FakeWS()
    await runner_main.handle_message(ws, {
        "type": "exec_tool", "req_id": "r2", "tool": "claude_prompt_stream",
        "container_id": "c2", "task_id": "t2",
        "args": {"prompt": "p"},
    })

    # 不触发 cancel
    assert mgr.killed == []
    # 终态 ok=True
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["data"]["result"] == "pong"
