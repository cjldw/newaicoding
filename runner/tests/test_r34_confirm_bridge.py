"""R34 runner 侧:权限确认桥接(--permission-prompt-tool MCP stdio 桥)协议用例

不依赖真实连接/docker:manager 替身(fake 容器内存文件系统)+ handle_message 直驱。
- setup_permission_bridge:bridge.py + mcp.json 注入;失败返回 False(调用方降级)
- claude_prompt_stream:permission_bridge=True 拼 --permission-prompt-tool / --mcp-config;
  False 维持原命令(无确认通道,静默拒绝)
- read_new_confirm_requests:cursor 增量读取 req.log;无日志(读失败)不推进
- write_confirm_answer:decision 写 ans-{seq}.json
- _confirm_poller:请求行 → 上行 claude_confirm_request + 登记挂起表
- exec_tool_confirm:allow 回传 updatedInput=原 input;deny 带 message;未知 confirm 幂等
"""
import asyncio
import base64
import json
import re

import pytest

import main as runner_main
from container_manager import ContainerManager, PERMGATE_DIR, PERMGATE_TOOL_REF, CLAUDE_JSON_PATH


# ---------------------------------------------------------------------------
# fake docker(容器内内存文件系统;与 test_r32_claude_stream 同思路)
# ---------------------------------------------------------------------------
class FakeExecApi:
    """low-level api 替身:exec_create/exec_start 捕获命令,socket 吐预设 stdout"""

    def __init__(self, stdout: bytes = b""):
        self._stdout = stdout
        self.created: list[str] = []

    def exec_create(self, container_id, cmd, **kw):
        self.created.append(" ".join(cmd))
        return "exec-1"

    def exec_start(self, exec_id, **kw):
        class _Sock:
            def __init__(self, payload):
                self._p = payload

            def read(self, n):
                out, self._p = self._p[:n], self._p[n:]
                return out

            def close(self):
                pass

        return _Sock(self._stdout)


class FakeContainer:
    """exec_run 语义的容器内内存 fs(写文件/cat/rm;与 exec_capture 对接)"""

    def __init__(self, api: FakeExecApi):
        self.api = api
        self.files: dict[str, str] = {}

    def exec_run(self, cmd_args):
        joined = " ".join(cmd_args) if isinstance(cmd_args, list) else str(cmd_args)
        m = re.search(r"echo (\S+) \| base64 -d > (\S+)", joined)
        if m:  # write_file / write_confirm_answer
            self.files[m.group(2)] = base64.b64decode(m.group(1)).decode("utf-8")
            return 0, b""
        # R5.F3:setup_permission_bridge 读 ~/.claude.json 做幂等合并
        if f"cat {CLAUDE_JSON_PATH}" in joined:
            content = self.files.get(CLAUDE_JSON_PATH)
            if content is None:
                return 1, b""  # 文件不存在
            return 0, content.encode()
        if f"cat {PERMGATE_DIR}/req.log" in joined:
            content = self.files.get(f"{PERMGATE_DIR}/req.log", "")
            if not content:
                return 2, b""  # cat:文件不存在
            return 0, content.encode()
        if "rm -f " in joined or "rm -rf " in joined:
            # 内存 fs 的 rm:删匹配字面量/前缀通配(桥接注入前的残留清理与收尾清理)
            body = joined.split("rm -f ", 1)[-1].split("rm -rf ", 1)[-1]
            body = body.replace("2>/dev/null", "").strip()
            for pattern in body.split():
                prefix = pattern.replace("*", "")
                for key in [k for k in list(self.files) if k.startswith(prefix)]:
                    self.files.pop(key, None)
            return 0, b""
        return 0, b""


class FakeContainers:
    def __init__(self, container: FakeContainer):
        self._c = container

    def get(self, container_id):
        return self._c


class FakeClient:
    def __init__(self, container: FakeContainer):
        self.api = container.api
        self.containers = FakeContainers(container)


def _manager(container: FakeContainer) -> ContainerManager:
    return ContainerManager(client_factory=lambda: FakeClient(container))


# ---------------------------------------------------------------------------
# 桥接注入 / 命令参数
# ---------------------------------------------------------------------------
def test_setup_permission_bridge_injects_files_and_cleans():
    container = FakeContainer(FakeExecApi())
    container.files[f"{PERMGATE_DIR}/req.log"] = "stale\n"
    # 预置既有 claude.json,验证合并而非覆盖
    container.files[CLAUDE_JSON_PATH] = json.dumps({
        "theme": "dark",
        "mcpServers": {"existing_server": {"url": "http://existing"}},
    })
    mgr = _manager(container)

    assert mgr.setup_permission_bridge("c1") is True
    bridge = container.files[f"{PERMGATE_DIR}/bridge.py"]
    assert "tools/call" in bridge and "req.log" in bridge  # 桥接协议面
    # R5.F3:不再写独立 mcp.json,改为合并进 ~/.claude.json
    assert f"{PERMGATE_DIR}/mcp.json" not in container.files
    merged = json.loads(container.files[CLAUDE_JSON_PATH])
    assert merged["theme"] == "dark"  # 既有顶层键保留
    assert "existing_server" in merged["mcpServers"]  # 既有 MCP server 不覆盖
    assert merged["mcpServers"]["permgate"]["args"] == [f"{PERMGATE_DIR}/bridge.py"]
    assert f"{PERMGATE_DIR}/req.log" not in container.files  # 残留已清


def test_setup_permission_bridge_failure_returns_false():
    """容器不可用(write_file 抛)→ 降级 False,调用方不加权限参数(维持静默拒绝)"""
    class _Client:
        containers = None  # containers.get 访问即 AttributeError

    mgr = ContainerManager(client_factory=lambda: _Client())
    assert mgr.setup_permission_bridge("c1") is False


def test_claude_prompt_stream_permission_flags():
    stdout = (json.dumps({"type": "result", "result": "ok"}) + "\n").encode()
    api = FakeExecApi(stdout)
    container = FakeContainer(api)
    mgr = _manager(container)

    mgr.claude_prompt_stream("c1", "hi", permission_bridge=True)
    # R5.F3 二修(BUG-072 第 41 轮):CLI 2.1.280 下 permgate 桥(--permission-prompt-tool)
    # 实测整体失效(容器内两种注入形态均复现 "MCP tool mcp__permgate__approval not found"),
    # 坏 flag 使每个 MCP 调用 tool_use_error → 秒级空结算。stream cmd 恒不输出权限 flag,
    # MCP 走 --allowedTools 放行;permission_bridge 形参保留但仅作兼容
    assert f"--permission-prompt-tool" not in api.created[0]
    assert f"--mcp-config {PERMGATE_DIR}/mcp.json" not in api.created[0]
    # R5.F3(BUG-072 路径①):新增 --allowedTools 放行 MCP 工具面
    assert "--allowedTools" in api.created[0]
    assert "mcp__mysql_dev__*" in api.created[0]
    assert "mcp__mysql_beta__*" in api.created[0]
    assert "mcp__filesystem__*" in api.created[0]
    assert "ListMcpResourcesTool" in api.created[0]
    assert "--strict-mcp-config" not in api.created[0]  # 保留项目级 MCP 配置

    api.created.clear()
    mgr.claude_prompt_stream("c1", "hi", permission_bridge=False)
    # 降级路径:无桥接时 --permission-prompt-tool 不出现,但 --allowedTools 仍出现(R5.F3 独立于桥接)
    assert "permission-prompt-tool" not in api.created[0]
    assert "--allowedTools" in api.created[0]  # MCP 工具放行是独立的,不依赖桥接


# ---------------------------------------------------------------------------
# 请求读取 / 应答写入
# ---------------------------------------------------------------------------
def test_read_new_confirm_requests_cursor_incremental():
    container = FakeContainer(FakeExecApi())
    mgr = _manager(container)
    line1 = json.dumps({"n": 1, "tool_name": "Bash", "input": {"command": "git push"}, "tool_use_id": "t1"})
    line2 = json.dumps({"n": 2, "tool_name": "Write", "input": {"file_path": "/a.py"}, "tool_use_id": "t2"})
    container.files[f"{PERMGATE_DIR}/req.log"] = line1 + "\n"

    cursor, reqs = mgr.read_new_confirm_requests("c1", 0)
    assert (cursor, len(reqs)) == (1, 1) and reqs[0]["tool_name"] == "Bash"

    container.files[f"{PERMGATE_DIR}/req.log"] = line1 + "\n" + line2 + "\n"
    cursor, reqs = mgr.read_new_confirm_requests("c1", cursor)
    assert (cursor, len(reqs)) == (2, 1) and reqs[0]["n"] == 2

    assert mgr.read_new_confirm_requests("c1", cursor) == (2, [])  # 无新行


def test_read_new_confirm_requests_missing_log_is_noop():
    container = FakeContainer(FakeExecApi())
    assert _manager(container).read_new_confirm_requests("c1", 0) == (0, [])


def test_write_confirm_answer_writes_ans_file():
    container = FakeContainer(FakeExecApi())
    mgr = _manager(container)
    decision = {"behavior": "allow", "updatedInput": {"command": "git push"}}
    mgr.write_confirm_answer("c1", 3, decision)
    assert json.loads(container.files[f"{PERMGATE_DIR}/ans-3.json"]) == decision


# ---------------------------------------------------------------------------
# main 协议面:轮询上行 / 应答下行
# ---------------------------------------------------------------------------
class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class _PollerManager:
    """read_new_confirm_requests 替身:首轮返回 1 条请求"""

    def __init__(self):
        self.calls = 0

    def read_new_confirm_requests(self, container_id, cursor):
        self.calls += 1
        if self.calls == 1:
            return 1, [{"n": 1, "tool_name": "Bash",
                        "input": {"command": "git push origin main"}, "tool_use_id": "t1"}]
        return 1, []


@pytest.mark.asyncio
async def test_confirm_poller_upstreams_request(monkeypatch):
    monkeypatch.setattr(runner_main, "manager", _PollerManager())
    runner_main._pending_confirms.clear()
    ws = FakeWS()

    task = asyncio.create_task(runner_main._confirm_poller(ws, "r1", "t1", "c1"))
    try:
        for _ in range(200):
            if ws.sent:
                break
            await asyncio.sleep(0.01)
        assert len(ws.sent) == 1, ws.sent
        frame = ws.sent[0]
        assert frame["type"] == "claude_confirm_request"
        assert frame["req_id"] == "r1" and frame["task_id"] == "t1"
        assert frame["tool_name"] == "Bash"
        assert frame["input"] == {"command": "git push origin main"}
        assert frame["confirm_id"] in runner_main._pending_confirms
        assert runner_main._pending_confirms[frame["confirm_id"]]["seq"] == 1
        await asyncio.sleep(0.6)  # 第二轮无新行:不重复上行
        assert len(ws.sent) == 1
    finally:
        task.cancel()
        runner_main._pending_confirms.clear()


class _AnswerManager:
    def __init__(self):
        self.answers = []

    def write_confirm_answer(self, container_id, seq, decision):
        self.answers.append((container_id, seq, decision))


@pytest.mark.asyncio
async def test_exec_tool_confirm_allow_and_deny(monkeypatch):
    fake = _AnswerManager()
    monkeypatch.setattr(runner_main, "manager", fake)
    runner_main._pending_confirms.clear()
    runner_main._pending_confirms["cf-allow"] = {
        "req_id": "r1", "container_id": "c1", "seq": 3, "input": {"command": "git push"}}
    ws = FakeWS()

    await runner_main.handle_message(ws, {
        "type": "exec_tool_confirm", "confirm_id": "cf-allow", "choice": "allow"})
    assert fake.answers == [("c1", 3, {"behavior": "allow",
                                       "updatedInput": {"command": "git push"}})]
    assert "cf-allow" not in runner_main._pending_confirms  # 应答即注销

    runner_main._pending_confirms["cf-deny"] = {
        "req_id": "r1", "container_id": "c1", "seq": 4, "input": {"command": "x"}}
    await runner_main.handle_message(ws, {
        "type": "exec_tool_confirm", "confirm_id": "cf-deny", "choice": "deny"})
    assert fake.answers[-1][2]["behavior"] == "deny"
    assert fake.answers[-1][2]["message"]  # 拒绝文案回给模型


@pytest.mark.asyncio
async def test_exec_tool_confirm_unknown_id_is_noop(monkeypatch):
    fake = _AnswerManager()
    monkeypatch.setattr(runner_main, "manager", fake)
    runner_main._pending_confirms.clear()
    ws = FakeWS()
    await runner_main.handle_message(ws, {
        "type": "exec_tool_confirm", "confirm_id": "ghost", "choice": "allow"})
    assert fake.answers == []  # 未知 confirm(桥接超时自拒/重启丢表)幂等


# ---------------------------------------------------------------------------
# R5.F3:_merge_permgate_into_config 纯函数单测
# ---------------------------------------------------------------------------
from container_manager import _merge_permgate_into_config


def test_merge_permgate_empty_config():
    """空配置/None → 返回只含 permgate 的 mcpServers"""
    result = _merge_permgate_into_config(None)
    assert result == {"mcpServers": {"permgate": {
        "command": "python3", "args": [f"{PERMGATE_DIR}/bridge.py"]}}}


def test_merge_permgate_existing_other_servers_preserved():
    """已有其他 MCP server → 保留不覆盖,permgate 新增"""
    cfg = {"mcpServers": {"mysql_dev": {"url": "x"}, "gitlab": {"url": "y"}}}
    result = _merge_permgate_into_config(cfg)
    assert result["mcpServers"]["mysql_dev"] == {"url": "x"}
    assert result["mcpServers"]["gitlab"] == {"url": "y"}
    assert "permgate" in result["mcpServers"]
    # 入参不被修改(纯函数)
    assert "permgate" not in cfg["mcpServers"]


def test_merge_permgate_idempotent():
    """已有 permgate → 幂等更新,不重复"""
    cfg = {"mcpServers": {"permgate": {"command": "old", "args": ["old"]}}}
    result = _merge_permgate_into_config(cfg)
    assert result["mcpServers"]["permgate"]["command"] == "python3"
    assert result["mcpServers"]["permgate"]["args"] == [f"{PERMGATE_DIR}/bridge.py"]


def test_merge_permgate_top_level_keys_preserved():
    """顶层其他键(如 theme)保留"""
    cfg = {"theme": "dark", "mcpServers": {"old": {"url": "x"}}}
    result = _merge_permgate_into_config(cfg)
    assert result["theme"] == "dark"
    assert "permgate" in result["mcpServers"]
    assert "old" in result["mcpServers"]


def test_merge_permgate_invalid_mcpServers_field():
    """mcpServers 非 dict(如字符串) → 按缺失处理,新建 dict"""
    cfg = {"mcpServers": "invalid"}
    result = _merge_permgate_into_config(cfg)
    assert isinstance(result["mcpServers"], dict)
    assert "permgate" in result["mcpServers"]
