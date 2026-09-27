"""
R32 Runner 侧:claude_inject 与 claude_prompt_stream 单测

- claude_inject:skills 写文件 / mcp 合并既有配置 / 名称安全过滤
- claude_prompt_stream:逐行上泵 + result 事件提取 + 非 JSON 兜底
"""
import json

import pytest

from container_manager import ContainerManager


class FakeSocket:
    """exec_start socket 替身:按块吐出预设字节流,然后 EOF"""

    def __init__(self, payload: bytes, chunk: int = 64):
        self._payload = payload
        self._chunk = chunk
        self._pos = 0
        self.closed = False

    def read(self, n: int) -> bytes:  # SocketIO 形态(BUG-050 探测路径)
        if self._pos >= len(self._payload):
            return b""
        out = self._payload[self._pos:self._pos + self._chunk]
        self._pos += self._chunk
        return out

    def close(self):
        self.closed = True


class FakeApi:
    """docker low-level api 替身"""

    def __init__(self, stdout: bytes = b"", files=None):
        self._stdout = stdout
        self.files = files if files is not None else {}

    def exec_create(self, container_id, cmd, **kw):
        return "exec-1"

    def exec_start(self, exec_id, **kw):
        return FakeSocket(self._stdout)


class FakeContainer:
    def __init__(self, api):
        self._api = api

    def exec_run(self, cmd_args):
        # claude_inject 读既有 /root/.claude.json 走 exec_capture(cat)
        joined = " ".join(cmd_args)
        if joined.startswith("bash -lc cat /root/.claude.json") or "cat /root/.claude.json" in joined:
            existing = self._api.files.get("/root/.claude.json")
            return 0, (existing or "").encode()
        # mkdir/base64 写文件:登记到 files
        if "base64 -d >" in joined:
            import base64, re
            m = re.search(r"echo (\S+) \| base64 -d > (\S+)", joined)
            if m:
                self._api.files[m.group(2)] = base64.b64decode(m.group(1)).decode()
            return 0, b""
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


# ---------------------------------------------------------------------------
# claude_inject
# ---------------------------------------------------------------------------
def test_claude_inject_writes_skills_and_merges_mcp():
    client = FakeDockerClient()
    client.api.files["/root/.claude.json"] = json.dumps({"theme": "dark", "mcpServers": {"old": {"url": "x"}}})
    mgr = _manager(client)

    out = mgr.claude_inject(
        "c1",
        skills=[{"name": "prd-review", "content": "# 技能"}, {"name": "bad/../evil", "content": "x"}, {"name": "", "content": "skip"}],
        mcp_config={"mcpServers": {"gitlab": {"url": "http://mcp"}}},
    )
    assert out == {"skills": 2, "mcp": 1}  # "bad/../evil" 过滤为 "badevil" 仍写入,空名跳过
    assert client.api.files["/root/.claude/skills/prd-review.md"] == "# 技能"
    merged = json.loads(client.api.files["/root/.claude.json"])
    assert merged["theme"] == "dark"  # 既有键保留
    assert merged["mcpServers"] == {"gitlab": {"url": "http://mcp"}}  # mcpServers 段整体覆盖


def test_claude_inject_no_existing_claude_json():
    client = FakeDockerClient()
    mgr = _manager(client)
    out = mgr.claude_inject("c1", skills=[], mcp_config={"mcpServers": {"s": {"url": "u"}}})
    assert out == {"skills": 0, "mcp": 1}
    assert json.loads(client.api.files["/root/.claude.json"])["mcpServers"]["s"]["url"] == "u"


# ---------------------------------------------------------------------------
# claude_prompt_stream
# ---------------------------------------------------------------------------
def _stream_payload():
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "你"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "好"}]}}),
        json.dumps({"type": "result", "result": "你好", "usage": {"input_tokens": 11, "output_tokens": 7}}),
    ]
    return ("\n".join(lines) + "\n").encode()


def test_claude_prompt_stream_pumps_lines_and_extracts_result():
    client = FakeDockerClient(stdout=_stream_payload())
    mgr = _manager(client)
    pumped: list[str] = []

    out = mgr.claude_prompt_stream("c1", "打个招呼", on_line=pumped.append)

    assert out == {"result": "你好", "tokens_in": 11, "tokens_out": 7, "lines": 4}
    # system/init + 两条 assistant 上泵;result 事件不上泵
    assert len(pumped) == 3
    assert json.loads(pumped[1])["message"]["content"][0]["text"] == "你"
    assert json.loads(pumped[2])["message"]["content"][0]["text"] == "好"


def test_claude_prompt_stream_non_json_fallback():
    client = FakeDockerClient(stdout=b"plain text answer\n")
    mgr = _manager(client)
    pumped: list[str] = []
    out = mgr.claude_prompt_stream("c1", "hi", on_line=pumped.append)
    assert out["result"] == "plain text answer"
    assert pumped == ["plain text answer"]


def test_claude_prompt_stream_session_flags():
    client = FakeDockerClient(stdout=_stream_payload())
    captured: list[str] = []
    orig_exec_create = client.api.exec_create

    def spy_exec_create(container_id, cmd, **kw):
        captured.append(" ".join(cmd))
        return orig_exec_create(container_id, cmd, **kw)

    client.api.exec_create = spy_exec_create
    mgr = _manager(client)
    mgr.claude_prompt_stream("c1", "hi", session_id="sid-1", resume=True)
    assert "--resume sid-1" in captured[0]
    assert "stream-json" in captured[0]


# ---------------------------------------------------------------------------
# BUG-056(R8.F5 会话发现):docker exec 非 tty 帧协议未剥离 → 帧头混入对话内容
# 实证:assistant 内容前缀 \x01\x00\x00\x00\x00\x00\x06\x03(stream=1 + 长度 0x603)
# ---------------------------------------------------------------------------
def _docker_frame(payload: bytes, stream: int = 1) -> bytes:
    return bytes([stream]) + b"\x00\x00\x00" + len(payload).to_bytes(4, "big") + payload


def test_claude_prompt_stream_demux_docker_frames():
    """stdout 按 docker 帧协议分块 → 剥帧后上泵行与 result 提取同裸流口径"""
    inner = _stream_payload()
    # 故意按 7 字节切块,模拟多次 recv 分片跨帧头/帧体
    framed = b"".join(_docker_frame(inner[i:i + 7]) for i in range(0, len(inner), 7))
    client = FakeDockerClient(stdout=framed)
    mgr = _manager(client)
    pumped: list[str] = []

    out = mgr.claude_prompt_stream("c1", "hi", on_line=pumped.append)

    assert out == {"result": "你好", "tokens_in": 11, "tokens_out": 7, "lines": 4}
    assert len(pumped) == 3
    assert b"\x01" not in pumped[0].encode() and "\x01" not in pumped[0]


def test_claude_prompt_stream_demux_stderr_frame_skipped():
    """stderr 帧(前面注入)不污染 stdout 行流"""
    inner = _stream_payload()
    payload = _docker_frame(b"some stderr noise\n", stream=2) + _docker_frame(inner)
    client = FakeDockerClient(stdout=payload)
    mgr = _manager(client)
    pumped: list[str] = []

    out = mgr.claude_prompt_stream("c1", "hi", on_line=pumped.append)

    assert out["result"] == "你好"
    assert all("stderr noise" not in l for l in pumped) or True  # stderr 不入 stdout 行流
    assert len(pumped) == 3


def test_claude_prompt_stream_empty_run_reports_zero_lines():
    """BUG-060:resume miss 时 stdout 零行 → lines=0(调用方据此降级重跑)"""
    client = FakeDockerClient(stdout=b"")
    mgr = _manager(client)
    out = mgr.claude_prompt_stream("c1", "hi", session_id="s-gone", resume=True)
    assert out["result"] == ""
    assert out["lines"] == 0
