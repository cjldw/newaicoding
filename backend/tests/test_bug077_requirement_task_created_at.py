"""
BUG-077:需求详情页关联任务列表「创建时间」列显示为空
====================================================
根因:`build_detail` 的 tasks 子列表未返回 `created_at`/`display_status`,
前端 RequirementDetail.tsx:482 硬编码 `—`。

覆盖:
1. GET /api/requirements/{req_id} 响应中 tasks 每项含 created_at 字段
2. created_at 为合法 ISO 时间串(非 null)
3. display_status 字段存在(R22.F3 打磨任务混合类型改造波及面)
4. requirement 类型任务(打磨任务)同样返回 created_at
"""
import uuid

import pytest

from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task


async def _setup(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(
        name="BUG-077 项目", slug=f"bug077-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_req(db_session, project, creator_id, title):
    r = Requirement(
        req_id=str(uuid.uuid4()), title=title, description="d", status="approved",
        priority="medium", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_task(db_session, project, creator_id, requirement, task_type, title, status="running"):
    t = Task(
        task_id=str(uuid.uuid4()), req_id=requirement.req_id,
        project_id=project.project_id, type=task_type, title=title,
        description="d", base_branch="b", work_branch="b", status=status,
        created_by=creator_id,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_requirement_detail_tasks_include_created_at(
    client, auth_headers, db_session, registered_user,
):
    """BUG-077:需求详情 tasks 子列表每项必须含 created_at(非 null)"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "BUG-077 需求")
    task = await _mk_task(db_session, project, registered_user["user_id"], req, "dev", "开发任务")

    resp = await client.get(f"/api/requirements/{req.req_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    tasks = data["tasks"]
    assert len(tasks) == 1
    t0 = tasks[0]

    # BUG-077 核心断言:created_at 必须存在且非 null
    assert "created_at" in t0, "tasks 子列表缺 created_at 字段(BUG-077)"
    assert t0["created_at"] is not None, "created_at 为 null(BUG-077)"
    # 值应与 DB 一致(ISO 串包含 T)
    assert "T" in t0["created_at"], f"created_at 非 ISO 格式: {t0['created_at']}"


@pytest.mark.asyncio
async def test_requirement_detail_tasks_include_display_status(
    client, auth_headers, db_session, registered_user,
):
    """R22.F3 波及面:tasks 子列表应含 display_status(前端状态徽章渲染依赖)"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "BUG-077 display_status")
    await _mk_task(db_session, project, registered_user["user_id"], req, "dev", "dev 任务", status="running")

    resp = await client.get(f"/api/requirements/{req.req_id}", headers=auth_headers)
    assert resp.status_code == 200
    tasks = resp.json()["data"]["tasks"]
    assert len(tasks) == 1
    # display_status 字段存在(值可以是 running/pending 等,此处不断言具体值)
    assert "display_status" in tasks[0], "tasks 子列表缺 display_status 字段"


@pytest.mark.asyncio
async def test_requirement_type_task_also_has_created_at(
    client, auth_headers, db_session, registered_user,
):
    """BUG-077 复现场景:requirement 类型任务(打磨任务)同样返回 created_at"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "BUG-077 打磨任务")
    # type='requirement' 即打磨任务(R3.F1 起=真实 Task 行)
    await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "打磨任务", status="running")

    resp = await client.get(f"/api/requirements/{req.req_id}", headers=auth_headers)
    assert resp.status_code == 200
    tasks = resp.json()["data"]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["type"] == "requirement"
    # BUG-077 核心:打磨任务也必须有 created_at
    assert "created_at" in tasks[0] and tasks[0]["created_at"] is not None
