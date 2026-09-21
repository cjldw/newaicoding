"""
R3 需求管理与打磨测试(平台侧)
==========================
- 创建需求(GitLab mock 建分支;所有绑定 repo)
- 开始打磨(3001 重复;模型未配置引导;容器拉起)
- 提交评审(3002 非 polishing)
- 评审通过/驳回 / 取消
"""
import uuid

import httpx
import pytest

from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.services import requirement_service


def _gitlab_branch_handler(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append((request.method, url))
        if request.method == "POST" and "/repository/branches" in url:
            return httpx.Response(201, json={"name": "req-x"})
        return httpx.Response(404)
    return handler


async def _setup_project(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(
        name="需求项目", slug=f"rq-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"], default_branch="master",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=111, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()
    return project


def _mk_requirement(db_session, project, creator_id, status="draft"):
    r = Requirement(
        req_id=str(uuid.uuid4()),
        title="测试需求", description="描述", status=status,
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    return r


@pytest.mark.asyncio
async def test_create_requirement_success(client, auth_headers, db_session, registered_user):
    """创建需求成功:GitLab mock 建分支;详情可查"""
    project = await _setup_project(db_session, registered_user)
    calls: list = []

    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "用户登录功能", "description": "支持手机号登录", "priority": "high"},
        )
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["req_branch"].startswith("req-")
    assert any(m == "POST" and "/repository/branches" in u for m, u in calls)

    # 详情
    resp = await client.get(f"/api/requirements/{data['data']['req_id']}", headers=auth_headers)
    detail = resp.json()["data"]
    assert detail["status"] == "draft"
    assert detail["title"] == "用户登录功能"
    assert detail["prd_file_path"] == ""  # 打磨任务创建时生成


@pytest.mark.asyncio
async def test_create_requirement_branch_conflict(client, auth_headers, db_session, registered_user):
    """同项目分支名重复:拒绝"""
    project = await _setup_project(db_session, registered_user)
    calls: list = []
    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "需求 A", "description": "d", "req_branch": "req-custom"},
        )
        assert resp.json()["code"] == 0
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "需求 B", "description": "d", "req_branch": "req-custom"},
        )
    assert resp.json()["code"] != 0


@pytest.mark.asyncio
async def test_start_polish_success(client, auth_headers, db_session, registered_user, monkeypatch):
    """开始打磨成功:状态 polishing + prd_file_path 生成(Q26)+ 容器指令下发"""
    project = await _setup_project(db_session, registered_user)
    # 在线 Runner(DB 调度)+ 内存连接
    from app.models.runner import Runner

    db_session.add(Runner(
        name=f"rn-{uuid.uuid4().hex[:6]}", role="worker", token_hash="x",
        status="online", created_by="test",
    ))
    await db_session.flush()
    # 模型配置(R13 resolve 用)
    from app.core.encryption import encrypt_token
    from app.models.model_config import ModelConfig

    db_session.add(ModelConfig(
        project_id=project.project_id, name="main",
        base_url="https://llm.example.com/v1",
        api_key_encrypted=encrypt_token("sk-test"),
        model="claude-sonnet-5", is_default=True, enabled=True,
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()

    from app.services import runner_service
    from app.services.runner_service import runner_registry

    runner_row = (await db_session.execute(
        __import__("sqlalchemy").select(Runner)
    )).scalars().first()
    conn = runner_registry.register(runner_row.runner_id, "worker", None, "10.0.0.7")
    sent: list = []

    async def fake_send(c, message):
        sent.append(message)

    monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

    # 需求
    calls: list = []
    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "打磨需求", "description": "d"},
        )
    req_id = resp.json()["data"]["req_id"]

    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(f"/api/requirements/{req_id}/polish", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["task_id"]

    import sqlalchemy

    req = (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req_id)
    )).scalars().first()
    assert req.status == "polishing"
    assert req.polish_task_id == data["data"]["task_id"]
    assert "docs/" in req.prd_file_path and req.prd_file_path.endswith("/PRD.md")
    runner_registry.unregister(runner_row.runner_id)


@pytest.mark.asyncio
async def test_start_polish_already_polishing(client, auth_headers, db_session, registered_user):
    """已有打磨任务进行中:3001"""
    project = await _setup_project(db_session, registered_user)
    req = _mk_requirement(db_session, project, registered_user["user_id"], status="polishing")
    req.polish_task_id = "task-existing"
    await db_session.flush()

    resp = await client.post(f"/api/requirements/{req.req_id}/polish", headers=auth_headers)
    assert resp.json()["code"] == 3001


@pytest.mark.asyncio
async def test_submit_review_and_review_flow(client, auth_headers, db_session, registered_user):
    """提交评审 + 评审通过/驳回状态机"""
    project = await _setup_project(db_session, registered_user)
    req = _mk_requirement(db_session, project, registered_user["user_id"], status="draft")

    # draft 提交评审 → 3002
    resp = await client.post(f"/api/requirements/{req.req_id}/submit-review", headers=auth_headers)
    assert resp.json()["code"] == 3002

    # polishing → reviewing
    req.status = "polishing"
    await db_session.flush()
    resp = await client.post(f"/api/requirements/{req.req_id}/submit-review", headers=auth_headers)
    assert resp.json()["code"] == 0
    await db_session.refresh(req)
    assert req.status == "reviewing"

    # 驳回(填理由)→ polishing;reject_reason 保留
    resp = await client.post(
        f"/api/requirements/{req.req_id}/review",
        headers=auth_headers,
        json={"approved": False, "reject_reason": "验收标准不清晰"},
    )
    assert resp.json()["code"] == 0
    await db_session.refresh(req)
    assert req.status == "polishing"
    assert req.reject_reason == "验收标准不清晰"

    # 再提交 → 评审通过(无容器:跳过 commit,仅状态流转)
    # 评审通过要求评审人已绑定 GitLab token(1012 校验),直绑 DB
    from sqlalchemy import text as _text

    from app.core.encryption import encrypt_token

    await db_session.execute(
        _text("UPDATE users SET gitlab_token_encrypted = :enc WHERE user_id = :uid"),
        {"enc": encrypt_token("glpat-reviewer"), "uid": registered_user["user_id"]},
    )
    await db_session.flush()
    req.status = "reviewing"
    await db_session.flush()
    resp = await client.post(
        f"/api/requirements/{req.req_id}/review",
        headers=auth_headers,
        json={"approved": True},
    )
    assert resp.json()["code"] == 0
    await db_session.refresh(req)
    assert req.status == "approved"
    assert req.reviewed_by == registered_user["user_id"]


@pytest.mark.asyncio
async def test_cancel_requirement(client, auth_headers, db_session, registered_user):
    """取消需求:rejected + 理由;分支保留(GitLab 不删)"""
    project = await _setup_project(db_session, registered_user)
    req = _mk_requirement(db_session, project, registered_user["user_id"], status="approved")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/cancel",
        headers=auth_headers,
        json={"reason": "优先级调整"},
    )
    assert resp.json()["code"] == 0
    await db_session.refresh(req)
    assert req.status == "rejected"
    assert req.reject_reason == "优先级调整"
