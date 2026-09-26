"""
R8.F5(BUG-055)对账收养 - TDD 测试
=====================================
场景:container_started 回报丢失(WS 抖动/断连)后,runner 重注册对账时
DB 行仍是 pending 占位 id。修复前:只按 container_id 匹配 → 活容器被判
destroyed、真容器沦为 docker 孤儿。修复后:按 task 标签收养。
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.container import Container
from app.models.runner import Runner
from app.services import runner_service


async def _make_runner(db_session):
    runner = Runner(
        runner_id=str(uuid.uuid4()),
        name=f"r8f5-{uuid.uuid4().hex[:6]}",
        role="worker",
        token_hash="x",
        status="online",
        max_containers=5,
        created_by="test",
    )
    db_session.add(runner)
    await db_session.flush()
    return runner


async def _make_project(db_session):
    """containers.project_id NOT NULL,需真项目行(owner 无 FK,惯例传字符串)"""
    from app.models.project import Project

    project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id="test")
    db_session.add(project)
    await db_session.flush()
    return project


async def _make_container(db_session, runner, task_id, container_id, status="creating"):
    project = await _make_project(db_session)
    c = Container(
        container_id=container_id,
        runner_id=runner.runner_id,
        project_id=project.project_id,
        task_id=task_id,
        status=status,
        exposed_ports=[],
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_sync_adopts_pending_row_by_task_id(db_session):
    """核心判据:creating 占位行按 task 标签收养(真实 id 替换 + 置上报状态),不判毁"""
    runner = await _make_runner(db_session)
    task_id = str(uuid.uuid4())
    pending = await _make_container(db_session, runner, task_id, f"pending-{task_id}-x")

    await runner_service.handle_sync(db_session, runner, [
        {"container_id": "cf6b123abc", "status": "running", "task_id": task_id},
    ])
    await db_session.refresh(pending)
    # 收养:真实 id 落库、状态以上报为准、不再 destroyed
    assert pending.container_id == "cf6b123abc"
    assert pending.status == "running"
    assert pending.destroyed_at is None
    # 收养行计入负载
    assert runner.current_containers == 1


@pytest.mark.asyncio
async def test_sync_id_dupe_suffix(db_session):
    """真实 id 已被占用(UNIQUE)→ 追加行号后缀,仍完成收养"""
    runner = await _make_runner(db_session)
    task_id = str(uuid.uuid4())
    pending = await _make_container(db_session, runner, task_id, f"pending-{task_id}-x")
    # 抢占真实 id 的另一行(非同 runner,不进对账集)
    other_project = await _make_project(db_session)
    other = Container(
        container_id="cf6b123abc", runner_id=str(uuid.uuid4()),
        project_id=other_project.project_id, task_id=str(uuid.uuid4()),
        status="running", exposed_ports=[],
    )
    db_session.add(other)
    await db_session.flush()

    await runner_service.handle_sync(db_session, runner, [
        {"container_id": "cf6b123abc", "status": "running", "task_id": task_id},
    ])
    await db_session.refresh(pending)
    assert pending.container_id == f"cf6b123abc-{pending.id}"
    assert pending.status == "running"


@pytest.mark.asyncio
async def test_sync_genuinely_gone_still_destroyed(db_session):
    """回归:真消失(id+task 双失配)仍判毁——修复不放宽破坏性"""
    runner = await _make_runner(db_session)
    task_id = str(uuid.uuid4())
    gone = await _make_container(db_session, runner, task_id, f"pending-{task_id}-x")

    await runner_service.handle_sync(db_session, runner, [
        {"container_id": "other-xyz", "status": "running", "task_id": str(uuid.uuid4())},
    ])
    await db_session.refresh(gone)
    assert gone.status == "destroyed"
    assert gone.destroyed_at is not None
    assert runner.current_containers == 0


@pytest.mark.asyncio
async def test_sync_legacy_report_without_task_id_unchanged(db_session):
    """旧版 runner 上报(无 task_id 字段)行为不变:未知忽略、失配判毁"""
    runner = await _make_runner(db_session)
    task_id = str(uuid.uuid4())
    pending = await _make_container(db_session, runner, task_id, f"pending-{task_id}-x")

    await runner_service.handle_sync(db_session, runner, [
        {"container_id": "docker-keep", "status": "running"},
    ])
    await db_session.refresh(pending)
    assert pending.status == "destroyed"
    assert runner.current_containers == 0
