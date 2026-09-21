"""
R6 测试任务测试
==========================
- 创建测试任务(dev done 前置 4001;test 仓库缺失提示;report 路径 Q26)
- 确认用例(cases_review → running;用例台账)
- 接受失败(豁免 → passed)
- 驳回回开发回环(rejected_to_dev_task_id 记录)
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services.runner_service import runner_registry
from tests.test_tasks_api import FakeRunnerWS, _bind_gitlab_token


async def _setup(db_session, registered_user, with_test_repo=True):
    from app.core.encryption import encrypt_token
    from app.models.model_config import ModelConfig
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    project = Project(name="测项", slug=f"ts-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=411, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    if with_test_repo:
        db_session.add(ProjectRepo(
            project_id=project.project_id, role="test",
            gitlab_repo_url="https://gitlab.example.com/g/tests.git",
            gitlab_repo_id=412, gitlab_bind_type="manual",
            created_by=registered_user["user_id"],
        ))
    db_session.add(ModelConfig(
        project_id=project.project_id, name="main",
        base_url="https://llm.example.com/v1",
        api_key_encrypted=encrypt_token("sk-x"),
        model="claude-sonnet-5", is_default=True, enabled=True,
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()
    ws = FakeRunnerWS()
    runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.8")
    return project, runner, ws


async def _mk_req(db_session, project, creator_id):
    r = Requirement(
        req_id=str(uuid.uuid4()), title="下单流程", description="d",
        status="approved", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_dev_done(db_session, project, req, creator_id):
    t = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="开发", description="d",
        base_branch=req.req_branch, work_branch=req.req_branch,
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=creator_id,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_create_test_task_success(client, auth_headers, db_session, registered_user):
    """创建测试任务成功:report_file_path(Q26)+ test_repo_ids;dev done 前置"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_req(db_session, project, registered_user["user_id"])

    # 无 dev done → 4001
    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "test", "title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 4001

    await _mk_dev_done(db_session, project, req, registered_user["user_id"])
    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "test", "title": "登录测试", "description": "d"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == data["data"]["task_id"])
    )).scalars().first()
    assert task.type == "test"
    ext = task.extended_attributes
    assert ext["report_file_path"].startswith("docs/")
    assert ext["report_file_path"].endswith("/report.md")
    assert len(ext["test_repo_ids"]) == 1
    assert ext["based_on_dev_tasks"] == []
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_confirm_cases_success(client, auth_headers, db_session, registered_user):
    """确认用例:cases_review → running;用例台账写入"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_req(db_session, project, registered_user["user_id"])
    await _mk_dev_done(db_session, project, req, registered_user["user_id"])

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "test", "title": "t", "description": "d"},
    )
    task_id = resp.json()["data"]["task_id"]

    cases = [
        {"id": "1", "title": "测试登录", "steps": "输入正确密码", "expected": "登录成功", "status": "pending"},
        {"id": "2", "title": "错误密码提示", "steps": "输入错误密码", "expected": "提示错误", "status": "pending"},
    ]
    resp = await client.post(
        f"/api/tasks/{task_id}/confirm-cases",
        headers=auth_headers,
        json={"test_cases": cases},
    )
    assert resp.json()["code"] == 0
    assert "开始执行" in resp.json()["message"]

    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == task_id)
    )).scalars().first()
    assert task.status == "running"
    assert len(task.extended_attributes["test_cases"]) == 2
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_accept_failure_success(client, auth_headers, db_session, registered_user):
    """接受失败(豁免):passed + 豁免标记"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_req(db_session, project, registered_user["user_id"])
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="test", title="t", description="d", base_branch="b", work_branch="b",
        status="failed", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
        extended_attributes={"test_cases": [{"id": "1", "title": "c", "status": "failed"}]},
    )
    db_session.add(task)
    await db_session.flush()

    resp = await client.post(
        f"/api/tasks/{task.task_id}/accept-failure",
        headers=auth_headers,
        json={"reason": "环境问题,非代码缺陷"},
    )
    assert resp.json()["code"] == 0
    await db_session.refresh(task)
    assert task.status == "passed"
    assert task.extended_attributes["exempt_failure"]["reason"] == "环境问题,非代码缺陷"


@pytest.mark.asyncio
async def test_reject_roundtrip_records_dev_task(client, auth_headers, db_session, registered_user):
    """驳回回开发回环:原测试任务记录 rejected_to_dev_task_id"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_req(db_session, project, registered_user["user_id"])
    test_task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="test", title="t", description="d", base_branch="b", work_branch="b",
        status="failed", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
        extended_attributes={"test_cases": [{"id": "1", "title": "c", "status": "failed"}],
                             "report_file_path": "docs/x/report.md"},
    )
    db_session.add(test_task)
    await db_session.flush()

    resp = await client.post(
        f"/api/tasks/{test_task.task_id}/reject-to-dev",
        headers=auth_headers,
        json={"title": "修复", "description": "d"},
    )
    assert resp.json()["code"] == 0
    dev_id = resp.json()["data"]["task_id"]
    await db_session.refresh(test_task)
    assert test_task.extended_attributes["rejected_to_dev_task_id"] == dev_id
    runner_registry.unregister(runner.runner_id)
