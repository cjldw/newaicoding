"""
R37.F10(BUG-085)PRD 防丢兜底测试
================================
丢失窗口:打磨中容器超时/异常销毁(未走「打磨完成」),PRD.md 只存容器内
→ 随容器一起没了(实锤:超时清扫 sweep_timeouts 销毁前无回传)。

修复契约:
- sweep_timeouts:requirement 型任务销毁容器**前**先回传 PRD(await 内联,
  先同步后销毁);非 requirement 不触发
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services import container_service, task_service


async def _insert_runner(db_session, name="r-f10"):
    r = Runner(
        name=name, role="worker", token_hash="placeholder-hash", status="online",
        current_containers=0, max_containers=10, created_by="test",
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_timeout_task(db_session, registered_user, task_type="requirement"):
    """构建 running 超 60 分钟的任务 + 一条 running 容器"""
    runner = await _insert_runner(db_session)
    project = Project(
        name=f"p-f10-{uuid.uuid4().hex[:6]}",
        slug=f"f10-{uuid.uuid4().hex[:8]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()

    req = Requirement(
        project_id=project.project_id,
        title=f"req-f10-{uuid.uuid4().hex[:6]}",
        description="t", status="polishing",
        req_branch=f"req-{uuid.uuid4().hex[:6]}",
        created_by=registered_user["user_id"],
    )
    db_session.add(req)
    await db_session.flush()

    task = Task(
        req_id=req.req_id, project_id=project.project_id, type=task_type,
        title=f"timeout-f10-{uuid.uuid4().hex[:6]}", description="t",
        base_branch="master", work_branch="feat/f10", status="running",
        created_by=registered_user["user_id"],
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=61),
    )
    db_session.add(task)
    await db_session.flush()

    db_session.add(Container(
        container_id=f"docker-f10-{uuid.uuid4().hex[:8]}",
        task_id=task.task_id, runner_id=runner.runner_id,
        project_id=project.project_id, status="running",
        image="platform/devbox:v2", exposed_ports=[5173, 8000],
    ))
    await db_session.flush()
    return task


@pytest.mark.asyncio
async def test_sweep_syncs_prd_before_stop_for_requirement(db_session, monkeypatch, registered_user):
    """requirement 超时任务:先回传 PRD 再销毁容器(顺序实锤)"""
    task = await _mk_timeout_task(db_session, registered_user, task_type="requirement")

    events: list[tuple] = []

    async def fake_sync_bg(task_id):
        events.append(("sync", task_id))

    async def fake_request_stop(db, c):
        events.append(("stop", c.container_id))

    monkeypatch.setattr("app.services.requirement_service._sync_prd_background", fake_sync_bg)
    monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

    count = await task_service.sweep_timeouts(db_session)

    assert count == 1
    assert task.status == "timeout"
    kinds = [e[0] for e in events]
    assert "sync" in kinds, "销毁前应回传 PRD(BUG-085:超时即丢的窗口)"
    assert kinds.index("sync") < kinds.index("stop"), "回传必须先于容器销毁"


@pytest.mark.asyncio
async def test_sweep_skips_prd_sync_for_non_requirement(db_session, monkeypatch, registered_user):
    """非 requirement(dev)超时任务:不触发 PRD 回传"""
    task = await _mk_timeout_task(db_session, registered_user, task_type="dev")

    synced: list[str] = []

    async def fake_sync_bg(task_id):
        synced.append(task_id)

    async def fake_request_stop(db, c):
        pass

    monkeypatch.setattr("app.services.requirement_service._sync_prd_background", fake_sync_bg)
    monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

    count = await task_service.sweep_timeouts(db_session)

    assert count == 1
    assert task.status == "timeout"
    assert synced == [], "dev 任务不应触发 PRD 回传"
