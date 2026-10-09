"""
R8.F7(BUG-081):容器回报丢失自愈
====================================================
现场(2026-10-08,任务 4d0e3ce5):WS 断连致 container_started 回报丢失 → runner 重连
注册触发 handle_sync,按 container_id 比对 docker 清单,pending- 占位行永不匹配被误杀
→ 任务永卡「启动中」。修复 = 对账护栏(占位行不杀)+ 收养(按 R8.F5 task 标签提升)
+ started 回报复活语义(行被抢先置 destroyed 后迟到回报仍可承接)。
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.container import Container
from app.models.project import Project
from app.models.runner import Runner
from app.models.task import Task
from app.services import container_service, runner_service


async def _mk_runner(db) -> Runner:
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db.add(runner)
    await db.flush()
    return runner


async def _mk_task_with_project(db, registered_user) -> Task:
    project = Project(name="r8f7-p", slug=f"r8-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db.add(project)
    await db.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=str(uuid.uuid4()),
        project_id=project.project_id, type="requirement", title="t", description="d",
        base_branch="b", work_branch="b", status="running",
        created_by=registered_user["user_id"],
    )
    db.add(task)
    await db.flush()
    return task


def _mk_placeholder(task: Task, runner: Runner) -> Container:
    return Container(
        container_id=f"pending-{task.task_id}-{uuid.uuid4().hex[:8]}",
        task_id=task.task_id, runner_id=runner.runner_id,
        project_id=task.project_id, status="creating", exposed_ports=[],
    )


# ---------------------------------------------------------------------------
# 收养:pending 占位行 + sync 上报带 task_id → 提升真实容器
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_sync_adopts_placeholder_by_task(db_session, registered_user):
    runner = await _mk_runner(db_session)
    task = await _mk_task_with_project(db_session, registered_user)
    ph = _mk_placeholder(task, runner)
    db_session.add(ph)
    await db_session.flush()

    reported = [{
        "container_id": "abc123def456", "status": "running", "task_id": task.task_id,
        "ports": {"5173": 23413, "8000": 20701},
    }]
    await runner_service.handle_sync(db_session, runner, reported)
    await db_session.refresh(ph)

    assert ph.container_id == "abc123def456", "占位行应收养为真实 docker id"
    assert ph.status == "running"
    assert ph.destroyed_at is None
    assert ph.runner_host_port_5173 == 23413
    assert ph.runner_host_port_8000 == 20701


# ---------------------------------------------------------------------------
# 护栏:pending 占位行不在上报 → 不被误杀(BUG-081 直接现场)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_sync_never_destroys_pending_placeholder(db_session, registered_user):
    runner = await _mk_runner(db_session)
    task = await _mk_task_with_project(db_session, registered_user)
    ph = _mk_placeholder(task, runner)
    db_session.add(ph)
    await db_session.flush()

    # 上报里只有别的容器,没有该 task 的条目(回报仍丢失中)
    await runner_service.handle_sync(db_session, runner, [
        {"container_id": "other999", "status": "running"},
    ])
    await db_session.refresh(ph)

    assert ph.status == "creating", "占位行不得被对账置 destroyed(等待 started 回报)"
    assert ph.destroyed_at is None


# ---------------------------------------------------------------------------
# 回归:真实 id 行不在上报 → destroyed(原语义保留)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_sync_still_destroys_missing_real_container(db_session, registered_user):
    runner = await _mk_runner(db_session)
    task = await _mk_task_with_project(db_session, registered_user)
    real = Container(
        container_id="deadbeef1234", task_id=task.task_id, runner_id=runner.runner_id,
        project_id=task.project_id, status="running", exposed_ports=[],
    )
    db_session.add(real)
    await db_session.flush()

    await runner_service.handle_sync(db_session, runner, [])  # runner 上报空:容器真没了
    await db_session.refresh(real)

    assert real.status == "destroyed"
    assert real.destroyed_at is not None


# ---------------------------------------------------------------------------
# 复活:行已被对账置 destroyed 后,迟到的 container_started 回报仍可承接
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_container_started_resurrects_destroyed_placeholder(db_session, registered_user):
    runner = await _mk_runner(db_session)
    task = await _mk_task_with_project(db_session, registered_user)
    ph = _mk_placeholder(task, runner)
    db_session.add(ph)
    await db_session.flush()
    # 模拟 BUG-081 现场:对账已把占位行置 destroyed,迟到回报才到
    ph.status = "destroyed"
    from datetime import datetime

    ph.destroyed_at = datetime(2026, 10, 8, 21, 9, 52)
    await db_session.flush()

    await container_service.handle_container_started(
        db_session, task_id=task.task_id,
        docker_container_id="abc123def456", ports={"5173": 23413, "8000": 20701},
    )
    await db_session.refresh(ph)
    await db_session.refresh(task)

    assert ph.container_id == "abc123def456"
    assert ph.status == "running"
    assert ph.destroyed_at is None
    # BUG-030 任务行回填链路照常生效
    assert task.container_id == "abc123def456"
    assert task.runner_id == runner.runner_id


# ---------------------------------------------------------------------------
# 复活守卫:task 已有 running 行(新容器已接管)→ 迟到旧回报不得复活覆盖
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_container_started_no_resurrect_when_running_exists(db_session, registered_user):
    runner = await _mk_runner(db_session)
    task = await _mk_task_with_project(db_session, registered_user)
    ph = _mk_placeholder(task, runner)
    ph.status = "destroyed"
    db_session.add(ph)
    live = Container(
        container_id="live12345678", task_id=task.task_id, runner_id=runner.runner_id,
        project_id=task.project_id, status="running", exposed_ports=[],
    )
    db_session.add(live)
    await db_session.flush()

    await container_service.handle_container_started(
        db_session, task_id=task.task_id,
        docker_container_id="old999", ports={},
    )
    await db_session.refresh(ph)
    await db_session.refresh(live)

    assert ph.container_id.startswith("pending-"), "已有 running 行时不得复活旧占位行"
    assert live.container_id == "live12345678"
