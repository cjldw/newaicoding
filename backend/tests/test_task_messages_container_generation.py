"""
R3.F5(BUG-076) container_generation 派生 — TDD Red 契约测试
====================================================
契约(DEVPLAN/R3.F5.md):

GET /tasks/{task_id}/messages 响应新增 container_generation(整数):
- 该 task 的容器启动代数:containers 表该 task_id 的行数(status 不限)
- 无容器行 → 0
- 同 task 建第 2 条容器行后 → generation=2

不测:前端判定逻辑(无 vitest 基建);前端以 sentGenerationRef 追踪,
由实现者自证(推演或抽纯函数)。
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.container import Container
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task, TaskMessage


# ---------------------------------------------------------------------------
# 造数助手
# ---------------------------------------------------------------------------
async def _mk_task(db_session, user_id):
    """创建项目 + 需求 + 任务,返回 task"""
    project = Project(
        name="CG项目", slug=f"cg-{uuid.uuid4().hex[:6]}",
        owner_id=user_id,
    )
    db_session.add(project)
    await db_session.flush()

    # 用户是项目 owner
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=user_id,
        role="owner", invited_by=user_id,
    ))
    await db_session.flush()

    req = Requirement(
        req_id=str(uuid.uuid4()), title="CG需求", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}", created_by=user_id,
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()

    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="requirement", title="CG任务", description="d",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status="running", conversation_id=str(uuid.uuid4()),
        created_by=user_id,
    )
    db_session.add(task)
    await db_session.flush()

    return task


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_messages_response_contains_container_generation(
    client, auth_headers, db_session, registered_user
):
    """① messages 响应含 container_generation(无容器行 → 0)"""
    task = await _mk_task(db_session, registered_user["user_id"])

    # 一条 assistant 消息(模拟历史)
    db_session.add(TaskMessage(
        message_id=str(uuid.uuid4()), task_id=task.task_id,
        role="assistant", content="AI reply",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/tasks/{task.task_id}/messages", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "container_generation" in data, "响应应含 container_generation 字段"
    assert data["container_generation"] == 0, "无容器行 → generation=0"


@pytest.mark.asyncio
async def test_container_generation_increments_with_container_rows(
    client, auth_headers, db_session, registered_user
):
    """② 同 task 建第 2 条容器行后 → generation=2"""
    task = await _mk_task(db_session, registered_user["user_id"])

    # 第 1 条容器行
    db_session.add(Container(
        container_id=f"c-{uuid.uuid4().hex[:6]}",
        task_id=task.task_id, runner_id="r1", project_id=task.project_id,
        status="running", exposed_ports=[5173, 8000],
    ))
    await db_session.commit()

    resp1 = await client.get(f"/api/tasks/{task.task_id}/messages", headers=auth_headers)
    data1 = resp1.json()["data"]
    assert data1["container_generation"] == 1, "1 条容器行 → generation=1"

    # 第 2 条容器行(模拟重启)
    db_session.add(Container(
        container_id=f"c-{uuid.uuid4().hex[:6]}",
        task_id=task.task_id, runner_id="r1", project_id=task.project_id,
        status="stopped", exposed_ports=[5173, 8000],
    ))
    await db_session.commit()

    resp2 = await client.get(f"/api/tasks/{task.task_id}/messages", headers=auth_headers)
    data2 = resp2.json()["data"]
    assert data2["container_generation"] == 2, "2 条容器行 → generation=2"


@pytest.mark.asyncio
async def test_container_generation_zero_when_no_container_rows(
    client, auth_headers, db_session, registered_user
):
    """③ 无容器行 → generation=0"""
    task = await _mk_task(db_session, registered_user["user_id"])
    await db_session.commit()

    resp = await client.get(f"/api/tasks/{task.task_id}/messages", headers=auth_headers)
    data = resp.json()["data"]
    assert data["container_generation"] == 0, "无容器行 → generation=0"
