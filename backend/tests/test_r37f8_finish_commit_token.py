"""
R37.F8(BUG-082)finish 提交凭据链测试
====================================
根因:finish_task 只取创建者个人 token,创建者未绑定 GitLab token 时
creator_token="" → `if runner_conn is not None and creator_token:` 整段
commit/push 静默跳过,任务照常 done,前端 toast 谎称「PRD 已推送」。
(实锤现场:需求 0d227c83 创建者 2845fe31 has_token=0,两次 finish 需求
分支零 commit。)

修复契约:
- 用例 A:创建者无 token + 平台 bot 已配置 → git_commit 收到 token=bot_token
- 用例 B:创建者无 token + bot 未配置 → BizError 显式报错(文案含「绑定」),
  任务状态不变 done
- 用例 C:创建者有 token → 行为不变(token=creator_token,回归保护)
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.core.response import BizError
from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.models.user import User
from app.services import container_service, runner_service, task_service
from app.services.runner_service import runner_registry


async def _insert_runner(db_session, name="r-f8"):
    r = Runner(
        name=name,
        role="worker",
        token_hash="placeholder-hash",
        status="online",
        current_containers=0,
        max_containers=10,
        created_by="test",
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _insert_repo(db_session, project_id, created_by):
    repo = ProjectRepo(
        project_id=project_id,
        role="main",
        gitlab_repo_url="http://gitlab.example.com/g/p.git",
        gitlab_repo_id=101,
        created_by=created_by,
    )
    db_session.add(repo)
    await db_session.flush()
    return repo


async def _mk_scenario(db_session, registered_user, with_running_container=True):
    """构建 finish 场景:runner + project + main repo + running 的 requirement 任务"""
    runner = await _insert_runner(db_session)
    project = Project(
        name=f"p-f8-{uuid.uuid4().hex[:6]}",
        slug=f"f8-{uuid.uuid4().hex[:8]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    await _insert_repo(db_session, project.project_id, created_by=registered_user["user_id"])

    req = Requirement(
        project_id=project.project_id,
        title=f"req-f8-{uuid.uuid4().hex[:6]}",
        description="t",
        status="polishing",
        req_branch=f"req-{uuid.uuid4().hex[:6]}",
        created_by=registered_user["user_id"],
    )
    db_session.add(req)
    await db_session.flush()

    task = Task(
        req_id=req.req_id,
        project_id=project.project_id,
        type="dev",
        title=f"finish-f8-{uuid.uuid4().hex[:6]}",
        description="t",
        base_branch="master",
        work_branch="feat/f8",
        status="running",
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    if with_running_container:
        db_session.add(Container(
            container_id=f"docker-f8-{uuid.uuid4().hex[:8]}",
            task_id=task.task_id,
            runner_id=runner.runner_id,
            project_id=project.project_id,
            status="running",
            image="platform/devbox:v2",
            exposed_ports=[5173, 8000],
        ))
        await db_session.flush()
    return task


def _patch_env(monkeypatch, commits, bot_config_impl=None):
    """统一 mock:runner_registry 在线 + git_commit 捕获 + request_stop 假收容"""
    class FakeConn:
        pass

    def fake_get(runner_id):
        # 单 runner 场景:一律在线(DB 行 runner_id 是模型默认 uuid,不预设键)
        return FakeConn()

    monkeypatch.setattr(runner_registry, "get", fake_get)

    async def fake_request_runner(conn, message, timeout=15.0):
        if message.get("type") == "git_commit":
            commits.append(message)
        return {"ok": True}

    monkeypatch.setattr(runner_service, "request_runner", fake_request_runner)

    async def fake_request_stop(db, c):
        c.status = "destroyed"
        c.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()

    monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

    if bot_config_impl is not None:
        monkeypatch.setattr(
            "app.services.platform_settings_service.get_gitlab_bot_config",
            bot_config_impl,
        )


@pytest.mark.asyncio
async def test_finish_falls_back_to_bot_token(db_session, monkeypatch, registered_user):
    """用例 A:创建者无 token + bot 已配置 → git_commit 用 bot_token(修复前静默跳过 → Red)"""
    commits = []

    async def bot_ok(db):
        return ("http://gitlab.example.com", "bot-token-xyz", None)

    _patch_env(monkeypatch, commits, bot_config_impl=bot_ok)

    task = await _mk_scenario(db_session, registered_user)
    operator = User(user_id=registered_user["user_id"])

    await task_service.finish_task(db_session, task, operator, status="done")

    assert len(commits) == 1, "创建者无 token 时应回退 bot token 完成提交(修复前静默跳过)"
    assert commits[0]["token"] == "bot-token-xyz", "git_commit 应携带平台 bot token"
    assert task.status == "done"


@pytest.mark.asyncio
async def test_finish_raises_when_no_credentials(db_session, monkeypatch, registered_user):
    """用例 B:创建者无 token + bot 未配置 → 显式报错,任务不得置 done"""

    async def bot_missing(db):
        raise BizError(2001, "平台 GitLab 未配置,请联系管理员")

    _patch_env(monkeypatch, [], bot_config_impl=bot_missing)

    task = await _mk_scenario(db_session, registered_user)
    operator = User(user_id=registered_user["user_id"])

    with pytest.raises(BizError) as exc:
        await task_service.finish_task(db_session, task, operator, status="done")

    assert "绑定" in exc.value.message, "报错文案应指导用户绑定 GitLab token"
    assert task.status == "running", "提交凭据缺失时任务不得置 done(不再静默)"


@pytest.mark.asyncio
async def test_finish_prefers_creator_token(db_session, monkeypatch, registered_user):
    """用例 C:创建者有 token → 行为不变(回归保护)"""
    commits = []
    _patch_env(monkeypatch, commits, bot_config_impl=None)

    task = await _mk_scenario(db_session, registered_user)
    # 创建者绑定 token(密文形态)——同事务 UPDATE,规避 RR 快照下 API 侧已提交行不可见
    from sqlalchemy import update as sa_update

    await db_session.execute(
        sa_update(User)
        .where(User.user_id == registered_user["user_id"])
        .values(gitlab_token_encrypted="enc-creator-token")
    )

    import app.core.encryption as enc

    monkeypatch.setattr(enc, "decrypt_token", lambda c: "creator-token-abc")

    operator = User(user_id=registered_user["user_id"])
    await task_service.finish_task(db_session, task, operator, status="done")

    assert len(commits) == 1
    assert commits[0]["token"] == "creator-token-abc", "创建者 token 优先,行为不变"
    assert task.status == "done"
