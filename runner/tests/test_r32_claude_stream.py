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

    assert out == {"result": "你好", "tokens_in": 11, "tokens_out": 7}
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
