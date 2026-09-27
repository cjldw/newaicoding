"""
DELETE /api/tasks/{task_id} 任务删除(R4.F2)— TDD 测试
====================================================
覆盖(DEVPLAN/R4.F2.md 测试验证逻辑 2-7):
2. pending(无容器/消息)dev/test/release → 200,本体+级联(消息/上传文件/Route 残留)清除
3. running → 400「不可删除」;done dev → 400(已产生数据,严档)
4. release 发布完成(done+deploy_phase=deployed)→ 400「发布已完成,请先下线部署」;有活跃 Route → 400
5. 有容器/消息行的 pending → 400(严档)
6. viewer → 403(1901);未认证 → 401
7. 删除留审计痕迹(audit_logs.action_type = task.delete)
"""
import uuid

import pytest
import sqlalchemy

from app.models.audit_log import AuditLog
from app.models.container import Container
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.route import Route
from app.models.task import Task, TaskMessage, TaskUploadedFile


async def _mk_project(db_session, registered_user):
    """空项目(owner=registered_user;删除不走调度,无 Runner/模型依赖)"""
    project = Project(name="任务删除项目", slug=f"td-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_requirement(db_session, project, creator_id, status="approved"):
    r = Requirement(
        req_id=str(uuid.uuid4()), title="登录功能", description="d",
        status=status, req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_task(db_session, project, req, creator_id, type="dev", status="pending", ext=None):
    """直插任务行(绕过创建流程的前置/调度)"""
    t = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type=type, title="待删除任务", description="d",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status=status, conversation_id=str(uuid.uuid4()),
        created_by=creator_id, extended_attributes=ext,
    )
    db_session.add(t)
    await db_session.flush()
    return t


async def _mk_route(db_session, task, project, status="active"):
    """直插网关路由行(活跃=发布已完成判定依据;inactive=残留)"""
    r = Route(
        task_id=task.task_id, project_id=project.project_id,
        host=f"{uuid.uuid4().hex[:12]}.preview.example.com",
        upstream="http://10.0.0.9:8000", type="deploy", port=8000, status=status,
    )
    db_session.add(r)
    await db_session.flush()
    return r


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


async def _task_exists(db_session, task_id: str) -> bool:
    return (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == task_id)
    )).scalars().first() is not None


# ---------------------------------------------------------------------------
# 2. pending(无容器/消息)删除 → 200 + 级联清除 + 审计
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_pending_task_success_cascades(client, auth_headers, db_session, registered_user):
    """pending dev 任务(带上传文件行 + inactive 残留 Route)→ 200;本体/文件/路由清除;审计 task.delete"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"])
    db_session.add(TaskUploadedFile(
        task_id=task.task_id, filename="a.txt", stored_filename="a.txt",
        size=3, container_path="/tmp/uploads/x", uploaded_by=registered_user["user_id"],
    ))
    await _mk_route(db_session, task, project, status="inactive")  # 残留路由随删
    await db_session.flush()

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.json()

    assert await _task_exists(db_session, task.task_id) is False
    assert (await db_session.execute(
        sqlalchemy.select(TaskUploadedFile).where(TaskUploadedFile.task_id == task.task_id)
    )).scalars().first() is None, "上传文件行应级联清除"
    assert (await db_session.execute(
        sqlalchemy.select(Route).where(Route.task_id == task.task_id)
    )).scalars().first() is None, "残留路由应摘除"

    audit = (await db_session.execute(
        sqlalchemy.select(AuditLog).where(
            AuditLog.action_type == "task.delete",
            AuditLog.target_id == task.task_id,
        )
    )).scalars().first()
    assert audit is not None, "删除任务应写审计日志"
    assert audit.project_id == project.project_id


@pytest.mark.asyncio
async def test_delete_pending_release_and_test_task_success(client, auth_headers, db_session, registered_user):
    """pending release / test 任务删除 → 200(三维统一入口)"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    for ttype in ("test", "release"):
        task = await _mk_task(db_session, project, req, registered_user["user_id"], type=ttype)
        resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
        assert resp.status_code == 200, f"{ttype} 应 200,实际 {resp.status_code}: {resp.text}"
        assert await _task_exists(db_session, task.task_id) is False


# ---------------------------------------------------------------------------
# 3. running / done → 400(严档:已开始即不可删)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_running_task_rejected(client, auth_headers, db_session, registered_user):
    """running 任务删除 → 400「不可删除」;任务仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"], status="running")

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可删除" in resp.json()["message"], resp.json()
    assert await _task_exists(db_session, task.task_id) is True


@pytest.mark.asyncio
async def test_delete_done_dev_task_rejected(client, auth_headers, db_session, registered_user):
    """done dev 任务(已产生分支提交数据)删除 → 400;任务仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"], status="done")

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可删除" in resp.json()["message"], resp.json()
    assert await _task_exists(db_session, task.task_id) is True


# ---------------------------------------------------------------------------
# 4. release 发布完成 / 活跃路由 → 400「发布已完成,请先下线部署」
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_deployed_release_rejected(client, auth_headers, db_session, registered_user):
    """release done + deploy_phase=deployed → 400「发布已完成,请先下线部署」(不得按不存在的 deployed 状态值判)"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"], type="release",
                          status="done", ext={"deploy_phase": "deployed", "deploy_port": 10042})

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["message"] == "发布已完成,请先下线部署", resp.json()
    assert await _task_exists(db_session, task.task_id) is True


@pytest.mark.asyncio
async def test_delete_release_with_active_route_rejected(client, auth_headers, db_session, registered_user):
    """release 仍有活跃 Route(在线服务)→ 400,任务仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"], type="release")
    await _mk_route(db_session, task, project, status="active")

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "下线" in resp.json()["message"], resp.json()
    assert await _task_exists(db_session, task.task_id) is True


# ---------------------------------------------------------------------------
# 5. 有容器 / 消息行的 pending → 400(严档:已产生数据)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_pending_with_container_row_rejected(client, auth_headers, db_session, registered_user):
    """pending 但已有容器台账行 → 400「已产生数据,不可删除」;任务与容器行保留"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"])
    db_session.add(Container(
        container_id=str(uuid.uuid4()), task_id=task.task_id, runner_id="rn-x",
        project_id=project.project_id, status="stopped", exposed_ports=[8000],
    ))
    await db_session.flush()

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可删除" in resp.json()["message"], resp.json()
    assert await _task_exists(db_session, task.task_id) is True
    assert (await db_session.execute(
        sqlalchemy.select(Container).where(Container.task_id == task.task_id)
    )).scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_pending_with_message_row_rejected(client, auth_headers, db_session, registered_user):
    """pending 但已有对话消息行 → 400(严档);任务与消息保留"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"])
    db_session.add(TaskMessage(task_id=task.task_id, role="user", content="开始实现"))
    await db_session.flush()

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可删除" in resp.json()["message"], resp.json()
    assert await _task_exists(db_session, task.task_id) is True
    assert (await db_session.execute(
        sqlalchemy.select(TaskMessage).where(TaskMessage.task_id == task.task_id)
    )).scalars().first() is not None


# ---------------------------------------------------------------------------
# 6. viewer → 403(1901);未认证 → 401
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_task_viewer_forbidden(client, auth_headers, db_session, registered_user):
    """viewer 删除任务 → 403(1901,editor 档);任务仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"])
    viewer = await _mk_member_user(client, db_session, project, registered_user["user_id"], "viewer")

    resp = await client.delete(f"/api/tasks/{task.task_id}", headers=viewer["headers"])
    assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1901, resp.json()
    assert await _task_exists(db_session, task.task_id) is True


@pytest.mark.asyncio
async def test_delete_task_unauthenticated_401(client, db_session, registered_user):
    """未认证 DELETE → 401"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    resp = await client.delete(f"/api/tasks/{task.task_id}")
    assert resp.status_code == 401, f"应 401,实际 {resp.status_code}"
