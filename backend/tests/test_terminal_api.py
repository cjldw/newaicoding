"""
R9 终端平台侧测试
==========================
- 创建会话(成功/viewer 拒绝/无运行容器 9001/Runner 离线 9001)
- 关闭会话(创建者/非创建者)
- 输入转发到 Runner(含破坏性命令审计不拦截)
- 输出限流(>1000 块/秒丢弃)
- ai_output 通道([ai] 前缀)
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.services import terminal_service
from app.services.runner_service import runner_registry
from app.services.terminal_service import (
    TerminalConnection,
    check_rate_limit,
    terminal_registry,
)


class FakeFrontendWS:
    """前端 WebSocket 替身(记录 send_json)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


async def _setup_running_container(db_session, registered_user, runner_id="runner-t"):
    """项目 + 需求 + 任务 + running 容器(R9 会话前置)

    R9.F1:终端创建端点需按 task_id 查 Task 行(ensure_claude_session),夹具补建真实 Task。
    """
    runner_row = None
    from app.models.runner import Runner

    runner_row = Runner(
        name=f"rn-{uuid.uuid4().hex[:6]}", role="worker", token_hash="x",
        status="online", created_by="test",
    )
    db_session.add(runner_row)
    project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()

    from app.models.requirement import Requirement
    from app.models.task import Task

    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="terminal-req",
        description="d",
        status="approved",
        req_branch="main",
        created_by=registered_user["user_id"],
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()

    task_id = str(uuid.uuid4())
    task = Task(
        task_id=task_id,
        req_id=req.req_id,
        project_id=project.project_id,
        type="dev",
        title="terminal-task",
        description="d",
        base_branch="main",
        work_branch="main",
        status="running",
        conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id=task_id,
        runner_id=runner_row.runner_id,
        project_id=project.project_id,
        status="running",
        exposed_ports=[5173, 8000],
    )
    db_session.add(container)
    await db_session.flush()
    return project, container


@pytest.mark.asyncio
async def test_create_terminal_session_success(client, auth_headers, db_session, registered_user, monkeypatch):
    """创建终端会话成功:平台下发 exec 指令到 Runner"""
    project, container = await _setup_running_container(db_session, registered_user)
    conn = runner_registry.register(container.runner_id, "worker", None, "10.0.0.9")

    sent = []

    async def fake_send(c, message):
        sent.append(message)

    from app.services import runner_service

    monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

    resp = await client.post(
        f"/api/tasks/{container.task_id}/terminal-sessions",
        headers=auth_headers,
        json={"shell": "/bin/bash"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["session_id"]
    assert data["data"]["ws_url"].endswith(data["data"]["session_id"])

    assert len(sent) == 1
    msg = sent[0]
    assert msg["type"] == "exec"
    assert msg["pty"] is True
    # R9.F1:cmd 从裸 ["/bin/bash"] 改为 bash -lc 包装的自动进 claude 命令
    # (claude 守卫 + 首次 --session-id + 退出落回 bash)
    assert msg["cmd"][:2] == ["/bin/bash", "-lc"]
    wrapper = msg["cmd"][2]
    assert wrapper.startswith("command -v claude")
    assert "claude --session-id '" in wrapper  # 新任务首建会话
    assert "exec /bin/bash" in wrapper
    assert msg["container_id"] == container.container_id
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_create_terminal_viewer_denied(client, auth_headers, db_session, registered_user):
    """viewer 创建终端会话:403(权限矩阵)"""
    project, container = await _setup_running_container(db_session, registered_user)
    phone = f"133{str(uuid.uuid4().int)[:8]}"
    await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    await client.post(
        f"/api/projects/{project.project_id}/members",
        headers=auth_headers,
        json={"phone": phone, "role": "viewer"},
    )
    resp = await client.post(
        f"/api/tasks/{container.task_id}/terminal-sessions",
        headers=viewer_headers,
        json={"shell": "/bin/bash"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_terminal_no_container_9001(client, auth_headers, db_session, registered_user):
    """任务无运行容器:9001"""
    resp = await client.post(
        "/api/tasks/no-such-task/terminal-sessions",
        headers=auth_headers,
        json={"shell": "/bin/bash"},
    )
    assert resp.json()["code"] == 9001


@pytest.mark.asyncio
async def test_create_terminal_runner_offline_9001(client, auth_headers, db_session, registered_user):
    """Runner 离线(无连接):9001"""
    project, container = await _setup_running_container(db_session, registered_user)
    resp = await client.post(
        f"/api/tasks/{container.task_id}/terminal-sessions",
        headers=auth_headers,
        json={"shell": "/bin/bash"},
    )
    assert resp.json()["code"] == 9001


@pytest.mark.asyncio
async def test_close_terminal_session(client, auth_headers, db_session, registered_user):
    """关闭会话:创建者可关;非创建者 403"""
    from app.models.terminal import TerminalSession

    project, container = await _setup_running_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.9")
    session = TerminalSession(
        task_id=container.task_id, container_id=container.container_id,
        runner_id=container.runner_id, shell="/bin/bash",
        created_by=registered_user["user_id"],
    )
    db_session.add(session)
    await db_session.flush()

    # 非创建者(新用户,超管 bootstrap 之外的普通用户)
    from tests.test_projects_api import _register_and_login
    other_headers, _uid = await _register_and_login(client)
    resp = await client.delete(f"/api/terminal-sessions/{session.session_id}", headers=other_headers)
    assert resp.status_code == 403

    resp = await client.delete(f"/api/terminal-sessions/{session.session_id}", headers=auth_headers)
    assert resp.json()["code"] == 0
    await db_session.refresh(session)
    assert session.closed_at is not None
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_terminal_input_forward_and_audit(client, auth_headers, db_session, registered_user, caplog):
    """输入转发到 Runner;破坏性命令不拦截但写审计日志"""
    sent = []

    class FakeRunnerWS:
        async def send_json(self, payload):
            sent.append(payload)

    conn = runner_registry.register("runner-fwd", "worker", FakeRunnerWS(), "")
    conn.websocket = FakeRunnerWS()
    ws = FakeFrontendWS()
    tconn = TerminalConnection(session_id="s-1", task_id="t-1", runner_id="runner-fwd",
                               user_id="u-1", websocket=ws)
    terminal_registry.put(tconn)

    # 正常命令
    ok = await terminal_service.forward_input_to_runner("s-1", "ls -la\n")
    assert ok is True
    assert sent[-1]["type"] == "terminal_input"
    assert sent[-1]["data"] == "ls -la\n"

    # 破坏性命令:转发(不拦截)+ 审计日志
    import logging

    with caplog.at_level(logging.WARNING):
        ok = await terminal_service.forward_input_to_runner("s-1", "git reset --hard HEAD~1\n")
    assert ok is True
    assert any("破坏性命令" in r.message for r in caplog.records)

    terminal_registry.pop("s-1")
    runner_registry.unregister("runner-fwd")


@pytest.mark.asyncio
async def test_terminal_output_rate_limit():
    """>1000 块/秒丢弃中间块"""
    ws = FakeFrontendWS()
    conn = TerminalConnection(session_id="s-2", task_id="t", runner_id="r", user_id="u", websocket=ws)
    terminal_registry.put(conn)

    allowed = 0
    for i in range(1200):
        if await terminal_service.forward_output_to_frontend("s-2", f"line {i}\n"):
            allowed += 1
    assert allowed <= terminal_service.MAX_OUTPUT_CHUNKS_PER_SECOND
    assert len(ws.sent) == allowed
    terminal_registry.pop("s-2")


@pytest.mark.asyncio
async def test_ai_output_channel():
    """SDK 事件 → ai_output([ai] 前缀)推送到该任务的终端"""
    ws = FakeFrontendWS()
    conn = TerminalConnection(session_id="s-3", task_id="task-ai", runner_id="r", user_id="u", websocket=ws)
    terminal_registry.put(conn)

    await terminal_service.push_ai_output("task-ai", 'git commit -m "x"')
    assert ws.sent[0]["type"] == "ai_output"
    assert ws.sent[0]["data"].startswith("[ai] ")
    terminal_registry.pop("s-3")
