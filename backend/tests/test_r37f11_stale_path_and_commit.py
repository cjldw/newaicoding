"""
R37.F11(BUG-086)同步自愈 + finish 提交结果感知测试
====================================================
现场(任务 89e587e8,2026-10-09 17:27):
  ① AI 把 PRD 写在自选目录 docs/20261009_后台图形验证码登录/,而 req.prd_file_path
    还是上一轮自愈写入的失效路径 docs/20261008_..._228e6d07/PRD.md → 固定路径
    task_read_file 抛「读取失败」→ 整个 sync 中止 → 发现器永远不跑 → prd_content
    一直空(BUG-085 的每轮回传全程空转);
  ② runner commit_push 凭据注入 replace("https://",...) 对 http:// remote 替换不了
    任何东西 → 裸推 → git 交互要用户名(无 tty)→ fatal;旧通道异常又不回包 →
    平台 60s 「Runner 响应超时」→ finish 吞掉 → 任务照常 done。

修复契约:
- 用例 A:固定路径读取失败 → 降级走发现器 → prd_file_path 自愈 + prd_content 回填
- 用例 B:git_commit runner 返回 ok=False 且非「nothing to commit」→ done 语义下
  finish 显式抛错(不再静默 done)
"""
import uuid

import pytest

from app.core.response import BizError
from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services import file_service, runner_service, task_service
from app.services.runner_service import runner_registry
from app.services import requirement_service


async def _seed(db_session, registered_user, stale_path="docs/20261008_旧_228e6d07/PRD.md"):
    runner = Runner(
        name=f"r-f11-{uuid.uuid4().hex[:6]}", role="worker", token_hash="h",
        status="online", current_containers=0, max_containers=10, created_by="test",
    )
    db_session.add(runner)
    await db_session.flush()
    project = Project(
        name=f"p-f11-{uuid.uuid4().hex[:6]}", slug=f"f11-{uuid.uuid4().hex[:8]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        project_id=project.project_id,
        title=f"req-f11-{uuid.uuid4().hex[:6]}", description="t",
        status="polishing", req_branch="feat/f11",
        prd_file_path=stale_path,
        created_by=registered_user["user_id"],
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        req_id=req.req_id, project_id=project.project_id, type="requirement",
        title=f"t-f11-{uuid.uuid4().hex[:6]}", description="t",
        base_branch="master", work_branch="feat/f11", status="running",
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(Container(
        container_id=f"docker-f11-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner.runner_id, project_id=project.project_id,
        status="running", image="platform/devbox:v2", exposed_ports=[],
    ))
    await db_session.flush()
    monkey_target = runner_registry
    return task, req


@pytest.mark.asyncio
async def test_stale_path_falls_through_to_discovery(db_session, monkeypatch, registered_user):
    """用例 A:失效固定路径读取失败 → 发现器自愈路径 + 回填内容(修复前直接中止)"""
    task, req = await _seed(db_session, registered_user)

    monkeypatch.setattr(runner_registry, "get", lambda rid: object())

    async def fake_read_file(db, task_id, container_path):
        if container_path == "/workspace/main/docs/20261009_后台图形验证码登录/PRD.md":
            return {"content": "# PRD:后台图形验证码登录\n\n内容"}
        raise RuntimeError("not found")

    async def fake_file_list(db, task_id, path):
        assert path == "/workspace/main/docs"
        return [{"type": "dir", "path": "20261009_后台图形验证码登录"}]

    monkeypatch.setattr(file_service, "task_read_file", fake_read_file)
    monkeypatch.setattr(file_service, "task_file_list", fake_file_list)

    await requirement_service.sync_prd_from_container(db_session, task.task_id)

    await db_session.refresh(req)
    assert req.prd_file_path == "docs/20261009_后台图形验证码登录/PRD.md", (
        "BUG-086:失效路径应触发发现器自愈(修复前 sync 直接中止)"
    )
    assert req.prd_content and "后台图形验证码登录" in req.prd_content, "PRD 内容应回填"


@pytest.mark.asyncio
async def test_finish_raises_on_git_commit_failure(db_session, monkeypatch, registered_user):
    """用例 B:git_commit ok=False → done 语义下显式抛错(修复前静默 done)"""
    runner = Runner(
        name=f"r-f11b-{uuid.uuid4().hex[:6]}", role="worker", token_hash="h",
        status="online", current_containers=0, max_containers=10, created_by="test",
    )
    db_session.add(runner)
    await db_session.flush()
    project = Project(
        name=f"p-f11b-{uuid.uuid4().hex[:6]}", slug=f"f11b-{uuid.uuid4().hex[:8]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    from app.models.project import ProjectRepo

    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="http://gitlab.example.com/g/p.git",
        gitlab_repo_id=101, created_by=registered_user["user_id"],
    ))
    await db_session.flush()
    req = Requirement(
        project_id=project.project_id, title=f"req-f11b-{uuid.uuid4().hex[:6]}",
        description="t", status="polishing", req_branch="feat/f11b",
        created_by=registered_user["user_id"],
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        req_id=req.req_id, project_id=project.project_id, type="requirement",
        title="t-f11b", description="t", base_branch="master", work_branch="feat/f11b",
        status="running", created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(Container(
        container_id=f"docker-f11b-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner.runner_id, project_id=project.project_id,
        status="running", image="platform/devbox:v2", exposed_ports=[],
    ))
    await db_session.flush()

    monkeypatch.setattr(runner_registry, "get", lambda rid: object())

    async def fake_request_runner(conn, message, timeout=15.0):
        return {"ok": False, "error": "PRD push 失败(128): fatal: could not read Username"}

    async def fake_bot_config(db):
        return ("http://gitlab.example.com", "bot-token", None)

    monkeypatch.setattr(runner_service, "request_runner", fake_request_runner)
    monkeypatch.setattr(
        "app.services.platform_settings_service.get_gitlab_bot_config", fake_bot_config
    )
    # PRD 回传钩子(mock 掉,聚焦提交失败断言)
    monkeypatch.setattr(
        requirement_service, "sync_prd_from_container", _noop_sync_factory()
    )

    from app.models.user import User

    operator = User(user_id=registered_user["user_id"])
    with pytest.raises(BizError) as exc:
        await task_service.finish_task(db_session, task, operator, status="done")
    assert "仓库提交失败" in exc.value.message
    await db_session.refresh(task)
    assert task.status == "running", "提交失败不得置 done"


def _noop_sync_factory():
    async def _noop(db, task_id):
        pass
    return _noop
