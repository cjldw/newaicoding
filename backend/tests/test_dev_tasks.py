"""
R5 开发任务测试
==========================
- 创建 dev 任务成功(R4 通用通道,需求 approved 前置)
- 测试驳回回开发:fix_context 组装(失败用例+报告路径)+ 首条消息 prompt 注入
"""
import uuid

import pytest
import sqlalchemy

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services.runner_service import runner_registry
from tests.test_tasks_api import (
    FakeRunnerWS, _bind_gitlab_token, _mk_requirement, _setup,
)


async def _mk_test_task(db_session, project, req, creator_id, test_cases, report_path):
    t = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="test", title="登录测试", description="d",
        base_branch=req.req_branch, work_branch=req.req_branch,
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=creator_id,
        extended_attributes={
            "test_cases": test_cases,
            "report_file_path": report_path,
        },
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_create_dev_task_success(client, auth_headers, db_session, registered_user):
    """创建 dev 任务成功(R4 通用通道;dev 前置 approved)"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "实现登录", "description": "实现手机号登录"},
    )
    assert resp.json()["code"] == 0
    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == resp.json()["data"]["task_id"])
    )).scalars().first()
    assert task is not None and task.type == "dev"
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_reject_to_dev_success(client, auth_headers, db_session, registered_user, monkeypatch):
    """测试驳回回开发:fix_context 正确;首条消息 prompt 携带修复上下文"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    test_task = await _mk_test_task(
        db_session, project, req, registered_user["user_id"],
        test_cases=[
            {"name": "用例1: 正确密码登录", "result": "failed"},
            {"name": "用例2: 错误密码提示", "result": "failed"},
        ],
        report_path="docs/20260922_登录测试_a1b2c3d4/report.md",
    )

    resp = await client.post(
        f"/api/tasks/{test_task.task_id}/reject-to-dev",
        headers=auth_headers,
        json={"title": "修复登录失败用例", "description": "按报告修复"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    dev_task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == data["data"]["task_id"])
    )).scalars().first()
    assert dev_task.type == "dev"
    ext = dev_task.extended_attributes
    assert ext["related_test_task_id"] == test_task.task_id
    assert "失败用例:" in ext["fix_context"]
    assert "用例1: 正确密码登录" in ext["fix_context"]
    assert "docs/20260922_登录测试_a1b2c3d4/report.md" in ext["fix_context"]

    # 首条消息 prompt 自动携带 fix_context
    from app.services import claude_service

    captured: list = []

    async def fake_run_prompt(runner_conn, container_id, prompt, workdir="/workspace/main", timeout=600.0):
        captured.append(prompt)
        return {"result": "ok", "tokens_in": 1, "tokens_out": 1}

    monkeypatch.setattr(claude_service, "run_prompt", fake_run_prompt)

    # fake WS 无回报:容器手动置 running(send_message 前置)
    container_row = (await db_session.execute(
        sqlalchemy.select(Container).where(Container.task_id == dev_task.task_id)
    )).scalars().first()
    container_row.status = "running"
    await db_session.flush()

    resp = await client.post(
        f"/api/tasks/{dev_task.task_id}/messages",
        headers=auth_headers,
        json={"content": "开始修复"},
    )
    assert resp.json()["code"] == 0, resp.json()
    assert "【修复上下文】" in captured[0]
    assert "开始修复" in captured[0]

    # 第二条消息不再注入
    captured.clear()
    await client.post(
        f"/api/tasks/{dev_task.task_id}/messages",
        headers=auth_headers,
        json={"content": "继续"},
    )
    assert "【修复上下文】" not in captured[0]
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_reject_to_dev_rejects_non_test_task(client, auth_headers, db_session, registered_user):
    """非 test 任务驳回回开发:4001"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")
    dev = await _mk_requirement(db_session, project, registered_user["user_id"])
    dev_task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="t", description="d", base_branch="b", work_branch="b",
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(dev_task)
    await db_session.flush()

    resp = await client.post(
        f"/api/tasks/{dev_task.task_id}/reject-to-dev",
        headers=auth_headers,
        json={"title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 4001
    runner_registry.unregister(runner.runner_id)
