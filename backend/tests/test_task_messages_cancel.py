"""
R34.F1 消息级真取消(后端)— TDD Red 契约测试
====================================================
契约(DEVPLAN/R34.F1.md 实现要点;.scratch/fix-analysis.md 第 5 问):

平台侧 POST /api/tasks/{task_id}/messages/cancel:
- 鉴权 401;任务不存在 404(任务不存在);权限 owner/editor 放行,viewer/非成员
  → 403 code=1901(与 PATCH/DELETE 任务同口径,require_project_role(editor))
- 状态守卫:任务已结束(done)/ 无 running 容器 / Runner 离线 → 400(9001 档)
- req_id 追踪:按 task_id 在 runner_service._stream_requests 定位执行中请求,
  向对应 Runner 下发 {"type":"exec_tool_cancel","req_id":<执行中 req_id>}
- 幂等:无执行中请求(从未开始 / 已取消 / 已自然结束)→ 200 code=0
  data.cancelled=False,且不得向 Runner 下发任何消息

runner_service 侧(单元):
- cancel_stream_request(conn, req_id) -> bool:下发 exec_tool_cancel + 本地结算
  流式请求(投递 done ok=False),返回是否存在匹配 req_id;重复取消幂等 False

不测(理由见 .scratch/R34.F1/qa-red-tests.md):runner 进程侧(runner/main.py +
container_manager 的 docker exec pkill -f claude)依赖真实 docker socket 与运行中
容器,非平台侧单测可测面,归集成/手工验证。
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services import runner_service
from app.services.runner_service import runner_registry


class FakeRunnerWS:
    """Runner WebSocket 替身(记录下发消息;与 test_r32_chat_stream_inject 同款)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


# ---------------------------------------------------------------------------
# 造数助手
# ---------------------------------------------------------------------------
async def _mk_running_task(db_session, registered_user, with_container=True,
                           register_conn=True, status="running"):
    """项目 + 需求 + running 任务 + (可选)running 容器 + (可选)在线 Runner 连接"""
    project = Project(name="消息取消项目", slug=f"mc-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()), title="取消功能", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}", created_by=registered_user["user_id"],
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="取消测试任务", description="d",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status=status, conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    conn = None
    runner_id = f"rn-{uuid.uuid4().hex[:6]}"
    if with_container:
        db_session.add(Runner(name=runner_id, role="worker", token_hash="x",
                              status="online", created_by="t"))
        await db_session.flush()
        if register_conn:
            conn = runner_registry.register(runner_id, "worker", FakeRunnerWS(), host="test")
        db_session.add(Container(
            container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
            runner_id=runner_id, project_id=project.project_id,
            status="running", image="img", cpu_limit="2c", mem_limit="4g", disk_limit="10g",
        ))
        await db_session.flush()
    return {"project": project, "req": req, "task": task, "conn": conn}


async def _open_stream(conn, task) -> tuple[str, "asyncio.Queue"]:
    """在 FakeRunnerWS 上注册一条执行中的流式请求(模拟 send_message_stream 进行中)"""
    return await runner_service.request_runner_stream(
        conn, {"type": "exec_tool", "tool": "claude_prompt_stream",
               "task_id": task.task_id}, timeout=60,
    )


async def _mk_member_user(client, db_session, project, owner_id, role):
    """注册第二用户并以指定角色入项目,返回 {headers, user_id}"""
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    db_session.add(ProjectMember(project_id=project.project_id, user_id=user_id,
                                 role=role, invited_by=owner_id))
    await db_session.flush()
    return {"headers": headers, "user_id": user_id}


# ---------------------------------------------------------------------------
# A. 契约主路径:取消执行中消息 → 下发 exec_tool_cancel
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_inflight_stream_sends_exec_tool_cancel(client, auth_headers, db_session,
                                                             registered_user):
    """有执行中流式请求 → 200 code=0 cancelled=True;Runner 收到
    {"type":"exec_tool_cancel","req_id":<执行中 req_id>}(req_id 原样追踪,不新造)"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    req_id, _queue = await _open_stream(conn, task)
    try:
        resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel",
                                 headers=auth_headers)
        assert resp.status_code == 200, f"应 200,实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["code"] == 0, body
        assert body["data"]["cancelled"] is True, body

        # 注:request_runner_stream 的 setup 消息(type=exec_tool)经同一 FakeRunnerWS
        # 下发(R32.F3 既有行为),故按 type 过滤 cancel 消息计数,而非统计 sent 总长
        cancels = [m for m in conn.websocket.sent if m["type"] == "exec_tool_cancel"]
        assert len(cancels) == 1, f"应恰好下发 1 条 cancel,实际 {conn.websocket.sent}"
        msg = cancels[0]
        assert msg["req_id"] == req_id, f"req_id 应追踪执行中请求,期望 {req_id},实际 {msg}"
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_without_inflight_is_idempotent_no_dispatch(client, auth_headers,
                                                                 db_session, registered_user):
    """无执行中请求 → 200 code=0 cancelled=False(幂等),且不向 Runner 下发任何消息"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    try:
        resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel",
                                 headers=auth_headers)
        assert resp.status_code == 200, f"应 200,实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["code"] == 0, body
        assert body["data"]["cancelled"] is False, body
        assert conn.websocket.sent == [], "无执行中请求不得下发 cancel 消息"
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_twice_second_still_ok_idempotent(client, auth_headers, db_session,
                                                       registered_user):
    """连续两次取消:第二次仍 200 code=0(不 500/409),前端双击/竞态安全"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    await _open_stream(conn, task)
    try:
        r1 = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
        assert r1.status_code == 200, r1.text
        r2 = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
        assert r2.status_code == 200, f"第二次取消应幂等 200,实际 {r2.status_code}: {r2.text}"
        assert r2.json()["code"] == 0, r2.json()
    finally:
        runner_registry.unregister(conn.runner_id)


# ---------------------------------------------------------------------------
# B. 任务存在性与权限
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_task_not_found_404(client, auth_headers):
    """任务不存在 → 404 统一响应体(code=404「任务不存在」)"""
    resp = await client.post(f"/api/tasks/{uuid.uuid4()}/messages/cancel", headers=auth_headers)
    assert resp.status_code == 404, f"应 404,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 404, resp.json()
    assert "任务不存在" in resp.json()["message"], resp.json()


@pytest.mark.asyncio
async def test_cancel_unauthenticated_401(client, db_session, registered_user):
    """未认证 → 401"""
    env = await _mk_running_task(db_session, registered_user)
    resp = await client.post(f"/api/tasks/{env['task'].task_id}/messages/cancel")
    assert resp.status_code == 401, f"应 401,实际 {resp.status_code}"


@pytest.mark.asyncio
async def test_cancel_viewer_forbidden_403_1901(client, auth_headers, db_session,
                                                registered_user):
    """viewer → 403 code=1901(写操作 editor 档,与 PATCH/DELETE 任务同口径);不下发消息"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    viewer = await _mk_member_user(client, db_session, env["project"],
                                   registered_user["user_id"], "viewer")
    try:
        resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel",
                                 headers=viewer["headers"])
        assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
        assert resp.json()["code"] == 1901, resp.json()
        assert conn.websocket.sent == [], "权限拒绝不得下发 cancel 消息"
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_non_member_forbidden_403_1901(client, auth_headers, db_session,
                                                    registered_user, second_user_headers):
    """非项目成员(已认证)→ 403 code=1901"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    try:
        resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel",
                                 headers=second_user_headers)
        assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
        assert resp.json()["code"] == 1901, resp.json()
    finally:
        runner_registry.unregister(conn.runner_id)


# ---------------------------------------------------------------------------
# C. 任务状态守卫(容器 / Runner / 任务终态)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_done_task_rejected_400(client, auth_headers, db_session, registered_user):
    """任务已结束(done,容器已销毁)→ 400;不下发消息"""
    env = await _mk_running_task(db_session, registered_user, with_container=False, status="done")
    task = env["task"]
    resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可取消" in resp.json()["message"], resp.json()


@pytest.mark.asyncio
async def test_cancel_no_running_container_400(client, auth_headers, db_session, registered_user):
    """running 任务但无 running 容器 → 400 code=9001;不下发消息(与 send_message 同守卫口径)"""
    project = Project(name="无容器项目", slug=f"nc-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()), title="r", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}", created_by=registered_user["user_id"],
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="t", description="d", base_branch="master",
        work_branch=f"req-{uuid.uuid4().hex[:6]}", status="running",
        conversation_id=str(uuid.uuid4()), created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 9001, resp.json()


@pytest.mark.asyncio
async def test_cancel_runner_offline_400(client, auth_headers, db_session, registered_user):
    """容器行在但 Runner 连接未注册(离线)→ 400 code=9001;不下发消息"""
    env = await _mk_running_task(db_session, registered_user, register_conn=False)
    task = env["task"]
    resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 9001, resp.json()


# ---------------------------------------------------------------------------
# D. runner_service 单元:cancel_stream_request(下发 + 本地结算 + 幂等)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_stream_request_sends_and_resolves_done():
    """cancel_stream_request:下发 exec_tool_cancel(原 req_id)+ 本地结算
    done(ok=False,error 含「取消」);返回 True"""
    conn = runner_registry.register(f"cs-{uuid.uuid4().hex[:6]}", "worker",
                                    FakeRunnerWS(), host="test")
    req_id, queue = await runner_service.request_runner_stream(
        conn, {"type": "exec_tool", "tool": "claude_prompt_stream", "task_id": "t1"}, timeout=60,
    )
    try:
        ok = await runner_service.cancel_stream_request(conn, req_id)
        assert ok is True

        # sent 含 setup 的 exec_tool(见 _open_stream 注),按 type 过滤后恰 1 条 cancel
        cancels = [m for m in conn.websocket.sent if m["type"] == "exec_tool_cancel"]
        assert len(cancels) == 1, conn.websocket.sent
        msg = cancels[0]
        assert msg["req_id"] == req_id, msg

        evt = await queue.get()
        assert evt["type"] == "done", evt
        assert evt["ok"] is False, evt
        assert "取消" in evt["error"], evt
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_stream_request_unknown_req_returns_false_no_send():
    """未知 req_id → 返回 False 且不向 Runner 下发任何消息"""
    conn = runner_registry.register(f"cs-{uuid.uuid4().hex[:6]}", "worker",
                                    FakeRunnerWS(), host="test")
    try:
        ok = await runner_service.cancel_stream_request(conn, "no-such-req")
        assert ok is False
        assert conn.websocket.sent == []
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_stream_request_twice_second_returns_false():
    """同一 req_id 取消两次:第二次返回 False(已注销),队列只收到一个 done"""
    conn = runner_registry.register(f"cs-{uuid.uuid4().hex[:6]}", "worker",
                                    FakeRunnerWS(), host="test")
    req_id, queue = await runner_service.request_runner_stream(
        conn, {"type": "exec_tool", "tool": "claude_prompt_stream", "task_id": "t2"}, timeout=60,
    )
    try:
        assert await runner_service.cancel_stream_request(conn, req_id) is True
        assert await runner_service.cancel_stream_request(conn, req_id) is False

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        assert len([e for e in events if e["type"] == "done"]) == 1, events
    finally:
        runner_registry.unregister(conn.runner_id)


# ---------------------------------------------------------------------------
# E. 边界:并发取消 / 取消后新流
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_concurrent_requests_dispatch_exactly_once(client, auth_headers,
                                                                db_session, registered_user):
    """并发两次 cancel(双击/竞态):均 200,恰下发 1 条 exec_tool_cancel,
    恰一次 cancelled=True(先到者取消,后到者幂等 False),无 5xx"""
    import asyncio

    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    await _open_stream(conn, task)
    try:
        r1, r2 = await asyncio.gather(
            client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers),
            client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers),
        )
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        flags = sorted([r1.json()["data"]["cancelled"], r2.json()["data"]["cancelled"]])
        assert flags == [False, True], (r1.json(), r2.json())
        cancels = [m for m in conn.websocket.sent if m["type"] == "exec_tool_cancel"]
        assert len(cancels) == 1, conn.websocket.sent
    finally:
        runner_registry.unregister(conn.runner_id)


@pytest.mark.asyncio
async def test_cancel_then_new_stream_tracks_fresh_req_id(client, auth_headers, db_session,
                                                          registered_user):
    """取消后同一连接再开新流:新 req_id 不复用;再次取消追踪新 req_id,不误伤旧 req"""
    env = await _mk_running_task(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    old_req_id, old_queue = await _open_stream(conn, task)
    try:
        r1 = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
        assert r1.status_code == 200 and r1.json()["data"]["cancelled"] is True, r1.text
        assert (await old_queue.get())["ok"] is False, "旧流应收到底 done 结算"

        new_req_id, new_queue = await _open_stream(conn, task)
        assert new_req_id != old_req_id, "取消后新流 req_id 不得复用"
        r2 = await client.post(f"/api/tasks/{task.task_id}/messages/cancel", headers=auth_headers)
        assert r2.status_code == 200 and r2.json()["data"]["cancelled"] is True, r2.text
        cancels = [m for m in conn.websocket.sent if m["type"] == "exec_tool_cancel"]
        assert len(cancels) == 2, conn.websocket.sent
        assert cancels[-1]["req_id"] == new_req_id, "第二次取消应追踪新流 req_id"
        assert (await new_queue.get())["ok"] is False, "新流也应被取消结算"
    finally:
        runner_registry.unregister(conn.runner_id)
