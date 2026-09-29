"""
R63 BUG-063 display_status 派生字段(Red 测试)
===========================================
修复前:任务详情/列表 API 不返回 display_status,或返回的 task.status 无法区分
「容器启动中」vs「容器运行中」。本测试文件 5 例全部预期失败(Red)。

判定口径(参考 R3.F2.md / fix-analysis.md 第 33 轮):
  task.status != "running"       → display_status = task.status(透传)
  running + 无容器/creating      → "starting"
  running + container running    → "running"
  running + container failed     → "failed"
  running + 其他(destroyed 等)   → 兜底 "running"(不卡 starting)
"""
import uuid

import pytest
import sqlalchemy

from app.models.container import Container
from app.models.model_config import ModelConfig
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.models.user import User
from app.services.runner_service import runner_registry
from tests.test_projects_api import _seed_gitlab_settings


class FakeRunnerWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


async def _setup(db, user_id):
    """项目 + 在线 Runner + 模型配置"""
    await _seed_gitlab_settings(db)
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db.add(runner)
    project = Project(name="p63", slug=f"p63-{uuid.uuid4().hex[:6]}", owner_id=user_id)
    db.add(project)
    await db.flush()
    db.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/r63.git",
        gitlab_repo_id=630, gitlab_bind_type="manual",
        created_by=user_id,
    ))
    from app.core.encryption import encrypt_token
    db.add(ModelConfig(
        project_id=project.project_id, name="main",
        base_url="https://llm.example.com/v1",
        api_key_encrypted=encrypt_token("sk-x"),
        model="claude-sonnet-5", is_default=True, enabled=True,
        created_by=user_id,
    ))
    await db.flush()
    ws = FakeRunnerWS()
    conn = runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.63")
    return project, runner, conn, ws


async def _bind_gitlab_token(db, user_id):
    result = await db.execute(sqlalchemy.select(User).where(User.user_id == user_id))
    user = result.scalars().first()
    if user is not None:
        from app.core.encryption import encrypt_token
        user.gitlab_token_encrypted = encrypt_token("glpat-user")
        await db.flush()
    return user


async def _mk_requirement(db, project, creator_id, status="approved"):
    r = Requirement(
        req_id=str(uuid.uuid4()), title="r63", description="d",
        status=status, req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db.add(r)
    await db.flush()
    return r


def _mk_task(req, user_id, status, type_="requirement"):
    return Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=req.project_id,
        type=type_, title="t63", description="d", base_branch="b", work_branch="b",
        status=status, created_by=user_id,
    )


def _mk_container(task, status, runner):
    return Container(
        container_id=f"cid-{uuid.uuid4().hex[:8]}",
        task_id=task.task_id,
        project_id=task.project_id,
        runner_id=runner.runner_id,
        status=status,
    )


# ---------------------------------------------------------------------------
# 1. running + container creating → display_status == "starting"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_detail_running_container_creating_returns_starting(
    client, auth_headers, db_session, registered_user,
):
    project, runner, conn, ws = await _setup(db_session, registered_user["user_id"])
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = _mk_task(req, registered_user["user_id"], status="running")
    db_session.add(task)
    await db_session.flush()
    container = _mk_container(task, "creating", runner)
    db_session.add(container)
    await db_session.flush()

    resp = await client.get(f"/api/tasks/{task.task_id}", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0, data
    body = data["data"]
    # Red:字段不存在或值不为 "starting"
    assert "display_status" in body, f"display_status 字段缺失,实际 keys={list(body.keys())}"
    assert body["display_status"] == "starting", f"期望 starting,实际 {body.get('display_status')!r}"
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 2. running + container running → display_status == "running"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_detail_running_container_running_returns_running(
    client, auth_headers, db_session, registered_user,
):
    project, runner, conn, ws = await _setup(db_session, registered_user["user_id"])
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = _mk_task(req, registered_user["user_id"], status="running")
    db_session.add(task)
    await db_session.flush()
    container = _mk_container(task, "running", runner)
    db_session.add(container)
    await db_session.flush()

    resp = await client.get(f"/api/tasks/{task.task_id}", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0, data
    body = data["data"]
    assert "display_status" in body, f"display_status 字段缺失,实际 keys={list(body.keys())}"
    assert body["display_status"] == "running", f"期望 running,实际 {body.get('display_status')!r}"
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 3. running + container failed → display_status == "failed"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_detail_running_container_failed_returns_failed(
    client, auth_headers, db_session, registered_user,
):
    project, runner, conn, ws = await _setup(db_session, registered_user["user_id"])
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    task = _mk_task(req, registered_user["user_id"], status="running")
    db_session.add(task)
    await db_session.flush()
    container = _mk_container(task, "failed", runner)
    db_session.add(container)
    await db_session.flush()

    resp = await client.get(f"/api/tasks/{task.task_id}", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0, data
    body = data["data"]
    assert "display_status" in body, f"display_status 字段缺失,实际 keys={list(body.keys())}"
    assert body["display_status"] == "failed", f"期望 failed,实际 {body.get('display_status')!r}"
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 4. 列表接口(项目任务列表)每项含 display_status
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_task_list_items_include_display_status(
    client, auth_headers, db_session, registered_user,
):
    project, runner, conn, ws = await _setup(db_session, registered_user["user_id"])
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"])
    # 造 2 条任务:一条 running + creating,一条 done
    t1 = _mk_task(req, registered_user["user_id"], status="running")
    t2 = _mk_task(req, registered_user["user_id"], status="done")
    db_session.add_all([t1, t2])
    await db_session.flush()
    db_session.add(_mk_container(t1, "creating", runner))
    await db_session.flush()

    resp = await client.get(f"/api/projects/{project.project_id}/tasks", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0, data
    items = data["data"]["items"]
    assert len(items) >= 2, f"期望至少 2 条任务,实际 {len(items)}"
    for it in items:
        assert "display_status" in it, f"列表项缺 display_status,实际 keys={list(it.keys())}"
    # 校验值也符合派生逻辑
    by_id = {it["task_id"]: it for it in items}
    assert by_id[t1.task_id]["display_status"] == "starting"
    assert by_id[t2.task_id]["display_status"] == "done"
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 5a. 非 running 任务(done)透传原值
# 5b. running + destroyed 容器 → 兜底 "running"(不卡 starting)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_running_passthrough_and_destroyed_fallback(
    client, auth_headers, db_session, registered_user,
):
    project, runner, conn, ws = await _setup(db_session, registered_user["user_id"])
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"])

    # done 任务 → 透传 done
    t_done = _mk_task(req, registered_user["user_id"], status="done")
    db_session.add(t_done)
    # cancelled 任务 → 透传 cancelled
    t_cancel = _mk_task(req, registered_user["user_id"], status="cancelled")
    db_session.add(t_cancel)
    # running + destroyed 容器 → 兜底 running
    t_running_destroyed = _mk_task(req, registered_user["user_id"], status="running")
    db_session.add(t_running_destroyed)
    await db_session.flush()
    db_session.add(_mk_container(t_running_destroyed, "destroyed", runner))
    await db_session.flush()

    # done
    resp = await client.get(f"/api/tasks/{t_done.task_id}", headers=auth_headers)
    body = resp.json()["data"]
    assert "display_status" in body, f"display_status 字段缺失,实际 keys={list(body.keys())}"
    assert body["display_status"] == "done", f"期望 done,实际 {body.get('display_status')!r}"

    # cancelled
    resp = await client.get(f"/api/tasks/{t_cancel.task_id}", headers=auth_headers)
    body = resp.json()["data"]
    assert body["display_status"] == "cancelled", f"期望 cancelled,实际 {body.get('display_status')!r}"

    # running + destroyed → 兜底 running
    resp = await client.get(f"/api/tasks/{t_running_destroyed.task_id}", headers=auth_headers)
    body = resp.json()["data"]
    assert body["display_status"] == "running", f"期望 running,实际 {body.get('display_status')!r}"

    runner_registry.unregister(runner.runner_id)
