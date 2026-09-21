"""
R4 任务统一执行单元测试(平台侧)
==========================
- 创建任务(成功/4001 需求状态/4002 未绑 token/4003 并发超限)
- 上传附件(成功/同名重命名)
- @file 引用解析(<100KB 注入内容/≥100KB 路径)+ 消息台账
- 停止任务(cancelled + 容器销毁指令)
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.core.security import create_access_token
from app.models.container import Container
from app.models.model_config import ModelConfig
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task, TaskMessage, TaskUploadedFile
from app.models.user import User
from app.services import file_service, runner_service, task_service
from app.services.runner_service import runner_registry
from tests.test_projects_api import _seed_gitlab_settings


class FakeRunnerWS:
    """Runner WebSocket 替身(记录下发消息)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


async def _setup(db_session, registered_user):
    """项目(main repo)+ 在线 Runner(DB + 内存连接)+ 模型配置;返回 (project, runner, conn, ws)"""
    await _seed_gitlab_settings(db_session)
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    project = Project(name="任务项目", slug=f"tk-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
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
    await db_session.flush()

    ws = FakeRunnerWS()
    conn = runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.8")
    return project, runner, conn, ws


async def _bind_gitlab_token(db_session, user_id):
    """会话内绑 token(ORM 对象直接改,后续查询/身份_map 一致)"""
    result = await db_session.execute(sqlalchemy.select(User).where(User.user_id == user_id))
    user = result.scalars().first()
    if user is not None:
        from app.core.encryption import encrypt_token

        user.gitlab_token_encrypted = encrypt_token("glpat-user")
        await db_session.flush()
    return user


async def _mk_requirement(db_session, project, creator_id, status="approved"):
    r = Requirement(
        req_id=str(uuid.uuid4()), title="登录功能", description="d",
        status=status, req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


@pytest.mark.asyncio
async def test_create_task_success(client, auth_headers, db_session, registered_user, monkeypatch):
    """创建任务成功:校验通过 → pending → 容器调度 running"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "实现登录", "description": "实现手机号登录"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == data["data"]["task_id"])
    )).scalars().first()
    assert task.status == "running"
    assert ws.sent and ws.sent[0]["type"] == "start_container"
    container = (await db_session.execute(
        sqlalchemy.select(Container).where(Container.task_id == task.task_id)
    )).scalars().first()
    assert container is not None
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_task_invalid_req_status(client, auth_headers, db_session, registered_user):
    """dev 任务要求需求 approved:4001"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "draft")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 4001
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_task_no_gitlab_token(client, auth_headers, db_session, registered_user):
    """未绑定 GitLab token:4002"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 4002
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_task_concurrent_limit(client, auth_headers, db_session, registered_user):
    """并发 running >3:4003"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    for _ in range(3):
        db_session.add(Task(
            req_id=req.req_id, project_id=project.project_id, type="dev",
            title="t", description="d", base_branch="b", work_branch="b",
            status="running", conversation_id=str(uuid.uuid4()),
            created_by=registered_user["user_id"],
        ))
    await db_session.flush()

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 4003
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_upload_file_success_and_rename(client, auth_headers, db_session, registered_user, monkeypatch):
    """上传成功 + 同名自动重命名 file-1.txt"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    writes: list = []

    async def fake_write_bytes(db, task_id_, path, content: bytes):
        writes.append((path, content))
        return {}

    monkeypatch.setattr(file_service, "task_write_file_bytes", fake_write_bytes)

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    task_id = resp.json()["data"]["task_id"]

    resp = await client.post(
        f"/api/tasks/{task_id}/files/upload",
        headers=auth_headers,
        files={"file": ("a.txt", b"hello attachment", "text/plain")},
    )
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["stored_filename"] == "a.txt"
    assert data["data"]["container_path"].startswith("/tmp/uploads/")

    resp = await client.post(
        f"/api/tasks/{task_id}/files/upload",
        headers=auth_headers,
        files={"file": ("a.txt", b"second", "text/plain")},
    )
    assert resp.json()["data"]["stored_filename"] == "a-1.txt"

    rows = (await db_session.execute(
        sqlalchemy.select(TaskUploadedFile).where(TaskUploadedFile.task_id == task_id)
    )).scalars().all()
    assert len(rows) == 2
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_send_message_with_file_ref(client, auth_headers, db_session, registered_user, monkeypatch):
    """@file 引用:<100KB 注入内容;≥100KB 只给路径;user+assistant 台账"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    async def fake_write_bytes(db, task_id_, path, content: bytes):
        return {}

    async def fake_read_bytes(db, task_id_, path):
        # @引用注入读取:small 返回内容,其余给大内容(走路径分支)
        return b"small content" if "small" in path else b"x" * (100 * 1024 + 10)

    monkeypatch.setattr(file_service, "task_write_file_bytes", fake_write_bytes)
    monkeypatch.setattr(file_service, "task_read_file_bytes", fake_read_bytes)

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    task_id = resp.json()["data"]["task_id"]

    # fake WS 无 container_started 回报:手动把容器置 running(模拟回报完成)
    container_row = (await db_session.execute(
        sqlalchemy.select(Container).where(Container.task_id == task_id)
    )).scalars().first()
    container_row.status = "running"
    await db_session.flush()

    small = b"small content"
    big = b"x" * (100 * 1024 + 10)
    for name, blob in (("small.txt", small), ("big.txt", big)):
        await client.post(
            f"/api/tasks/{task_id}/files/upload",
            headers=auth_headers,
            files={"file": (name, blob, "text/plain")},
        )

    captured: list = []

    async def fake_run_prompt(runner_conn, container_id, prompt, workdir="/workspace/main", timeout=600.0):
        captured.append(prompt)
        return {"result": "已处理", "tokens_in": 10, "tokens_out": 5}

    from app.services import claude_service

    monkeypatch.setattr(claude_service, "run_prompt", fake_run_prompt)

    resp = await client.post(
        f"/api/tasks/{task_id}/messages",
        headers=auth_headers,
        json={"content": "请看 @small.txt 和 @big.txt"},
    )
    assert resp.json()["code"] == 0, resp.json()
    prompt = captured[0]
    assert "small content" in prompt
    assert "Path:" in prompt and "/tmp/uploads/" in prompt

    msgs = (await db_session.execute(
        sqlalchemy.select(TaskMessage).where(TaskMessage.task_id == task_id)
    )).scalars().all()
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant"]
    refs = {r["filename"]: r["injected"] for r in msgs[0].file_refs}
    assert refs == {"small.txt": True, "big.txt": False}
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_stop_task_destroys_container(client, auth_headers, db_session, registered_user):
    """停止任务:cancelled + 销毁指令下发"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=None,
        runner_id=runner.runner_id, project_id=project.project_id,
        status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="t", description="d", base_branch="b", work_branch="b",
        status="running", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()
    container.task_id = task.task_id
    await db_session.flush()

    resp = await client.post(f"/api/tasks/{task.task_id}/stop", headers=auth_headers)
    assert resp.json()["code"] == 0
    await db_session.refresh(task)
    assert task.status == "cancelled"
    assert any(m["type"] == "stop_container" for m in ws.sent)
    runner_registry.unregister(runner.runner_id)
