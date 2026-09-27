"""
R5(probe_claude)— Runner 侧指令单测 — QA TDD Red phase
=========================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R5.md:
- Runner 新指令 probe_claude(照 claude_inject 先例 runner/main.py:429):
  container_manager 新方法在单次调用内完成
  start_container(repos=[], task_id 哨兵)→ exec_capture 探测 → stop_container(用后即毁)
  返回 {skills:[name...], mcps:[{name,transport...}]}
- main.handle_message 接线:单条指令 → 单条 result 回报(ok=True + data)

不依赖真实 Docker/平台:handle_message 用 FakeWS 直驱(test_runner_shutdown.py 先例),
container_manager 用 fake docker client(test_container_manager.py 先例)。
真机全链路(临时容器起→探→毁 + 镜像实际资产核对)依赖在线 Runner 与 devbox 镜像,
不在本轮(Runner 依赖,已注明)。

实现纬度说明(收口审查后已定口径):
- 单侧探测命令失败 = PRD R1「部分结果+警告」:该侧按空并在 failed_sides/warnings
  标记(平台侧据此不清该侧旧库),不上抛;exec 通道抛异常(硬失败)才向上传播
  且容器仍被销毁(销毁兜底)。命令不掩盖 exit code(无 `|| true`)。
"""
import asyncio
import json

import pytest

import main as runner_main
from container_manager import ContainerManager


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------
class FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class FakeProbeManager:
    """接线测试用:记录 probe_claude 调用,返回预置结果/异常"""

    def __init__(self, result=None, exc=None):
        self.calls = 0
        self.result = result or {
            "skills": ["skill-a"],
            "mcps": [{"name": "fetch", "transport": "stdio"}],
        }
        self.exc = exc

    def probe_claude(self, *args, **kwargs):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.result


class FakeExecResult:
    def __init__(self, code=0, output=b""):
        self.exit_code = code
        self.output = output

    def __iter__(self):
        # 兼容 docker SDK namedtuple 用法:exit_code, output = exec_run(...)
        return iter((self.exit_code, self.output))


class ProbeFakeContainer:
    """fake 容器:exec_run 按 cmd 子串路由预置输出;记录 stop/remove"""

    def __init__(self, routes=None, exec_exc=None):
        self.short_id = "probe123abc"
        self.exec_cmds: list[str] = []
        self.stopped = False
        self.removed = False
        self._routes = routes or []  # [(匹配子串列表, code, output_bytes)]
        self._exec_exc = exec_exc

    def exec_run(self, cmd_args):
        cmd = cmd_args[-1] if isinstance(cmd_args, (list, tuple)) else str(cmd_args)
        self.exec_cmds.append(cmd)
        if self._exec_exc is not None:
            raise self._exec_exc
        for subs, code, out in self._routes:
            if all(s in cmd for s in subs):
                return FakeExecResult(code, out)
        return FakeExecResult(0, b"")

    def stop(self, timeout=10):
        self.stopped = True

    def remove(self, force=False):
        self.removed = True


class ProbeFakeContainersAPI:
    def __init__(self, container: ProbeFakeContainer, run_exc=None):
        self.container = container
        self.run_kwargs = None
        self._run_exc = run_exc

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        if self._run_exc is not None:
            raise self._run_exc
        return self.container

    def get(self, container_id):
        return self.container


class ProbeFakeDockerClient:
    """标准形态 fake client:containers API 挂 .containers(与真实 docker SDK 同形)"""

    def __init__(self, api: ProbeFakeContainersAPI):
        self.containers = api


def _make_manager(container=None, run_exc=None) -> tuple[ContainerManager, ProbeFakeContainersAPI]:
    container = container or ProbeFakeContainer()
    api = ProbeFakeContainersAPI(container, run_exc=run_exc)
    client = ProbeFakeDockerClient(api)
    return ContainerManager(client_factory=lambda: client), api


def _call_probe(manager: ContainerManager):
    """probe_claude 调用(image 必填签名直调;方法缺失显式 fail,
    防 AttributeError 被 pytest.raises(Exception) 误吞成假通过)"""
    if not hasattr(manager, "probe_claude"):
        pytest.fail("container_manager.probe_claude 方法未创建(R5 契约)")
    return manager.probe_claude(image="platform/devbox:v1")


async def _dispatch_probe(ws: FakeWS, req_id: str):
    """下发 probe 指令(type 直发)"""
    await runner_main.handle_message(ws, {"type": "probe_claude", "req_id": req_id})


# ---------------------------------------------------------------------------
# 1. main.handle_message 接线:单条指令 → 单条 result(ok=True + data)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_message_probe_claude_single_result():
    """probe 指令 → manager.probe_claude 恰一次 → 回一条 result(ok=True, data 原样)"""
    ws = FakeWS()
    fake = FakeProbeManager()
    orig = runner_main.manager
    runner_main.manager = fake
    try:
        await _dispatch_probe(ws, "r-p1")
    finally:
        runner_main.manager = orig

    assert fake.calls == 1, f"probe_claude 应被调用一次,实际 {fake.calls}"
    results = [p for p in ws.sent if p.get("type") == "result" and p.get("req_id") == "r-p1"]
    assert len(results) == 1, f"应回一条 result,实际: {ws.sent}"
    assert results[0]["ok"] is True
    assert results[0]["data"] == {"skills": ["skill-a"], "mcps": [{"name": "fetch", "transport": "stdio"}]}


@pytest.mark.asyncio
async def test_handle_message_probe_failure_replies_ok_false():
    """probe 抛异常(容器启动失败等)→ 回一条 result(ok=False, error 非空);平台侧据此 502"""
    ws = FakeWS()
    fake = FakeProbeManager(exc=RuntimeError("container start failed"))
    orig = runner_main.manager
    runner_main.manager = fake
    try:
        await _dispatch_probe(ws, "r-p2")
    finally:
        runner_main.manager = orig

    assert fake.calls == 1
    results = [p for p in ws.sent if p.get("type") == "result" and p.get("req_id") == "r-p2"]
    assert len(results) == 1, f"应回一条 result,实际: {ws.sent}"
    assert results[0]["ok"] is False
    assert results[0]["error"]


# ---------------------------------------------------------------------------
# 2. container_manager.probe_claude:start(repos=[])→exec 探测→stop 单次调用内完成
# ---------------------------------------------------------------------------
def test_probe_happy_path_start_exec_stop():
    """时序:空仓库临时容器(repos=[],task_id 哨兵,无 qicheng.managed)→ 探测
    (skills 只取一级目录 + 读 /root/.claude.json)→ 容器销毁(用后即毁);
    返回 {skills:[name...], mcps:[{name,...}], failed_sides:[], warnings:[]}"""
    find_out = b"skill-a\nskill-b\n"
    claude_json = json.dumps({
        "mcpServers": {"fetch": {"type": "stdio", "command": "uvx mcp-server-fetch"}},
    }).encode()
    container = ProbeFakeContainer(routes=[
        (["find /root/.claude/skills"], 0, find_out),
        (["cat /root/.claude.json"], 0, claude_json),
    ])
    manager, api = _make_manager(container)

    result = _call_probe(manager)

    # start 契约:临时容器,不挂仓库,task_id 为哨兵值;一次性容器不打 qicheng.managed
    # (die 自动重启/对账清扫均按该标签过滤,探测容器不得参与)
    assert api.run_kwargs is not None, "未启动容器"
    labels = (api.run_kwargs.get("labels") or {})
    task_id = labels.get("qicheng.task_id", "")
    assert task_id, "task_id 哨兵缺失(labels)"
    assert labels.get("qicheng.managed") != "true", "一次性探测容器不得带 qicheng.managed 标签"
    # 探测命令:skills 只取一级目录(find -type d)+ 读 /root/.claude.json;
    # 命令不得掩盖 exit code(无 `|| true`——单侧失败须可检测,PRD R1 部分结果语义)
    skills_cmds = [c for c in container.exec_cmds if "/root/.claude/skills" in c]
    assert skills_cmds and all("-type d" in c for c in skills_cmds), container.exec_cmds
    assert all("|| true" not in c for c in container.exec_cmds), container.exec_cmds
    assert any("/root/.claude.json" in c for c in container.exec_cmds), container.exec_cmds
    # 空仓库:不做 git clone
    assert not any("git clone" in c for c in container.exec_cmds), container.exec_cmds
    # 用后即毁:容器已 stop + remove
    assert container.stopped and container.removed, "临时容器未销毁(用后即毁)"
    # 返回契约
    assert {"skills", "mcps", "failed_sides", "warnings"} <= set(result.keys()), result
    assert result["skills"] == ["skill-a", "skill-b"]
    assert result["failed_sides"] == [] and result["warnings"] == []
    assert len(result["mcps"]) == 1
    m = result["mcps"][0]
    assert m.get("name") == "fetch"
    # 传输字段:归一化 transport 或探测原文 type 均认(PRD:名称+传输类型)
    assert m.get("transport", m.get("type")) == "stdio"


def test_probe_side_failure_reported_not_masked():
    """单侧探测命令失败(skills find 非零)→ 不上抛,该侧按空并在
    failed_sides/warnings 标记(PRD R1 部分结果语义;平台侧据此不清该侧旧库);
    另一侧(mcps)正常探测;容器仍销毁"""
    claude_json = json.dumps({
        "mcpServers": {"fetch": {"type": "stdio", "command": "uvx mcp-server-fetch"}},
    }).encode()
    container = ProbeFakeContainer(routes=[
        (["find /root/.claude/skills"], 1, b""),  # skills 目录缺失/命令失败
        (["cat /root/.claude.json"], 0, claude_json),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == []
    assert result["failed_sides"] == ["skills"]
    assert result["warnings"] and "skills" in result["warnings"][0]
    assert [m["name"] for m in result["mcps"]] == ["fetch"]
    assert container.stopped and container.removed, "失败路径临时容器未销毁"


def test_probe_mcps_side_failure_reported():
    """claude.json 不可读(cat 非零)→ mcps 侧按空 + failed_sides 标记,不上抛"""
    container = ProbeFakeContainer(routes=[
        (["find /root/.claude/skills"], 0, b"skill-a\n"),
        (["cat /root/.claude.json"], 1, b""),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == ["skill-a"]
    assert result["mcps"] == []
    assert result["failed_sides"] == ["mcps"]
    assert result["warnings"]


def test_probe_mcp_servers_non_dict_treated_as_empty():
    """mcpServers 真值非 dict(list)→ 按空处理不炸(契约「非法按空」),不标记侧失败"""
    claude_json = json.dumps({"mcpServers": ["not-a-dict"]}).encode()
    container = ProbeFakeContainer(routes=[
        (["find /root/.claude/skills"], 0, b"skill-a\n"),
        (["cat /root/.claude.json"], 0, claude_json),
    ])
    manager, _ = _make_manager(container)

    result = _call_probe(manager)

    assert result["skills"] == ["skill-a"]
    assert result["mcps"] == []
    assert result["failed_sides"] == []


def test_probe_start_failure_propagates():
    """容器启动失败 → 异常向上传播(接线层转 ok=False → 平台 502 可重试)"""
    manager, api = _make_manager(run_exc=RuntimeError("docker run failed"))
    with pytest.raises(Exception):
        _call_probe(manager)


def test_probe_exec_exception_still_destroys_container():
    """exec 通道硬失败(异常)→ 异常向上传播,且容器仍被销毁(销毁兜底,不留临时容器)"""
    container = ProbeFakeContainer(exec_exc=RuntimeError("exec channel broken"))
    manager, api = _make_manager(container)

    with pytest.raises(Exception):
        _call_probe(manager)

    assert container.stopped and container.removed, "exec 失败后临时容器未销毁(销毁兜底)"
