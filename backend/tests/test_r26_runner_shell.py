"""
R26 Runner 管理终端 — 后端批次
================================
覆盖 R26.md 完成判据:
2. shell-sessions 端点四段校验(404/6001/6002/6003 + 成功返回 session_id+ws_url)
3. task_id 解耦(TerminalConnection.task_id 可空;registry put/pop 正常)
5(API 部分). 非 online 直接调 API → 6001
6. 非超管 POST shell-sessions → 403
10. 打开会话 → runner.terminal_open 审计行(operator=超管)

Runner 连接(内存)与 exec 下发均 monkeypatch/直构,不依赖真实 Runner 进程。
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.models.audit_log import AuditLog
from app.models.runner import Runner
from app.models.terminal import TerminalSession
from app.core.security import hash_password
from app.services import runner_service
from app.services.terminal_service import TerminalConnection, terminal_registry

from tests.test_projects_api import _register_and_login

PLACEHOLDER_UID = "00000000-0000-0000-0000-000000000000"


def _phone() -> str:
    return f"135{str(uuid.uuid4().int)[:8]}"[:11]


async def _spawn_rows(action_type: str, timeout: float = 2.0) -> list:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(AuditLog).where(AuditLog.action_type == action_type)
            )).scalars().all()
        if rows:
            return list(rows)
        await asyncio.sleep(0.05)
    return []


async def _make_runner(db_session, status="online", machine_info=None) -> Runner:
    runner = Runner(
        name=f"r-{uuid.uuid4().hex[:6]}",
        role="worker",
        token_hash=hash_password("tok"),
        status=status,
        machine_info=machine_info,
        created_by="test",
    )
    db_session.add(runner)
    await db_session.flush()
    return runner


def _install_fake_conn(runner_id: str, sent: list):
    """注册假 Runner 连接并捕获 send_to_runner 的消息"""
    conn = runner_service.RunnerConnection(
        runner_id=runner_id, role="worker", websocket=SimpleNamespace(), host="test",
    )
    runner_service.runner_registry.register(runner_id, "worker", SimpleNamespace(), "test")

    async def _fake_send(c, message):
        sent.append(message)

    return conn, _fake_send


# ---------------------------------------------------------------------------
# 判据 2:四段校验
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shell_session_404(client, superadmin_headers):
    resp = await client.post(
        f"/api/admin/runners/{uuid.uuid4()}/shell-sessions", headers=superadmin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_shell_session_6001_not_online(client, db_session, superadmin_headers):
    runner = await _make_runner(db_session, status="offline")
    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
    )
    assert resp.json()["code"] == 6001
    assert resp.json()["message"] == "Runner 不在线"


@pytest.mark.asyncio
async def test_shell_session_6002_session_exists(client, db_session, superadmin_headers):
    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": "abc123def456"})
    db_session.add(TerminalSession(
        task_id="__runner_shell__",
        container_id="abc123def456",
        runner_id=runner.runner_id,
        shell="/bin/bash",
        created_by="test",
    ))
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
    )
    assert resp.json()["code"] == 6002
    assert resp.json()["message"] == "该 Runner 已有终端会话,请先关闭"


# ---------------------------------------------------------------------------
# R26.F2 / BUG-047:6002 场景 ?force=true 强制关闭旧会话并新建
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shell_session_force_recreates_when_session_exists(client, db_session, superadmin_headers):
    """6002 场景:?force=true → 旧会话收 terminal_close 并置 closed_at,新会话照常创建;
    不带 force 维持 6002(向后兼容)"""
    from datetime import datetime, timezone

    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": "abc123def456"})
    old = TerminalSession(
        task_id="__runner_shell__",
        container_id="abc123def456",
        runner_id=runner.runner_id,
        shell="/bin/bash",
        created_by="test",
    )
    db_session.add(old)
    await db_session.flush()

    sent: list = []
    runner_service.runner_registry.register(runner.runner_id, "worker", SimpleNamespace(), "test")
    orig = runner_service.send_to_runner

    async def _fake(c, message):
        sent.append(message)

    runner_service.send_to_runner = _fake  # type: ignore
    try:
        # 不带 force:维持 6002
        resp_no = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
        )
        assert resp_no.json()["code"] == 6002

        # 带 force:创建成功
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions?force=true",
            headers=superadmin_headers,
        )
    finally:
        runner_service.send_to_runner = orig  # type: ignore
        runner_service.runner_registry.unregister(runner.runner_id)

    body = resp.json()
    assert body["code"] == 0, resp.text
    # 旧会话收到 terminal_close 指令
    close_msgs = [m for m in sent if m.get("type") == "terminal_close"]
    assert any(m.get("session_id") == old.session_id for m in close_msgs)
    # 旧会话台账置 closed_at
    await db_session.refresh(old)
    assert old.closed_at is not None
    # 新会话独立存在且处于打开态
    new_row = (await db_session.execute(
        select(TerminalSession).where(TerminalSession.session_id == body["data"]["session_id"])
    )).scalar_one()
    assert new_row.session_id != old.session_id
    assert new_row.closed_at is None


@pytest.mark.asyncio
async def test_shell_session_6002_cleared_after_close(client, db_session, superadmin_headers):
    """关闭(closed_at 置值)后可再开——6002 判定基于 closed_at IS NULL"""
    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": "abc123def456"})
    from datetime import datetime, timezone

    db_session.add(TerminalSession(
        task_id="__runner_shell__",
        container_id="abc123def456",
        runner_id=runner.runner_id,
        shell="/bin/bash",
        created_by="test",
        closed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    await db_session.flush()

    sent: list = []
    runner_service.runner_registry.register(runner.runner_id, "worker", SimpleNamespace(), "test")
    orig = runner_service.send_to_runner

    async def _fake(c, message):
        sent.append(message)

    runner_service.send_to_runner = _fake  # type: ignore
    try:
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
        )
    finally:
        runner_service.send_to_runner = orig  # type: ignore
        runner_service.runner_registry.unregister(runner.runner_id)
    assert resp.json()["code"] == 0, resp.text


@pytest.mark.asyncio
async def test_shell_session_6003_too_old(client, db_session, superadmin_headers):
    """旧版 Runner:machine_info 无 self_container_id → 6003"""
    runner = await _make_runner(db_session, status="online", machine_info={"os": "linux"})
    runner_service.runner_registry.register(runner.runner_id, "worker", SimpleNamespace(), "test")
    try:
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
        )
    finally:
        runner_service.runner_registry.unregister(runner.runner_id)
    assert resp.json()["code"] == 6003
    assert "版本过旧" in resp.json()["message"]


@pytest.mark.asyncio
async def test_shell_session_host_shell_for_bare_process(client, db_session, superadmin_headers):
    """R31.F1/BUG-043:非容器 runner(新版上报空串)→ 降级宿主 shell:
    code=0 + exec 哨兵 container_id="__host__" + 台账落 __host__"""
    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": ""})
    runner_service.runner_registry.register(runner.runner_id, "worker", SimpleNamespace(), "test")
    sent: list = []
    orig = runner_service.send_to_runner

    async def _fake(c, message):
        sent.append(message)

    runner_service.send_to_runner = _fake  # type: ignore
    try:
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
        )
    finally:
        runner_service.send_to_runner = orig  # type: ignore
        runner_service.runner_registry.unregister(runner.runner_id)
    body = resp.json()
    assert body["code"] == 0, resp.text
    assert body["data"]["session_id"]
    assert sent and sent[0]["container_id"] == "__host__"
    # 台账:宿主会话标记
    row = (await db_session.execute(
        select(TerminalSession).where(TerminalSession.runner_id == runner.runner_id)
    )).scalar_one()
    assert row.container_id == "__host__"
    assert row.shell in ("cmd.exe", "bash")


@pytest.mark.asyncio
async def test_shell_session_6001_when_conn_missing(client, db_session, superadmin_headers):
    """库 online 但内存连接已断 → 同 6001 口径"""
    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": "abc123def456"})
    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
    )
    assert resp.json()["code"] == 6001


# ---------------------------------------------------------------------------
# 判据 2:成功路径 + 判据 10:打开审计
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shell_session_success_and_audit(client, db_session, superadmin_headers):
    headers_user = (await db_session.execute(
        select(AuditLog).limit(0)
    ))
    runner = await _make_runner(
        db_session, status="online", machine_info={"self_container_id": "abc123def456"},
    )
    sent: list = []
    runner_service.runner_registry.register(runner.runner_id, "worker", SimpleNamespace(), "test")

    orig = runner_service.send_to_runner

    async def _fake(c, message):
        sent.append(message)

    runner_service.send_to_runner = _fake  # type: ignore
    try:
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=superadmin_headers,
        )
    finally:
        runner_service.send_to_runner = orig  # type: ignore
        runner_service.runner_registry.unregister(runner.runner_id)

    assert resp.json()["code"] == 0, resp.text
    data = resp.json()["data"]
    assert data["session_id"] and data["ws_url"] == f"/ws/terminal/{data['session_id']}"

    # exec 消息:下发 Runner 自身容器短 id
    assert len(sent) == 1
    msg = sent[0]
    assert msg["type"] == "exec"
    assert msg["container_id"] == "abc123def456"
    assert msg["cmd"] == ["/bin/bash"]
    assert msg["pty"] is True
    assert msg["session_id"] == data["session_id"]

    # 台账行:task_id=__runner_shell__ 标记
    session = (await db_session.execute(
        select(TerminalSession).where(TerminalSession.session_id == data["session_id"])
    )).scalar_one()
    assert session.task_id == "__runner_shell__"
    assert session.container_id == "abc123def456"

    # 判据 10:runner.terminal_open 审计(operator=超管)
    rows = await _spawn_rows("runner.terminal_open")
    assert len(rows) >= 1
    row = rows[0]
    assert row.target_id == runner.runner_id
    assert row.operator_role == "superadmin"
    assert row.detail.get("runner_name") == runner.name


# ---------------------------------------------------------------------------
# 判据 6:非超管 403
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shell_session_403_for_normal_user(client, db_session):
    # 占位注册占掉 superadmin(R1 bootstrap:首个注册用户=superadmin),再取普通用户
    await client.post("/api/auth/register", json={"phone": _phone(), "password": "Test1234"})
    headers, _uid = await _register_and_login(client)
    runner = await _make_runner(db_session, status="online", machine_info={"self_container_id": "abc"})
    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/shell-sessions", headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 判据 3:task_id 解耦(TerminalConnection.task_id 可空)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terminal_connection_task_id_optional():
    """runner shell 场景:不传 task_id;registry put/get/pop 正常;限流不炸"""
    conn = TerminalConnection(
        session_id="s-r26", runner_id="r-1", user_id="u-1", websocket=None,
        role="superadmin",
    )
    assert conn.task_id is None
    terminal_registry.put(conn)
    assert terminal_registry.get("s-r26") is conn
    assert terminal_registry.pop("s-r26") is conn
    assert terminal_registry.get("s-r26") is None

    # push_ai_output 按 task_id 过滤:task_id=None 的会话不被任务广播命中
    from app.services.terminal_service import push_ai_output
    conn2 = TerminalConnection(
        session_id="s-r26b", runner_id="r-1", user_id="u-1", websocket=None,
        task_id="t-1",
    )
    terminal_registry.put(conn2)
    try:
        await push_ai_output("t-None", "[ai] x")  # 不命中 task_id=None 会话,不抛
        await push_ai_output("t-1", "[ai] y")     # 命中 conn2;websocket=None → 转发 False 不抛
    finally:
        terminal_registry.pop("s-r26b")


# ---------------------------------------------------------------------------
# 判据 9:破坏性命令审计(detail 含 runner 会话标记)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_destructive_command_runner_shell_flag():
    """runner shell 会话(task_id=None)的破坏性命令 → detail.session_kind=runner_shell"""
    from app.services.terminal_service import audit_destructive_input

    conn = TerminalConnection(
        session_id="s-r26-audit", runner_id="r-1", user_id="u-super", websocket=None,
        role="superadmin",  # task_id 缺省 None = runner shell 会话
    )
    terminal_registry.put(conn)
    try:
        audit_destructive_input("s-r26-audit", "rm -rf /tmp/x")
        rows = await _spawn_rows("terminal.destructive_command")
        assert len(rows) >= 1
        row = rows[-1]
        assert row.detail.get("matched_pattern") == "rm -rf"
        assert row.detail.get("session_kind") == "runner_shell"
        assert row.user_id == "u-super"
    finally:
        terminal_registry.pop("s-r26-audit")
