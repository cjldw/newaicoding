"""
PATCH /api/tasks/{task_id} 任务字段编辑(R2.F2)— TDD 测试
==========================================
覆盖(DEVPLAN/R2.F2.md 接口契约):
1. pending dev 任务 PATCH title/description/base_branch/work_branch → 200 且生效
2. pending release 任务改 deploy_port:已占用端口 → 400(7001);空闲端口 → 200
3. 非 pending(running/done)任务 PATCH → 400「任务已开始,不可编辑」
4. PATCH 带 type/req_id/status → 被忽略(响应值不变;不在 UpdateTaskRequest schema)
5. viewer 项目成员 → 403;未认证 → 401
6. title 空串 / 129 字 → 422 带字段名
7. base_branch/work_branch 仅 dev 类型接受(其它类型静默忽略)
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task
from tests.test_tasks_api import _mk_requirement


async def _mk_project(db_session, registered_user):
    """空项目(owner=registered_user,无 Runner/模型依赖;编辑不走调度)"""
    project = Project(name="编辑项目", slug=f"tu-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_task(db_session, project, req, creator_id, type="dev", status="pending", ext=None):
    """直插任务行(绕过创建流程的前置/调度)"""
    t = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type=type, title="旧标题", description="旧描述",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status=status, conversation_id=str(uuid.uuid4()),
        created_by=creator_id,
        extended_attributes=ext,
    )
    db_session.add(t)
    await db_session.flush()
    return t


async def _patch_task(client, headers, task_id, payload: dict) -> httpx.Response:
    return await client.patch(f"/api/tasks/{task_id}", headers=headers, json=payload)


# ---------------------------------------------------------------------------
# 1. pending dev 任务:通用 + 分支字段全部生效
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_pending_dev_task_fields(client, auth_headers, db_session, registered_user):
    """pending dev 任务 PATCH title/description/base_branch/work_branch → 200 且生效"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    resp = await _patch_task(client, auth_headers, task.task_id, {
        "title": "新标题", "description": "新描述",
        "base_branch": "master2", "work_branch": "feat/new-work",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.json()

    detail = (await client.get(f"/api/tasks/{task.task_id}", headers=auth_headers)).json()["data"]
    assert detail["title"] == "新标题"
    assert detail["description"] == "新描述"
    assert detail["base_branch"] == "master2"
    assert detail["work_branch"] == "feat/new-work"


# ---------------------------------------------------------------------------
# 2. pending release 任务:deploy_port 全平台唯一校验
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_release_task_port_conflict_then_free(client, auth_headers, db_session, registered_user):
    """改 deploy_port 为已占用端口 → 400(7001);改为空闲端口 → 200 且 ext 生效"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"], type="release",
                          ext={"deploy_host": "mine.example.com", "deploy_port": 10080,
                               "deploy_script": "echo hi", "deploy_phase": "deploying"})

    # 平台上已存在同端口的其他 release 任务(done 不在排除列表,占用生效)
    other_project = Project(name="o", slug=f"o-{uuid.uuid4().hex[:6]}",
                            owner_id=registered_user["user_id"])
    db_session.add(other_project)
    await db_session.flush()
    db_session.add(Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=other_project.project_id,
        type="release", title="o", description="d", base_branch="m", work_branch="m",
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
        extended_attributes={"deploy_port": 10081, "deploy_host": "other.example.com",
                             "deploy_phase": "deployed"},
    ))
    await db_session.flush()

    resp = await _patch_task(client, auth_headers, task.task_id, {"deploy_port": 10081})
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 7001, resp.json()
    assert "端口" in resp.json()["message"], resp.json()

    resp = await _patch_task(client, auth_headers, task.task_id, {"deploy_port": 10090})
    assert resp.status_code == 200, resp.text
    await db_session.refresh(task)
    assert task.extended_attributes["deploy_port"] == 10090
    # 原有 ext 字段不被清掉
    assert task.extended_attributes["deploy_host"] == "mine.example.com"


# ---------------------------------------------------------------------------
# 3. 非 pending 任务:400「任务已开始,不可编辑」
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_non_pending_task_rejected(client, auth_headers, db_session, registered_user):
    """running/done 任务 PATCH → 400,消息「任务已开始,不可编辑」"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    for status in ("running", "done"):
        task = await _mk_task(db_session, project, req, registered_user["user_id"], status=status)
        resp = await _patch_task(client, auth_headers, task.task_id, {"title": "新标题"})
        assert resp.status_code == 400, f"{status} 应 400,实际 {resp.status_code}: {resp.text}"
        assert resp.json()["message"] == "任务已开始,不可编辑", resp.json()


# ---------------------------------------------------------------------------
# 4. 保护字段:type / req_id / status 被忽略
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_ignores_protected_fields(client, auth_headers, db_session, registered_user):
    """PATCH 带 type/req_id/status → 200 但三者不变(不在 schema,pydantic 忽略)"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    resp = await _patch_task(client, auth_headers, task.task_id, {
        "title": "新标题", "type": "release", "req_id": str(uuid.uuid4()), "status": "done",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["title"] == "新标题"
    assert data["type"] == "dev"
    assert data["req_id"] == req.req_id
    assert data["status"] == "pending"
    await db_session.refresh(task)
    assert task.type == "dev" and task.status == "pending"


# ---------------------------------------------------------------------------
# 5. 权限:viewer → 403;未认证 → 401
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_viewer_forbidden(client, auth_headers, db_session, registered_user):
    """viewer 项目成员 PATCH → 403(1901)"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    # 第二个用户注册并以 viewer 身份入项目
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0
    viewer_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    db_session.add(ProjectMember(project_id=project.project_id, user_id=viewer_id,
                                 role="viewer", invited_by=registered_user["user_id"]))
    await db_session.flush()

    resp = await _patch_task(client, viewer_headers, task.task_id, {"title": "越权改"})
    assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1901


@pytest.mark.asyncio
async def test_update_unauthenticated_401(client, db_session, registered_user):
    """未认证 PATCH → 401"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    resp = await client.patch(f"/api/tasks/{task.task_id}", json={"title": "x"})
    assert resp.status_code == 401, f"应 401,实际 {resp.status_code}"


# ---------------------------------------------------------------------------
# 6. title 校验:空串 / 129 字 → 422 带字段名
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_title_validation_422(client, auth_headers, db_session, registered_user):
    """title=""(min_length=1)/ 129 字(max_length=128)→ 422,message 含字段名 title"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"])

    for bad_title in ("", "x" * 129):
        resp = await _patch_task(client, auth_headers, task.task_id, {"title": bad_title})
        assert resp.status_code == 422, f"应 422,实际 {resp.status_code}: {resp.text}"
        assert "title" in resp.json()["message"], resp.json()


# ---------------------------------------------------------------------------
# 7. base_branch / work_branch 仅 dev 类型接受
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_branch_fields_ignored_for_non_dev(client, auth_headers, db_session, registered_user):
    """release 任务 PATCH 带 base_branch/work_branch → 200 但分支不变(静默忽略)"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    task = await _mk_task(db_session, project, req, registered_user["user_id"], type="release",
                          ext={"deploy_port": 10080, "deploy_host": "mine.example.com"})

    resp = await _patch_task(client, auth_headers, task.task_id, {
        "title": "新标题", "base_branch": "hack", "work_branch": "hack",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["base_branch"] == "master"
    assert resp.json()["data"]["work_branch"] == task.work_branch
