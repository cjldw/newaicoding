"""
R3 打磨 Tab 免容器预览 — Red 阶段失败测试
======================================
覆盖 DEVPLAN/R3.md「完成判据」表判据 1 的五个分支(后端部分):
1. 预置 prd_content 非空 → GET /api/requirements/{req_id}/prd-content 返回 200 {prd_content, source: 'db'}
2. prd_content 为 NULL + FakeWS 容器在线(monkeypatch file_service.task_read_file)
   → 返回 (content, 'container') 且库中 prd_content 已回填
3. prd_content 为 NULL + 无 running 容器 → 200 {prd_content: null, source: 'none'}(非 500)
4. req_id 不存在 → 404
5. 非项目成员访问 → 403

打磨任务定位逻辑(接口契约降级链②)同时覆盖:
- requirement.polish_task_id 指向的 task 存在 running 容器

mock 策略:
- 容器/runner:参照 test_prd_sync.py 的 _seed_task_with_container 模式,monkeypatch
  file_service.task_read_file + runner_registry 注册
- 不测前端(前端无单测基建)

已知坑:
- 单进程 pytest;不动 test_prd_sync.py / test_requirement_prd_content.py
- Red 阶段预期:路由不存在 → 404(对非 404 用例为失败),不是语法错误
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task
from app.services import file_service
from app.services.runner_service import runner_registry


# ---------------------------------------------------------------------------
# 辅助:构造 project + requirement(+ 可选 task + container)
# ---------------------------------------------------------------------------
async def _mk_project_with_req(db_session, owner_id, prd_content=None,
                                polish_task_id=None):
    """创建项目 + 需求(可预置 prd_content / polish_task_id)"""
    project = Project(
        name="r3-prd-api-p",
        slug=f"r3p-{uuid.uuid4().hex[:6]}",
        owner_id=owner_id,
    )
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="R3 PRD API 测试需求",
        description="d",
        status="draft",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=owner_id,
        project_id=project.project_id,
        prd_content=prd_content,
        polish_task_id=polish_task_id,
        prd_file_path="docs/PRD.md",  # R3:sync_prd_from_container 需要此字段
    )
    db_session.add(req)
    await db_session.flush()
    return project, req


async def _seed_task_with_container(db_session, project_id, req_id,
                                     owner_id, task_id=None):
    """构造 requirement 关联的 task + running container(polish_task_id 指向)"""
    task_id = task_id or f"task-r3-{uuid.uuid4().hex[:8]}"
    task = Task(
        task_id=task_id,
        req_id=req_id,
        project_id=project_id,
        type="requirement",
        title="polish task",
        description="打磨 PRD",
        base_branch="master",
        work_branch="req-test",
        created_by=owner_id,
    )
    db_session.add(task)
    await db_session.flush()
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id=task_id,
        runner_id=f"runner-{uuid.uuid4().hex[:6]}",
        project_id=project_id,
        status="running",
        exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.99")
    return task, container


async def _register_member_user(client):
    """注册普通用户,返回 {headers, user_id}(参照 test_requirements_api.py)"""
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    return {"headers": headers, "user_id": user_id}


# ---------------------------------------------------------------------------
# 分支 1: 预置 prd_content 非空 → 返回 (content, 'db')
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_from_db(client, auth_headers, db_session, registered_user):
    """判据 1-①:预置 prd_content 非空 → 200 {prd_content, source: 'db'}"""
    expected = "# PRD Title\n\n## Background\n预置副本内容"
    project, req = await _mk_project_with_req(
        db_session, registered_user["user_id"], prd_content=expected
    )

    resp = await client.get(
        f"/api/requirements/{req.req_id}/prd-content",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"期望 200,实际 {resp.status_code}: {resp.text[:200]}"
    data = resp.json()["data"]
    assert data["prd_content"] == expected, (
        f"期望 prd_content='{expected}',实际 '{data.get('prd_content')}'"
    )
    assert data["source"] == "db", f"期望 source='db',实际 '{data.get('source')}'"


# ---------------------------------------------------------------------------
# 分支 2: prd_content NULL + 容器在线 → (content, 'container') 且库已回填
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_from_container_fills_back(
    client, auth_headers, db_session, registered_user, monkeypatch
):
    """判据 1-②:NULL + FakeWS 容器在线 → 返回 (content, 'container') 且库中 prd_content 已回填"""
    project, req = await _mk_project_with_req(
        db_session, registered_user["user_id"], prd_content=None
    )
    task, container = await _seed_task_with_container(
        db_session, project.project_id, req.req_id, registered_user["user_id"]
    )
    # 把 polish_task_id 指向该 task(打磨任务定位逻辑覆盖)
    req.polish_task_id = task.task_id
    await db_session.flush()

    mock_content = "# 从容器读到的 PRD\n\n容器直读内容"

    async def fake_task_read_file(db, task_id, path):
        return {"path": path, "content": mock_content, "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    resp = await client.get(
        f"/api/requirements/{req.req_id}/prd-content",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"期望 200,实际 {resp.status_code}: {resp.text[:200]}"
    data = resp.json()["data"]
    assert data["prd_content"] == mock_content, (
        f"期望 prd_content='{mock_content}',实际 '{data.get('prd_content')}'"
    )
    assert data["source"] == "container", (
        f"期望 source='container',实际 '{data.get('source')}'"
    )

    # 库中 prd_content 已回填
    await db_session.refresh(req)
    assert req.prd_content == mock_content, (
        f"库中 prd_content 应已回填,实际 '{req.prd_content}'"
    )

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 分支 3: prd_content NULL + 无 running 容器 → 200 {prd_content: null, source: 'none'}
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_no_container_returns_none(
    client, auth_headers, db_session, registered_user
):
    """判据 1-③:NULL + 无 running 容器 → 200 {prd_content: null, source: 'none'}(非 500)"""
    project, req = await _mk_project_with_req(
        db_session, registered_user["user_id"], prd_content=None
    )
    # 不创建任何 task/container

    resp = await client.get(
        f"/api/requirements/{req.req_id}/prd-content",
        headers=auth_headers,
    )
    # 关键:HTTP 恒 200,不能是 500
    assert resp.status_code == 200, (
        f"期望 200(降级到 none),实际 {resp.status_code}: {resp.text[:200]}"
    )
    data = resp.json()["data"]
    assert data["prd_content"] is None, (
        f"期望 prd_content=null,实际 '{data.get('prd_content')}'"
    )
    assert data["source"] == "none", f"期望 source='none',实际 '{data.get('source')}'"


# ---------------------------------------------------------------------------
# 分支 4: req_id 不存在 → 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_not_found(client, auth_headers):
    """判据 1-④:req_id 不存在 → 404"""
    fake_req_id = f"req-{uuid.uuid4().hex[:8]}-nonexistent"
    resp = await client.get(
        f"/api/requirements/{fake_req_id}/prd-content",
        headers=auth_headers,
    )
    assert resp.status_code == 404, (
        f"期望 404,实际 {resp.status_code}: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# 分支 5: 非项目成员访问 → 403
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_non_member_forbidden(
    client, db_session, registered_user
):
    """判据 1-⑤:非项目成员访问 → 403"""
    project, req = await _mk_project_with_req(
        db_session, registered_user["user_id"], prd_content="secret content"
    )
    # 注册另一个用户,不加入项目
    outsider = await _register_member_user(client)

    resp = await client.get(
        f"/api/requirements/{req.req_id}/prd-content",
        headers=outsider["headers"],
    )
    assert resp.status_code == 403, (
        f"期望 403,实际 {resp.status_code}: {resp.text[:200]}"
    )


# ---------------------------------------------------------------------------
# 打磨任务定位逻辑(polish_task_id 指向的 task 存在 running 容器)
# 覆盖接口契约降级链②:requirement.polish_task_id 优先定位打磨任务
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_prd_content_uses_polish_task_id(
    client, auth_headers, db_session, registered_user, monkeypatch
):
    """降级链②:polish_task_id 指向的 task 存在 running 容器 → 走该容器读"""
    project, req = await _mk_project_with_req(
        db_session, registered_user["user_id"], prd_content=None
    )
    # 创建 polish_task(通过 polish_task_id 显式指向)
    polish_task_id = f"task-polish-{uuid.uuid4().hex[:8]}"
    task, container = await _seed_task_with_container(
        db_session, project.project_id, req.req_id,
        registered_user["user_id"], task_id=polish_task_id
    )
    req.polish_task_id = polish_task_id
    await db_session.flush()

    mock_content = "# 通过 polish_task_id 找到的 PRD"
    called_task_ids = []

    async def fake_task_read_file(db, task_id, path):
        called_task_ids.append(task_id)
        return {"path": path, "content": mock_content, "encoding": "utf-8"}

    monkeypatch.setattr(file_service, "task_read_file", fake_task_read_file)

    resp = await client.get(
        f"/api/requirements/{req.req_id}/prd-content",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"期望 200,实际 {resp.status_code}: {resp.text[:200]}"
    data = resp.json()["data"]
    assert data["prd_content"] == mock_content
    assert data["source"] == "container"
    # 关键断言:读的是 polish_task_id 指向的 task,而非其他 task
    assert polish_task_id in called_task_ids, (
        f"应通过 polish_task_id='{polish_task_id}' 定位容器,实际调用 {called_task_ids}"
    )

    runner_registry.unregister(container.runner_id)
