"""
R7 发布任务测试
==========================
- 创建发布任务(成功[默认域名 Q28]/端口冲突 7001/部署数超限 7002/host 非法或冲突 7003/test passed 前置 4001)
- run_release(merge/deploy fake;路由注册;需求 done 推进)
- 下线(路由摘除)
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.route import Route
from app.models.runner import Runner
from app.models.task import Task
from app.services import route_service, task_service
from app.services.runner_service import runner_registry
from tests.test_tasks_api import FakeRunnerWS, _bind_gitlab_token, _mk_requirement


async def _setup(db_session, registered_user):
    from app.core.encryption import encrypt_token
    from app.models.model_config import ModelConfig
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="deploy",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    project = Project(name="发布项目", slug=f"rel-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=511, gitlab_bind_type="manual",
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
    runner_registry.register(runner.runner_id, "deploy", ws, "10.0.0.9")
    return project, runner, ws


async def _mk_env(db_session, project, creator_id):
    req = Requirement(
        req_id=str(uuid.uuid4()), title="下单流程重构", description="d",
        status="approved", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    passed = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="test", title="测试", description="d",
        base_branch=req.req_branch, work_branch=req.req_branch,
        status="passed", conversation_id=str(uuid.uuid4()),
        created_by=creator_id,
    )
    db_session.add(passed)
    await db_session.flush()
    return req


async def _create_release(client, auth_headers, req, port=10080, host=None, title="发布 v1"):
    payload = {"type": "release", "title": title, "description": "d", "deploy_port": port}
    if host:
        payload["deploy_host"] = host
    return await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json=payload,
    )


@pytest.mark.asyncio
async def test_create_release_task_success(client, auth_headers, db_session, registered_user, monkeypatch):
    """创建发布任务成功:默认域名拼接(Q28)+ deploy Runner + deploying"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_env(db_session, project, registered_user["user_id"])

    # run_release 内部经 Runner 请求-响应,全部 fake 成功
    from app.services import runner_service

    async def fake_request(c, message, timeout=15.0):
        return {"ok": True, "data": {}}

    monkeypatch.setattr(runner_service, "request_runner", fake_request)

    resp = await _create_release(client, auth_headers, req)
    data = resp.json()
    assert data["code"] == 0, data
    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == data["data"]["task_id"])
    )).scalars().first()
    assert task.status == "done"  # fake 全成功 → done(发布完成)
    ext = task.extended_attributes
    assert ext["deploy_host"] == f"{project.slug}.coding-console.zhanqitv.com.cn"  # Q28 默认域名
    assert ext["deploy_phase"] == "deployed"

    # 网关路由已注册(host 含端口,公开)
    route = (await db_session.execute(
        sqlalchemy.select(Route).where(Route.type == "deploy")
    )).scalars().first()
    assert route is not None
    assert route.auth_required is False
    assert route.host == f"{ext['deploy_host']}:10080"

    # 需求推进 done(全部发布完成)
    await db_session.refresh(req)
    assert req.status == "done"
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_release_task_port_conflict(client, auth_headers, db_session, registered_user):
    """deploy_port 全平台唯一:冲突拒绝 7001"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_env(db_session, project, registered_user["user_id"])

    # 平台上已存在同端口的 release 任务(直接插 extended_attributes)
    other_project = Project(name="o", slug=f"o-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(other_project)
    await db_session.flush()
    db_session.add(Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=other_project.project_id,
        type="release", title="o", description="d", base_branch="m", work_branch="m",
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
        extended_attributes={"deploy_port": 10080, "deploy_host": "other.example.com",
                             "deploy_phase": "deployed"},
    ))
    await db_session.flush()

    resp = await _create_release(client, auth_headers, req, port=10080, host="free.example.com")
    assert resp.json()["code"] == 7001
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_release_task_limit_exceeded(client, auth_headers, db_session, registered_user):
    """同时部署数 >5:7002"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_env(db_session, project, registered_user["user_id"])

    for i in range(5):
        db_session.add(Task(
            task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
            type="release", title=f"r{i}", description="d", base_branch="m", work_branch="m",
            status="running", conversation_id=str(uuid.uuid4()),
            created_by=registered_user["user_id"],
            extended_attributes={"deploy_phase": "deployed", "deploy_port": 10000 + i,
                                 "deploy_host": f"h{i}.example.com"},
        ))
    await db_session.flush()

    resp = await _create_release(client, auth_headers, req, port=10099, host="new.example.com")
    assert resp.json()["code"] == 7002
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_create_release_task_host_invalid_and_conflict(client, auth_headers, db_session, registered_user, monkeypatch):
    """deploy_host 非法格式/重复:7003"""
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    # 前置:需求下至少一个 test 任务 passed(4001 先于 7003)
    db_session.add(Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="test", title="测试", description="d",
        base_branch=req.req_branch, work_branch=req.req_branch,
        status="passed", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()

    # 发布执行 fake(request_runner 全成功;重复 host 由唯一性校验拦截)
    from app.services import runner_service as _rs

    async def fake_request(c, message, timeout=15.0):
        return {"ok": True, "data": {}}

    monkeypatch.setattr(_rs, "request_runner", fake_request)

    # 非法格式(含协议)
    resp = await _create_release(client, auth_headers, req, port=10081,
                                 host="https://bad.example.com")
    assert resp.json()["code"] == 7003

    # 重复:先创建一个,再创建同 host
    resp = await _create_release(client, auth_headers, req, port=10082,
                                 host="dup.example.com")
    assert resp.json()["code"] == 0
    resp = await _create_release(client, auth_headers, req, port=10083,
                                 host="dup.example.com")
    assert resp.json()["code"] == 7003
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_offline_deactivates_route(client, auth_headers, db_session, registered_user, monkeypatch):
    """下线:路由 inactive + 容器 stop 指令下发"""
    from app.services import runner_service as _rs

    async def fake_request(c, message, timeout=15.0):
        return {"ok": True, "data": {}}

    monkeypatch.setattr(_rs, "request_runner", fake_request)
    project, runner, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_env(db_session, project, registered_user["user_id"])

    resp = await _create_release(client, auth_headers, req)
    task_id = resp.json()["data"]["task_id"]
    task = (await db_session.execute(
        sqlalchemy.select(Task).where(Task.task_id == task_id)
    )).scalars().first()
    ext = task.extended_attributes
    # 创建流程 run_release 已注册 deploy 路由(active)

    resp = await client.post(f"/api/tasks/{task_id}/offline", headers=auth_headers)
    assert resp.json()["code"] == 0
    await db_session.refresh(task)
    assert task.extended_attributes["deploy_phase"] == "undeployed"

    route = (await db_session.execute(sqlalchemy.select(Route))).scalars().first()
    assert route.status == "inactive"
    assert any(m["type"] == "stop_container" for m in ws.sent)
    runner_registry.unregister(runner.runner_id)
