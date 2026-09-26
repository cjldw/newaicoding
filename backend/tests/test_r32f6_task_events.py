"""
R32.F6(BUG-057/058)任务事件推送链 - TDD 测试
================================================
BUG-057:TaskEventRegistry 把 dict 塞进 set → TypeError → 端点崩、注册表永远空,
广播 conns=0,前端永远收不到 chat_delta/chat_done/活动流。
BUG-058:claude stream-json 按 turn 整块输出;--include-partial-messages 的
stream_event/content_block_delta 应映射为 chat_delta 文本增量。
"""
import pytest

from app.services.task_service import TaskEventRegistry, _stream_event_to_chat


class _FakeWs:
    """send_json 替身:记录收到的帧;可注入异常模拟断连"""

    def __init__(self, fail=False):
        self.frames: list[dict] = []
        self._fail = fail

    async def send_json(self, payload: dict) -> None:
        if self._fail:
            raise RuntimeError("connection gone")
        self.frames.append(payload)


@pytest.mark.asyncio
async def test_registry_connect_broadcast_disconnect():
    """核心判据:connect 后 broadcast 能送达;disconnect 后不再送达(且不抛 TypeError)"""
    reg = TaskEventRegistry()
    ws = _FakeWs()
    conn = reg.connect("t1", ws)  # BUG-057:这里曾 TypeError: unhashable type: 'dict'

    sent = await reg.broadcast("t1", {"type": "chat_delta", "text": "你"})
    assert sent == 1
    assert ws.frames == [{"type": "chat_delta", "text": "你"}]

    reg.disconnect("t1", conn)
    sent = await reg.broadcast("t1", {"type": "chat_done"})
    assert sent == 0


@pytest.mark.asyncio
async def test_registry_multi_client_and_dead_conn_cleanup():
    """多订阅者都收到;坏连接自动摘除不拖垮其他订阅者"""
    reg = TaskEventRegistry()
    good, bad = _FakeWs(), _FakeWs(fail=True)
    reg.connect("t2", good)
    reg.connect("t2", bad)

    sent = await reg.broadcast("t2", {"type": "chat_delta", "text": "好"})
    assert sent == 1
    assert good.frames == [{"type": "chat_delta", "text": "好"}]

    # 坏连接已被摘除,再次广播只剩 good
    sent = await reg.broadcast("t2", {"type": "chat_done"})
    assert sent == 1


def test_stream_event_partial_delta_maps_to_chat_delta():
    """BUG-058:--include-partial-messages 的 stream_event/text_delta → chat_delta 增量"""
    evt = {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "1\n"},
        },
    }
    assert _stream_event_to_chat(evt) == {"type": "chat_delta", "text": "1\n"}


def test_stream_event_non_text_delta_ignored():
    """非文本 delta(input_json_delta 等)不产生对话增量"""
    evt = {
        "type": "stream_event",
        "event": {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{}"}},
    }
    assert _stream_event_to_chat(evt) is None


def test_assistant_whole_block_still_maps():
    """回归:assistant 整块路径保留(无 partial flag 的旧输出形态)"""
    evt = {"type": "assistant", "message": {"content": [{"type": "text", "text": "整块"}]}}
    assert _stream_event_to_chat(evt) == {"type": "chat_delta", "text": "整块"}


# ---------------------------------------------------------------------------
# BUG-059(R32.F7):chat_delta 打字机平滑——上游非流式时增量瞬达,视觉等同同步
# ---------------------------------------------------------------------------
class _RecordingRegistry:
    """记录广播帧与时刻的注册表替身"""

    def __init__(self):
        self.frames: list[tuple[float, dict]] = []

    async def broadcast(self, task_id, payload):
        import time as _t
        self.frames.append((_t.monotonic(), payload))
        return 1


@pytest.mark.asyncio
async def test_smooth_splits_and_preserves_order(monkeypatch):
    """大块增量拆为 ≤16 字符小帧,顺序与内容保持"""
    import asyncio
    from app.services import task_service as ts

    reg = _RecordingRegistry()
    monkeypatch.setattr(ts, "task_event_registry", reg)
    text = "字" * 50
    await ts._broadcast_delta_smooth("t", text, {})
    pieces = [f[1]["text"] for f in reg.frames]
    assert all(len(p) <= 16 for p in pieces)
    assert "".join(pieces) == text
    assert all(f[1]["type"] == "chat_delta" for f in reg.frames)
    asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_smooth_paces_burst(monkeypatch):
    """瞬达增量按节奏铺开:4 帧间隔 ≥ 3×30ms(容差 0.7)"""
    import asyncio
    import time as _t
    from app.services import task_service as ts

    reg = _RecordingRegistry()
    monkeypatch.setattr(ts, "task_event_registry", reg)
    t0 = _t.monotonic()
    for ch in ["1", "2", "3", "4", "5"]:
        await ts._broadcast_delta_smooth("t", ch, {})
    elapsed = _t.monotonic() - t0
    assert len(reg.frames) == 5
    assert elapsed >= ts.CHAT_DELTA_MIN_INTERVAL * 3 * 0.7


@pytest.mark.asyncio
async def test_smooth_passthrough_when_slow(monkeypatch):
    """真流式(到达间隔 > 节奏下限)零额外延迟直通"""
    import asyncio
    import time as _t
    from app.services import task_service as ts

    reg = _RecordingRegistry()
    monkeypatch.setattr(ts, "task_event_registry", reg)
    state: dict = {}  # 真实用法:同一轮对话共享节奏状态
    t0 = _t.monotonic()
    for _ in range(3):
        await ts._broadcast_delta_smooth("t", "x", state)
        await asyncio.sleep(0.06)  # > 30ms 下限
    elapsed = _t.monotonic() - t0
    # 3 次广播 + 2 次间隔(60ms)+ 首帧节奏 30ms;Windows sleep 过冲放宽
    # (若错误节流慢到达:每次调用额外 +30ms → elapsed ≥ 0.30)
    assert elapsed < 0.30
