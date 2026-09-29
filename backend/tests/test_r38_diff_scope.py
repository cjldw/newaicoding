"""
R38:任务工作台 Diff 口径切换(全部改动 ⇄ 仅未提交) — 后端 Red 测试
====================================================================
覆盖判据 1/2:
  ① scope=head → runner 消息 base_branch="HEAD" 且不调 resolve_task_base_branch
  ② scope 缺省(=all) → 行为与现状一致(走 resolve)
  ③ scope=xxx 非法 → 422(httpx AsyncClient 打真实路由)
  ④ changes 与 diff 两端点同参同语义
"""
import uuid

import pytest
import httpx

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.task import Task
from app.services import file_service
from app.services.runner_service import runner_registry


# ---------------------------------------------------------------------------
# fixture:造 项目 + 任务 + running 容器(参照 test_bug074_diff_base.py)
# ---------------------------------------------------------------------------
async def _setup_task_with_container(db_session, registered_user):
    """造 项目 + 任务 + running 容器(用于 scope 测试)"""
    project = Project(
        name=f"r38-{uuid.uuid4().hex[:6]}",
        slug=f"r38-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
        default_branch="main",
    )
    db_session.add(project)
    await db_session.flush()

    task = Task(
        task_id=f"task-r38-{uuid.uuid4().hex[:8]}",
        req_id=f"req-r38-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        type="dev", title="r38", description="r38", status="running",
        base_branch="master", work_branch="feat/r38",
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    container = Container(
        container_id=f"docker-r38-{uuid.uuid4().hex[:10]}",
        task_id=task.task_id,
        runner_id=f"runner-r38-{uuid.uuid4().hex[:4]}",
        project_id=project.project_id,
        status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()

    # 挂一个 main 仓库(变更清单需要)
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/r38/main.git",
        gitlab_repo_id=380, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()

    return project, task, container


# ---------------------------------------------------------------------------
# 判据 1a: scope=head → base_branch="HEAD" 且不调 resolve
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_diff_scope_head_bypasses_resolve(client, auth_headers, db_session, registered_user, monkeypatch):
    """scope=head → runner 消息 base_branch='HEAD' 且不调 resolve_task_base_branch

    关键:resolve mock 若被调用会 raise,以此检测实现是否真的绕过了 resolve。
    """
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.38")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"files": []}

    async def fake_resolve_should_not_be_called(*args, **kwargs):
        raise AssertionError("scope=head 不应调用 resolve_task_base_branch")

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    monkeypatch.setattr(file_service, "resolve_task_base_branch", fake_resolve_should_not_be_called)

    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "", scope="head")

    assert len(seen) == 1
    assert seen[0]["base_branch"] == "HEAD", f"期望 HEAD,实际 {seen[0]['base_branch']}"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 判据 1b: scope 缺省(=all) → 走 resolve,行为与现状一致
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_diff_scope_default_all_calls_resolve(client, auth_headers, db_session, registered_user, monkeypatch):
    """scope 缺省(=all) → 走 resolve_task_base_branch(现状行为)"""
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.39")

    seen: list[dict] = []
    resolve_called = False

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"files": []}

    async def fake_resolve(db, c, task_id, base_branch=None):
        nonlocal resolve_called
        resolve_called = True
        return "resolved-base"

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    monkeypatch.setattr(file_service, "resolve_task_base_branch", fake_resolve)

    # 不传 scope → 默认 all → 走 resolve
    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "")

    assert len(seen) == 1
    assert resolve_called, "scope 缺省(=all)应调用 resolve_task_base_branch"
    assert seen[0]["base_branch"] == "resolved-base"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 判据 1c: changes 端点同语义(scope=head → HEAD)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_changes_scope_head_bypasses_resolve(client, auth_headers, db_session, registered_user, monkeypatch):
    """changes 端点:scope=head → runner 消息 base_branch='HEAD' 且不调 resolve

    关键:resolve mock 若被调用会 raise,以此检测实现是否真的绕过了 resolve。
    """
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.40")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        if message["type"] == "git_changes":
            return {"files": [{"path": "a.py", "status": "M", "additions": 1, "deletions": 0}]}
        raise AssertionError(f"unexpected {message['type']}")

    async def fake_resolve_should_not_be_called(*args, **kwargs):
        raise AssertionError("scope=head 不应调用 resolve_task_base_branch")

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    monkeypatch.setattr(file_service, "resolve_task_base_branch", fake_resolve_should_not_be_called)

    data = await file_service.task_git_changes(db_session, task.task_id, "", scope="head")

    assert len(seen) == 1
    assert seen[0]["base_branch"] == "HEAD", f"期望 HEAD,实际 {seen[0]['base_branch']}"
    assert data["total"] == 1

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 判据 2a: scope=xxx 非法 → 422(diff 端点)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_diff_scope_illegal_returns_422(client, auth_headers, db_session, registered_user):
    """scope=xxx 非法 → 422(httpx AsyncClient 打真实路由)"""
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.41")

    resp = await client.get(
        f"/api/tasks/{task.task_id}/files/diff?scope=xxx",
        headers=auth_headers,
    )
    assert resp.status_code == 422, f"期望 422,实际 {resp.status_code}"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 判据 2b: scope=xxx 非法 → 422(changes 端点)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_changes_scope_illegal_returns_422(client, auth_headers, db_session, registered_user):
    """scope=xxx 非法 → 422(httpx AsyncClient 打真实路由)"""
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.42")

    resp = await client.get(
        f"/api/tasks/{task.task_id}/files/changes?scope=xxx",
        headers=auth_headers,
    )
    assert resp.status_code == 422, f"期望 422,实际 {resp.status_code}"

    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 判据 4: changes 与 diff 两端点同参同语义(scope 参数名/枚举/默认一致)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_changes_and_diff_same_scope_semantics(client, auth_headers, db_session, registered_user, monkeypatch):
    """changes 与 diff 两端点:同 scope 参数名/同枚举/同默认(均为 all)

    关键:resolve mock 若被调用会 raise;scope=head 时两端点均应绕过 resolve 且 base_branch='HEAD'。
    """
    project, task, container = await _setup_task_with_container(db_session, registered_user)
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.43")

    seen_diff: list[dict] = []
    seen_changes: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        if message["type"] == "git_diff":
            seen_diff.append(message)
            return {"files": []}
        elif message["type"] == "git_changes":
            seen_changes.append(message)
            return {"files": []}
        raise AssertionError(f"unexpected {message['type']}")

    async def fake_resolve_should_not_be_called(*args, **kwargs):
        raise AssertionError("scope=head 不应调用 resolve_task_base_branch")

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    monkeypatch.setattr(file_service, "resolve_task_base_branch", fake_resolve_should_not_be_called)

    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "", scope="head")
    await file_service.task_git_changes(db_session, task.task_id, "", scope="head")

    assert len(seen_diff) == 1
    assert len(seen_changes) == 1
    assert seen_diff[0]["base_branch"] == "HEAD"
    assert seen_changes[0]["base_branch"] == "HEAD"

    runner_registry.unregister(container.runner_id)
