"""
R21/R22 工作台与四维管理测试
==========================
- summary:四卡片统计 + 每类 recent ≤5 + created_by 口径 + archived 项目不可见
- 四维列表:requirements/tasks(dev/test/release)过滤与分页
- 超管口径:全部 active 项目
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.task import Task
from tests.test_tasks_api import _bind_gitlab_token


async def _setup(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name="工作台项目", slug=f"db-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_requirement(db_session, project, creator_id, title, status, priority="medium"):
    r = Requirement(
        req_id=str(uuid.uuid4()), title=title, description="d", status=status,
        priority=priority, req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_task(db_session, project, creator_id, task_type, title, status):
    t = Task(
        task_id=str(uuid.uuid4()), req_id="req-x", project_id=project.project_id,
        type=task_type, title=title, description="d",
        base_branch="b", work_branch="b", status=status,
        conversation_id=str(uuid.uuid4()), created_by=creator_id,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_dashboard_summary_counts(client, auth_headers, db_session, registered_user):
    """summary:created_by=me 口径;by_status 分布;recent ≤5"""
    project = await _setup(db_session, registered_user)

    # 需求 3 条(不同状态)
    await _mk_requirement(db_session, project, registered_user["user_id"], "需求A", "draft")
    await _mk_requirement(db_session, project, registered_user["user_id"], "需求B", "approved")
    await _mk_requirement(db_session, project, registered_user["user_id"], "需求C", "approved")

    # 任务:dev ×3(pending/running/done),test ×1(passed),release ×1(failed)
    await _mk_task(db_session, project, registered_user["user_id"], "dev", "d1", "pending")
    await _mk_task(db_session, project, registered_user["user_id"], "dev", "d2", "running")
    await _mk_task(db_session, project, registered_user["user_id"], "dev", "d3", "done")
    await _mk_task(db_session, project, registered_user["user_id"], "test", "t1", "passed")
    await _mk_task(db_session, project, registered_user["user_id"], "release", "r1", "failed")

    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    data = resp.json()["data"]
    assert data["requirements"]["total"] == 3
    assert data["requirements"]["by_status"]["approved"] == 2
    assert data["requirements"]["by_status"]["draft"] == 1
    assert data["dev_tasks"]["total"] == 3
    assert data["dev_tasks"]["by_status"]["done"] == 1
    assert data["test_tasks"]["total"] == 1
    assert data["release_tasks"]["total"] == 1
    # by_status 全集返回(0 也返回)
    assert "archived" in data["requirements"]["by_status"]
    assert "timeout" in data["dev_tasks"]["by_status"]


@pytest.mark.asyncio
async def test_dashboard_summary_recent_max5(client, auth_headers, db_session, registered_user):
    """recent ≤5:创建 7 条 dev,只返回 5 条(按 updated_at 倒序)"""
    project = await _setup(db_session, registered_user)
    for i in range(7):
        await _mk_task(db_session, project, registered_user["user_id"], "dev", f"任务{i}", "done")

    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    recent = resp.json()["data"]["dev_tasks"]["recent"]
    assert len(recent) == 5


@pytest.mark.asyncio
async def test_dashboard_excludes_archived_project(client, auth_headers, db_session, registered_user):
    """archived 项目数据不出现"""
    project = await _setup(db_session, registered_user)
    project.status = "archived"
    await db_session.flush()
    await _mk_requirement(db_session, project, registered_user["user_id"], "隐藏需求", "draft")

    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.json()["data"]["requirements"]["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_no_projects_empty(client, auth_headers, registered_user):
    """无项目:全 0 空态"""
    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    data = resp.json()["data"]
    assert data["requirements"]["total"] == 0
    assert data["dev_tasks"]["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_created_by_filtering(client, auth_headers, db_session, registered_user):
    """created_by=me:他人创建的不计入(即使同项目)"""
    project = await _setup(db_session, registered_user)
    from tests.test_projects_api import _register_and_login

    other_headers, other_uid = await _register_and_login(client)
    # 他人创建
    await _mk_requirement(db_session, project, other_uid, "他人的", "draft")

    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.json()["data"]["requirements"]["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_summary_visible_projects_member(client, auth_headers, db_session, registered_user):
    """BUG-051/R21.F1:非 owner 成员 summary 含 visible_projects=可见 active 项目数(≥1)"""
    project = await _setup(db_session, registered_user)
    from app.models.project_member import ProjectMember
    from tests.test_projects_api import _register_and_login

    # 非 owner 成员:第二个用户被拉进项目当 editor(owner 是 registered_user)
    member_headers, member_uid = await _register_and_login(client)
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=member_uid, role="editor",
        invited_by=registered_user["user_id"],
    ))
    await db_session.flush()

    # 成员可见 1 个 active 项目(owner 的项目,自己是 editor)
    resp = await client.get("/api/dashboard/summary", headers=member_headers)
    data = resp.json()["data"]
    assert data["visible_projects"] == 1

    # owner 同项目:visible_projects 同为 1(门槛与数据同源)
    resp_owner = await client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp_owner.json()["data"]["visible_projects"] == 1


@pytest.mark.asyncio
async def test_dashboard_summary_visible_projects_empty(client, auth_headers, registered_user):
    """BUG-051/R21.F1:无项目用户 visible_projects=0(空态门槛依据)"""
    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.json()["data"]["visible_projects"] == 0


# ---------------------------------------------------------------------------
# R22 四维列表
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requirements_list_filtered(client, auth_headers, db_session, registered_user):
    """四维-需求列表:status 过滤 + project 信息"""
    project = await _setup(db_session, registered_user)
    await _mk_requirement(db_session, project, registered_user["user_id"], "草稿需求", "draft")
    await _mk_requirement(db_session, project, registered_user["user_id"], "通过需求", "approved")

    resp = await client.get(
        "/api/dashboard/requirements", headers=auth_headers, params={"status": "approved"}
    )
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["title"] == "通过需求"
    assert data["items"][0]["project"]["name"]


@pytest.mark.asyncio
async def test_tasks_list_by_type(client, auth_headers, db_session, registered_user):
    """四维-任务列表:dev/test/release 分列"""
    project = await _setup(db_session, registered_user)
    await _mk_task(db_session, project, registered_user["user_id"], "dev", "开发1", "running")
    await _mk_task(db_session, project, registered_user["user_id"], "test", "测试1", "passed")
    await _mk_task(db_session, project, registered_user["user_id"], "release", "发布1", "failed")

    for task_type, expected in (("dev", 1), ("test", 1), ("release", 1)):
        resp = await client.get(
            f"/api/dashboard/tasks/{task_type}", headers=auth_headers
        )
        data = resp.json()["data"]
        assert data["total"] == expected
        assert data["items"][0]["type"] == task_type

    # 未知维度 → 404
    resp = await client.get("/api/dashboard/tasks/unknown", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tasks_list_pagination(client, auth_headers, db_session, registered_user):
    """分页:page=2, page_size=2"""
    project = await _setup(db_session, registered_user)
    for i in range(3):
        await _mk_task(db_session, project, registered_user["user_id"], "dev", f"d{i}", "done")

    resp = await client.get(
        "/api/dashboard/tasks/dev", headers=auth_headers, params={"page": 2, "page_size": 2}
    )
    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["page"] == 2
