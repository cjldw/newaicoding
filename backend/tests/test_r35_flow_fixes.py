"""
R35 流程断点修复包(平台侧)
==========================
F1 打磨可重启:polishing + 关联打磨 task 已终态 → start_polish 清空 polish_task_id 重建;
   active task 仍 3001;build_detail 透传 polish_task_status;draft 原路径回归
F2 取消需求收尾:polish_task 未终态 → finish_task(cancelled) + 容器销毁(stop_container
   下发实证);收尾失败不阻塞取消;task 已终态零副作用
F3 retry 拉起:failed/cancelled/timeout → pending → start_task 立即拉起(FakeRunner 收
   start_container);无 Runner 回 pending;非终态拒绝重试
F5 sweep_timeouts 挂调度:main.py lifespan 注册 _task_timeout_sweep,循环体调 sweep_timeouts
"""
import asyncio
import inspect
import uuid

import pytest
from sqlalchemy import select

from app.models.container import Container
from app.models.model_config import ModelConfig
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.models.user import User
from app.services import requirement_service, task_service
from app.services.runner_service import runner_registry
from tests.test_tasks_api import FakeRunnerWS, _seed_gitlab_settings


async def _mk_project(db, user_id):
    await _seed_gitlab_settings(db)
    project = Project(name="p", slug=f"pj-{uuid.uuid4().hex[:6]}", owner_id=user_id)
    db.add(project)
    await db.flush()
    return project


def _mk_req(project, user_id, status="polishing", polish_task_id=None):
    req = Requirement(
        req_id=str(uuid.uuid4()), project_id=project.project_id,
        title="需求", description="d", background="", acceptance_criteria="",
        status=status, priority="medium", req_branch="feat/x20260926",
        prd_file_path="", created_by=user_id, polish_task_id=polish_task_id,
    )
    return req


def _mk_task(req, user_id, status, type_="requirement"):
    return Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=req.project_id,
        type=type_, title="t", description="d", base_branch="b", work_branch="b",
        status=status, created_by=user_id,
    )


async def _get_user(db, user_id):
    """按 user_id 取 User。注意:user_id 非 PK(PK 是自增 id),db.get() 按 PK 查必 None"""
    return (await db.execute(
        select(User).where(User.user_id == user_id)
    )).scalars().first()


# ---------------------------------------------------------------------------
# F1:start_polish 前置放宽
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_polish_allows_repolish_when_task_terminal(db_session, registered_user, monkeypatch):
    """polishing + 打磨 task cancelled → 清空 polish_task_id 并走创建链路"""
    project = await _mk_project(db_session, registered_user["user_id"])
    old_task_id = str(uuid.uuid4())
    req = _mk_req(project, registered_user["user_id"], status="polishing", polish_task_id=old_task_id)
    db_session.add(req)
    old_task = _mk_task(req, registered_user["user_id"], status="cancelled")
    old_task.task_id = old_task_id
    db_session.add(old_task)
    await db_session.flush()

    captured = {}

    async def fake_create_polish(db, project_, requirement, operator):
        captured["called"] = True
        return str(uuid.uuid4())

    monkeypatch.setattr(task_service, "create_polish_task", fake_create_polish)
    # build_prd_path 依赖 task_id,真实函数可用
    operator = await _get_user(db_session, registered_user["user_id"])
    new_id = await requirement_service.start_polish(db_session, project, operator, req)
    assert captured.get("called") is True
    assert req.polish_task_id == new_id
    assert req.status == "polishing"


@pytest.mark.asyncio
async def test_start_polish_rejects_when_task_active(db_session, registered_user):
    """polishing + 打磨 task running → 3001 维持"""
    from app.core.response import BizError

    project = await _mk_project(db_session, registered_user["user_id"])
    old_task_id = str(uuid.uuid4())
    req = _mk_req(project, registered_user["user_id"], status="polishing", polish_task_id=old_task_id)
    db_session.add(req)
    old_task = _mk_task(req, registered_user["user_id"], status="running")
    old_task.task_id = old_task_id
    db_session.add(old_task)
    await db_session.flush()

    operator = await _get_user(db_session, registered_user["user_id"])
    with pytest.raises(BizError) as ei:
        await requirement_service.start_polish(db_session, project, operator, req)
    assert ei.value.code == 3001


@pytest.mark.asyncio
async def test_build_detail_includes_polish_task_status(db_session, registered_user):
    """build_detail 透传 polish_task_status(前端免二次请求)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="polishing")
    task = _mk_task(req, registered_user["user_id"], status="cancelled")
    req.polish_task_id = task.task_id
    db_session.add(req)
    db_session.add(task)
    await db_session.flush()
    await db_session.refresh(req)  # 加载 server-default(created_at),防空属性同步懒加载炸 greenlet

    detail = await requirement_service.build_detail(db_session, req)
    assert detail["polish_task_id"] == task.task_id
    assert detail["polish_task_status"] == "cancelled"

@pytest.mark.asyncio
async def test_start_polish_draft_path_unchanged(db_session, registered_user, monkeypatch):
    """F1 回归:draft 原路径不变(无 polish_task_id → 正常创建打磨任务)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="draft")
    db_session.add(req)
    await db_session.flush()

    captured = {}

    async def fake_create_polish(db, project_, requirement, operator):
        captured["called"] = True
        return str(uuid.uuid4())

    monkeypatch.setattr(task_service, "create_polish_task", fake_create_polish)
    operator = await _get_user(db_session, registered_user["user_id"])
    new_id = await requirement_service.start_polish(db_session, project, operator, req)
    assert captured.get("called") is True
    assert req.polish_task_id == new_id
    assert req.status == "polishing"


# ---------------------------------------------------------------------------
# F2:取消需求收尾孤儿容器
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_requirement_stops_polish_task(db_session, registered_user, monkeypatch):
    """取消需求:打磨 task running → finish_task(cancelled) 被调(容器链复用)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="polishing")
    task = _mk_task(req, registered_user["user_id"], status="running")
    req.polish_task_id = task.task_id
    db_session.add(req)
    db_session.add(task)
    await db_session.flush()

    called = {}

    async def fake_finish(db, task_, operator_, status="done"):
        called["status"] = status
        task_.status = status

    monkeypatch.setattr(task_service, "finish_task", fake_finish)
    operator = await _get_user(db_session, registered_user["user_id"])
    await requirement_service.cancel_requirement(db_session, operator, req, reason="不要了")
    assert called.get("status") == "cancelled"
    assert req.status == "rejected"


@pytest.mark.asyncio
async def test_cancel_requirement_skips_terminal_task(db_session, registered_user, monkeypatch):
    """打磨 task 已终态 → 不调 finish_task,取消照常"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="polishing")
    task = _mk_task(req, registered_user["user_id"], status="cancelled")
    req.polish_task_id = task.task_id
    db_session.add(req)
    db_session.add(task)
    await db_session.flush()

    called = {"n": 0}

    async def fake_finish(db, task_, operator_, status="done"):
        called["n"] += 1

    monkeypatch.setattr(task_service, "finish_task", fake_finish)
    operator = await _get_user(db_session, registered_user["user_id"])
    await requirement_service.cancel_requirement(db_session, operator, req, reason="r")
    assert called["n"] == 0
    assert req.status == "rejected"


@pytest.mark.asyncio
async def test_cancel_requirement_survives_finish_failure(db_session, registered_user, monkeypatch):
    """收尾失败(stop 下发炸)不阻塞需求取消,需求照常 rejected(留 warning)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="polishing")
    task = _mk_task(req, registered_user["user_id"], status="running")
    req.polish_task_id = task.task_id
    db_session.add(req)
    db_session.add(task)
    await db_session.flush()

    async def fake_finish(db, task_, operator_, status="done"):
        raise RuntimeError("stop 指令下发失败")

    monkeypatch.setattr(task_service, "finish_task", fake_finish)
    operator = await _get_user(db_session, registered_user["user_id"])
    await requirement_service.cancel_requirement(db_session, operator, req, reason="r")
    assert req.status == "rejected"
    assert task.status == "running"  # 收尾失败:task 状态未被伪 finish 改动


@pytest.mark.asyncio
async def test_cancel_requirement_sends_stop_container(db_session, registered_user):
    """取消需求端到端:真 finish_task 链 → Runner 收 stop_container(孤儿容器销毁实证)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    req = _mk_req(project, registered_user["user_id"], status="polishing")
    task = _mk_task(req, registered_user["user_id"], status="running")
    req.polish_task_id = task.task_id
    db_session.add(req)
    db_session.add(task)
    await db_session.flush()
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        runner_id=runner.runner_id, project_id=project.project_id,
        task_id=task.task_id, status="running", exposed_ports=[5173, 8000],
    )
    db_session.add(container)
    await db_session.flush()

    ws = FakeRunnerWS()
    runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.8")
    try:
        operator = await _get_user(db_session, registered_user["user_id"])
        await requirement_service.cancel_requirement(db_session, operator, req, reason="不要了")
        assert req.status == "rejected"
        assert task.status == "cancelled"
        assert task.finished_at is not None
        stops = [m for m in ws.sent if m["type"] == "stop_container"]
        assert stops, f"未下发 stop_container,下发消息:{[m['type'] for m in ws.sent]}"
        assert stops[0]["container_id"] == container.container_id
    finally:
        runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# F3:retry 拉起
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_task_dispatches_start_task(db_session, registered_user, monkeypatch):
    """failed → pending → start_task 被调(立即拉起)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="approved")
    db_session.add(req)
    task = _mk_task(req, registered_user["user_id"], status="failed", type_="dev")
    db_session.add(task)
    await db_session.flush()

    called = {}

    async def fake_start(db, task_, project_, requirement_):
        called["task_id"] = task_.task_id
        task_.status = "running"

    monkeypatch.setattr(task_service, "start_task", fake_start)
    await task_service.retry_task(db_session, task)
    assert called.get("task_id") == task.task_id
    assert task.status == "running"


@pytest.mark.asyncio
async def test_retry_task_no_runner_stays_pending(db_session, registered_user, monkeypatch):
    """无可用 Runner(8003)→ 回 pending 排队,不炸"""
    from app.core.response import BizError, ErrCode

    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="approved")
    db_session.add(req)
    task = _mk_task(req, registered_user["user_id"], status="cancelled", type_="dev")
    db_session.add(task)
    await db_session.flush()

    async def fake_start(db, task_, project_, requirement_):
        raise BizError(ErrCode.NO_RUNNER_AVAILABLE, "无可用 Runner")

    monkeypatch.setattr(task_service, "start_task", fake_start)
    await task_service.retry_task(db_session, task)
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_retry_failed_task_starts_container(db_session, registered_user):
    """端到端:failed dev 任务 retry → 真 start_task 链 → FakeRunner 收 start_container,
    status 推进 pending → running(F3 验证逻辑核心断言)"""
    project = await _mk_project(db_session, registered_user["user_id"])
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    await db_session.flush()
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=311, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    from app.core.encryption import encrypt_token

    db_session.add(ModelConfig(
        project_id=project.project_id, name="main",
        base_url="https://llm.example.com/v1",
        api_key_encrypted=encrypt_token("sk-x"),
        model="claude-sonnet-5", is_default=True, enabled=True,
        created_by=registered_user["user_id"],
    ))
    req = _mk_req(project, registered_user["user_id"], status="approved")
    db_session.add(req)
    await db_session.flush()
    task = _mk_task(req, registered_user["user_id"], status="failed", type_="dev")
    db_session.add(task)
    await db_session.flush()

    ws = FakeRunnerWS()
    runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.8")
    try:
        await task_service.retry_task(db_session, task)
        assert task.status == "running"
        assert ws.sent and ws.sent[0]["type"] == "start_container"
        container = (await db_session.execute(
            select(Container).where(Container.task_id == task.task_id)
        )).scalars().first()
        assert container is not None
    finally:
        runner_registry.unregister(runner.runner_id)


@pytest.mark.parametrize("st", ["running", "pending", "done"])
@pytest.mark.asyncio
async def test_retry_rejects_non_terminal_status(db_session, registered_user, st):
    """非终态(running/pending/done)重试 → 拒绝且状态不变(重试只面向三终态)"""
    from app.core.response import BizError, ErrCode

    project = await _mk_project(db_session, registered_user["user_id"])
    req = _mk_req(project, registered_user["user_id"], status="approved")
    db_session.add(req)
    task = _mk_task(req, registered_user["user_id"], status=st, type_="dev")
    db_session.add(task)
    await db_session.flush()

    with pytest.raises(BizError) as ei:
        await task_service.retry_task(db_session, task)
    assert ei.value.code == ErrCode.TASK_REQ_STATUS_INVALID
    assert task.status == st


# ---------------------------------------------------------------------------
# F5:sweep_timeouts 挂调度(main.py lifespan)
# ---------------------------------------------------------------------------
def test_task_timeout_sweep_registered_in_lifespan():
    """调度注册断言:lifespan create_task 挂 _task_timeout_sweep,关闭时 cancel;
    循环体调 task_service.sweep_timeouts,60s 一轮(R16 同模式)"""
    import app.main as app_main

    life_src = inspect.getsource(app_main.lifespan)
    assert "_task_timeout_sweep" in life_src, "lifespan 未注册任务超时巡检"
    assert "create_task" in life_src
    assert "task_timeout_task.cancel" in life_src, "lifespan 关闭未回收超时巡检 task"

    loop_src = inspect.getsource(app_main._task_timeout_sweep)
    assert "sweep_timeouts" in loop_src, "巡检循环未调用 task_service.sweep_timeouts"
    assert "sleep(60)" in loop_src, "巡检未按 60s 间隔轮询"


@pytest.mark.asyncio
async def test_task_timeout_sweep_loop_invokes_sweep_timeouts(monkeypatch):
    """功能接线:巡检循环真实调用 task_service.sweep_timeouts(压平 60s 等待)"""
    import app.main as app_main

    calls = {"n": 0}

    async def fake_sleep(seconds):
        return None

    async def fake_sweep(db):
        calls["n"] += 1
        raise asyncio.CancelledError()  # 首轮即退出循环

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(task_service, "sweep_timeouts", fake_sweep)
    await asyncio.wait_for(app_main._task_timeout_sweep(), timeout=5)
    assert calls["n"] == 1
