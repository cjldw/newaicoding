"""
DELETE /api/requirements/{req_id} 需求删除(R4.F1)— TDD 测试
==========================================================
覆盖(DEVPLAN/R4.F1.md 测试验证逻辑 2-7):
2. owner 删「待评审且无关联」需求 → 200,本体+从属数据(原型链接/关联用户)清除
3. owner 删「评审通过及之后(approved/in_progress/done/archived)」→ 400 文案含「不可删除」,需求仍在
4. 有关联任务(任意任务状态)→ 400,需求与任务均在
5. editor/viewer 删除 → 403(1901);未认证 → 401
7. 删除留审计痕迹(audit_logs.action_type = requirement.delete)
"""
import uuid

import pytest
import sqlalchemy

from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task


async def _mk_project(db_session, registered_user):
    """空项目(owner=registered_user;删除不走 GitLab/调度,无 Runner 依赖)"""
    project = Project(name="删除项目", slug=f"rd-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_requirement(db_session, project, creator_id, status="draft", links=None, related=None):
    """直插需求行(可带从属数据:原型链接/关联用户)"""
    r = Requirement(
        req_id=str(uuid.uuid4()),
        title="待删除需求", description="描述", status=status,
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
        prototype_links=links,
        related_user_ids=related,
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


# ---------------------------------------------------------------------------
# 2. owner 删待评审且无关联 → 200 + 本体/从属数据清除 + 审计留痕
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_draft_requirement_success(client, auth_headers, db_session, registered_user):
    """owner 删 draft 需求(带原型链接/关联用户)→ 200;行消失(从属字段随行清除);审计 requirement.delete"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(
        db_session, project, registered_user["user_id"], status="draft",
        links=[{"label": "Figma", "url": "https://figma.com/file/x"}],
        related=[registered_user["user_id"]],
    )

    resp = await client.delete(f"/api/requirements/{req.req_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.json()

    # 本体硬删(原型链接/关联用户/评审字段均为行内字段,随行清除)
    row = (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req.req_id)
    )).scalars().first()
    assert row is None

    # 审计留痕
    audit = (await db_session.execute(
        sqlalchemy.select(AuditLog).where(
            AuditLog.action_type == "requirement.delete",
            AuditLog.target_id == req.req_id,
        )
    )).scalars().first()
    assert audit is not None, "删除需求应写审计日志"
    assert audit.project_id == project.project_id
    assert audit.user_id == registered_user["user_id"]


# ---------------------------------------------------------------------------
# 3. 评审通过及之后状态 → 400「不可删除」,需求仍在
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_approved_or_later_rejected(client, auth_headers, db_session, registered_user):
    """approved/in_progress/done/archived → 400 文案含「不可删除」;需求未被删除"""
    project = await _mk_project(db_session, registered_user)
    for status in ("approved", "in_progress", "done", "archived"):
        req = await _mk_requirement(db_session, project, registered_user["user_id"], status=status)
        resp = await client.delete(f"/api/requirements/{req.req_id}", headers=auth_headers)
        assert resp.status_code == 400, f"{status} 应 400,实际 {resp.status_code}: {resp.text}"
        assert "不可删除" in resp.json()["message"], resp.json()
        row = (await db_session.execute(
            sqlalchemy.select(Requirement).where(Requirement.req_id == req.req_id)
        )).scalars().first()
        assert row is not None, f"{status} 需求不应被删除"


# ---------------------------------------------------------------------------
# 4. 有关联任务(任意任务状态)→ 400,需求与任务均在
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_requirement_with_related_task_rejected(client, auth_headers, db_session, registered_user):
    """draft 需求但 Task.req_id 命中 → 400「需求已关联任务,不可删除」;需求与任务均保留"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], status="draft")
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="关联任务", description="d",
        base_branch="master", work_branch="feat/x", status="done",
        conversation_id=str(uuid.uuid4()), created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    resp = await client.delete(f"/api/requirements/{req.req_id}", headers=auth_headers)
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {resp.text}"
    assert "不可删除" in resp.json()["message"], resp.json()
    assert (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req.req_id)
    )).scalars().first() is not None
    assert (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == task.task_id)
    )).scalars().first() is not None


# ---------------------------------------------------------------------------
# 5. editor / viewer → 403(1901);未认证 → 401
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_requirement_editor_forbidden(client, auth_headers, db_session, registered_user):
    """editor(非 owner)删除 → 403(仅 owner 可删,对齐 cancel 档);需求仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], status="draft")
    editor = await _mk_member_user(client, db_session, project, registered_user["user_id"], "editor")

    resp = await client.delete(f"/api/requirements/{req.req_id}", headers=editor["headers"])
    assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1901, resp.json()
    assert (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req.req_id)
    )).scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_requirement_viewer_forbidden(client, auth_headers, db_session, registered_user):
    """viewer 删除 → 403(1901);需求仍在"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], status="draft")
    viewer = await _mk_member_user(client, db_session, project, registered_user["user_id"], "viewer")

    resp = await client.delete(f"/api/requirements/{req.req_id}", headers=viewer["headers"])
    assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1901, resp.json()
    assert (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req.req_id)
    )).scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_requirement_unauthenticated_401(client, db_session, registered_user):
    """未认证 DELETE → 401"""
    project = await _mk_project(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], status="draft")

    resp = await client.delete(f"/api/requirements/{req.req_id}")
    assert resp.status_code == 401, f"应 401,实际 {resp.status_code}"
