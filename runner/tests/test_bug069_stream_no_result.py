"""BUG-069(R5.F2) runner 侧:流式输出无 result 事件时,应返回累积文本而非 lines[-1] 解析垃圾

根因:长消息/中途出错场景 CLI 不发 result 事件,原实现兜底取 lines[-1] 拿到
最后一个 content_block_delta(解析出空/残缺),上泵后 task_service 落库空 content。

修复 F1:读循环累积 textDelta,finalize 优先级:
  显式 result 事件 > 累积文本 > lines[-1] 兜底(零行降级保持不动)

用例:
- ① N 行 content_block_delta + 无 result → result=累积文本(修复前:Red,返 lines[-1] 解析垃圾)
- ② 显式 result 事件 → 行为不变(回归)
- ③ 零行 → 仍走 R32.F8 零行降级(回归)
- ④ stderr 捕获(F4):stderr 帧内容进返回体 stderr_tail
"""
import json

import pytest

from container_manager import ContainerManager


class FakeSocket:
    def __init__(self, payload: bytes, chunk: int = 64):
        self._payload = payload
        self._chunk = chunk
        self._pos = 0
        self.closed = False

    def read(self, n: int) -> bytes:
        if self._pos >= len(self._payload):
            return b""
        out = self._payload[self._pos:self._pos + self._chunk]
        self._pos += self._chunk
        return out

    def close(self):
        self.closed = True


class FakeApi:
    def __init__(self, stdout: bytes = b""):
        self._stdout = stdout

    def exec_create(self, container_id, cmd, **kw):
        self.last_cmd = cmd
        return "exec-1"

    def exec_start(self, exec_id, **kw):
        return FakeSocket(self._stdout)


class FakeContainer:
    def __init__(self, api):
        self._api = api

    def exec_run(self, cmd_args):
        return 0, b""


class FakeContainers:
    def __init__(self, api):
        self._api = api

    def get(self, container_id):
        return FakeContainer(self._api)


class FakeDockerClient:
    def __init__(self, stdout: bytes = b""):
        self.api = FakeApi(stdout)
        self.containers = FakeContainers(self.api)


def _manager(client):
    return ContainerManager(client_factory=lambda: client)


def _docker_frame(payload: bytes, stream: int = 1) -> bytes:
    return bytes([stream]) + b"\x00\x00\x00" + len(payload).to_bytes(4, "big") + payload


def _delta_lines(text_fragments: list[str]) -> bytes:
    """构造 N 行 content_block_delta/text_delta 事件(无 result 事件)"""
    lines = []
    for frag in text_fragments:
        lines.append(json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": frag},
            },
        }))
    return ("\n".join(lines) + "\n").encode()


# ---------------------------------------------------------------------------
# ① 核心 Red:流式 N 行 delta + 无 result → 应返回累积文本
# ---------------------------------------------------------------------------
def test_stream_no_result_returns_accumulated_text():
    """修复前:返回 lines[-1] 解析出的残缺 JSON(空字符串);修复后:返回累积文本"""
    fragments = ["项目", "需要", "登录", "加上", "图形验证码"]
    client = FakeDockerClient(stdout=_delta_lines(fragments))
    mgr = _manager(client)

    out = mgr.claude_prompt_stream("c1", "项目需要登录加上图形验证码")

    assert out["result"] == "项目需要登录加上图形验证码"
    assert out["lines"] == len(fragments)
    # 累积文本字段(F1 新增)
    assert out.get("accumulated_text") == "项目需要登录加上图形验证码"


def test_stream_no_result_with_docker_frames_returns_accumulated():
    """帧协议下同样能累积(F4 剥帧语义不变)"""
    fragments = ["长", "消", "息", "测", "试"]
    inner = _delta_lines(fragments)
    framed = b"".join(_docker_frame(inner[i:i + 11]) for i in range(0, len(inner), 11))
    client = FakeDockerClient(stdout=framed)
    mgr = _manager(client)

    out = mgr.claude_prompt_stream("c1", "长消息测试")

    assert out["result"] == "长消息测试"
    assert out.get("accumulated_text") == "长消息测试"


# ---------------------------------------------------------------------------
# ② 回归:显式 result 事件 → 行为不变(优先于累积文本)
# ---------------------------------------------------------------------------
def test_stream_with_result_event_unchanged():
    """有 result 事件时,返回 result 事件文本(不返回累积文本)"""
    lines = [
        json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "部分"},
        }}),
        json.dumps({"type": "result", "result": "完整结果",
                    "usage": {"input_tokens": 10, "output_tokens": 5}}),
    ]
    payload = ("\n".join(lines) + "\n").encode()
    client = FakeDockerClient(stdout=payload)
    mgr = _manager(client)

    out = mgr.claude_prompt_stream("c1", "hi")

    assert out["result"] == "完整结果"
    assert out["tokens_in"] == 10
    assert out["tokens_out"] == 5


# ---------------------------------------------------------------------------
# ③ 回归:零行 → R32.F8 零行降级(lines=0,result 空)
# ---------------------------------------------------------------------------
def test_stream_zero_lines_unchanged():
    """BUG-060(R32.F8):零行降级路径不被 F1 破坏"""
    client = FakeDockerClient(stdout=b"")
    mgr = _manager(client)

    out = mgr.claude_prompt_stream("c1", "hi", session_id="s-gone", resume=True)

    assert out["result"] == ""
    assert out["lines"] == 0
    assert out.get("accumulated_text", "") == ""


# ---------------------------------------------------------------------------
# ④ F4 stderr 捕获:去 2>/dev/null,stderr 进返回体
# ---------------------------------------------------------------------------
def test_stderr_captured_in_result():
    """F4:stderr 帧内容进 stderr_tail(截断 ≤2000 字符)"""
    # 构造:stderr 帧 + 正常 stdout 行
    stdout_lines = [json.dumps({"type": "result", "result": "ok"})]
    stdout_payload = ("\n".join(stdout_lines) + "\n").encode()
    stderr_msg = b"Error: API rate limit exceeded\n"
    payload = _docker_frame(stderr_msg, stream=2) + _docker_frame(stdout_payload, stream=1)
    client = FakeDockerClient(stdout=payload)
    mgr = _manager(client)

    out = mgr.claude_prompt_stream("c1", "hi")

    # F4 新增字段:stderr_tail
    assert "stderr_tail" in out
    assert "rate limit" in out["stderr_tail"]


def test_cmd_no_longer_redirects_stderr_to_devnull():
    """F4:命令不再含 2>/dev/null(stderr 走 docker demux 分离)"""
    client = FakeDockerClient(stdout=b"")
    mgr = _manager(client)

    mgr.claude_prompt_stream("c1", "hi")

    # 命令不应再含 2>/dev/null(末尾的 stderr 重定向)
    # 注意:cd 的 2>/dev/null 允许保留(目录切换失败静默是合理的)
    cmd = " ".join(client.api.last_cmd)
    # 关键:claude 命令后不应再跟 2>/dev/null
    assert not cmd.rstrip().endswith("2>/dev/null")
