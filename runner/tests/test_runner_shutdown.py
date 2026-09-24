"""R31 runner_shutdown 协议用例:收到指令 → 回 result(ok)→ 置退出标志(_receive_loop 据此结束)

不依赖真实连接:handle_message 直驱,fake ws 捕获 send。
"""
import asyncio
import json

import pytest

import main as runner_main


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    runner_main._SHUTDOWN_REQUESTED = False
    yield
    runner_main._SHUTDOWN_REQUESTED = False


@pytest.mark.asyncio
async def test_runner_shutdown_replies_and_sets_flag():
    """收 runner_shutdown:先回 result(req_id, ok=True),后置退出标志"""
    ws = FakeWS()
    msg = {"type": "runner_shutdown", "req_id": "r-1"}

    await runner_main.handle_message(ws, msg)

    assert runner_main._SHUTDOWN_REQUESTED is True
    # 回包恰一条 result 且结算该 req_id
    results = [p for p in ws.sent if p.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["req_id"] == "r-1"
    assert results[0]["ok"] is True


@pytest.mark.asyncio
async def test_receive_loop_returns_after_shutdown():
    """_receive_loop 处理完 runner_shutdown 即 return(驱动 session 收尾退出)"""
    payloads = [
        json.dumps({"type": "runner_shutdown", "req_id": "r-2"}),
        json.dumps({"type": "heartbeat"}),  # 不应被消费(标志先行返回)
    ]

    class IterWS(FakeWS):
        def __aiter__(self):
            async def gen():
                for p in payloads:
                    yield p
            return gen()

    iws = IterWS()
    await asyncio.wait_for(runner_main._receive_loop(iws), timeout=2)

    assert runner_main._SHUTDOWN_REQUESTED is True
    # shutdown 的 result 已回;heartbeat 未被处理(标志置位后循环 return)
    assert any(p.get("type") == "result" and p.get("req_id") == "r-2" for p in iws.sent)


@pytest.mark.asyncio
async def test_other_message_does_not_set_flag():
    """无关指令不影响退出标志(回归:非 shutdown 消息只走原分支)"""
    ws = FakeWS()
    # 未知指令仅告警,不置标志(避免依赖 terminals 真实状态)
    await runner_main.handle_message(ws, {"type": "__unknown_type__"})
    assert runner_main._SHUTDOWN_REQUESTED is False
