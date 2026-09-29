"""
BUG-074 测试:Diff/变更基线解析 + 任务创建基线默认值
====================================================
- 自指基线(base==work,存量数据)→ 回退项目默认分支
- 非自指 task.base_branch → 原样使用
- 显式 base_branch 参数 → 最高优先透传
- create_task 默认基线 = project.default_branch(原为 requirement.req_branch 自指)
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.task import Task
from app.models.user import User
from app.models.requirement import Requirement
from app.services import file_service, task_service
from app.services.runner_service import runner_registry


async def _setup_task_with_container(db_session, registered_user, *, base_branch: str,
                                     work_branch: str, project_default: str = "main"):
    """造 项目(default=project_default) + 任务(base/work 可构造自指) + running 容器"""
    project = Project(name=f"d71-{uuid.uuid4().hex[:6]}", slug=f"d71-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"], default_branch=project_default)
    db_session.add(project)
    await db_session.flush()
    task = Task(
        task_id=f"task-71-{uuid.uuid4().hex[:8]}",
        req_id=f"req-71-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        type="dev", title="d71", description="d71", status="running",
        base_branch=base_branch, work_branch=work_branch,
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id=task.task_id, runner_id=f"runner-71-{uuid.uuid4().hex[:4]}",
        project_id=project.project_id, status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    return project, task, container


@pytest.mark.asyncio
async def test_git_diff_degenerate_base_falls_back_to_project_default(
        client, auth_headers, db_session, registered_user, monkeypatch):
    """自指基线(base==work,存量数据)→ 回退项目默认分支"""
    project, task, container = await _setup_task_with_container(
        db_session, registered_user, base_branch="feat/x", work_branch="feat/x", project_default="main")
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.71")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"files": []}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "")
    # 自指基线 → 用项目默认分支,不再 diff 自己
    assert seen[0]["base_branch"] == "main"
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_git_diff_uses_task_base_when_not_degenerate(
        client, auth_headers, db_session, registered_user, monkeypatch):
    """非自指 task.base_branch → 原样使用"""
    project, task, container = await _setup_task_with_container(
        db_session, registered_user, base_branch="master", work_branch="feat/y", project_default="main")
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.72")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"files": []}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "")
    assert seen[0]["base_branch"] == "master"
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_git_diff_explicit_base_highest_priority(
        client, auth_headers, db_session, registered_user, monkeypatch):
    """显式 base_branch 参数最高优先(向后兼容)"""
    project, task, container = await _setup_task_with_container(
        db_session, registered_user, base_branch="feat/x", work_branch="feat/x", project_default="main")
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.73")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"files": []}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    await file_service.task_git_diff(db_session, task.task_id, "/workspace/main", "explicit-b")
    assert seen[0]["base_branch"] == "explicit-b"
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_git_changes_resolves_base_same_way(
        client, auth_headers, db_session, registered_user, monkeypatch):
    """变更清单同口径解析(原端点硬编码 master 不看任务/项目)"""
    project, task, container = await _setup_task_with_container(
        db_session, registered_user, base_branch="feat/z", work_branch="feat/z", project_default="trunk")
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=777, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.74")

    seen: list[dict] = []

    async def fake_request(db, c, message, timeout=15.0):
        if message["type"] == "git_changes":
            seen.append(message)
            return {"files": [{"path": "a.py", "status": "M", "additions": 1, "deletions": 0}]}
        raise AssertionError(f"unexpected {message['type']}")

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    data = await file_service.task_git_changes(db_session, task.task_id, "")
    # 变更清单基线同样回退项目默认分支
    assert seen[0]["base_branch"] == "trunk"
    assert data["total"] == 1
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_create_task_defaults_base_to_project_default_branch(
        client, auth_headers, db_session, registered_user):
    """BUG-074 治本:create_task 默认基线 = 项目默认分支(原 requirement.req_branch 自指)"""
    project = Project(name=f"c71-{uuid.uuid4().hex[:6]}", slug=f"c71-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"], default_branch="main")
    db_session.add(project)
    await db_session.flush()

    from sqlalchemy import select as _select
    res = await db_session.execute(
        _select(User).where(User.user_id == registered_user["user_id"]))
    operator = res.scalar_one()
    operator.gitlab_token_encrypted = "enc-token"

    requirement = Requirement(
        req_id=f"req-71-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        title="d71 需求", description="d71 需求描述", status="approved",
        req_branch="feat/req71",
        created_by=operator.user_id,
    )
    db_session.add(requirement)
    await db_session.flush()

    task = await task_service.create_task(
        db_session, requirement, project, operator,
        type="dev", title="d71 任务", description="",
        base_branch=None, work_branch=None,
    )
    # 基线=项目默认分支;工作分支仍为需求分支(diff 基线≠工作分支 → 全部改动可见)
    assert task.base_branch == "main"
    assert task.work_branch == "feat/req71"
