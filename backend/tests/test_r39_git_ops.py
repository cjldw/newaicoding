"""
R39 QA-Red 测试:平台侧 git commit / push 接口规格
=================================================
预期:全红(路由/方法/ErrCode 尚未实现)。
覆盖:
- POST /api/tasks/{tid}/git/commit 与 /git/push 路由存在
- 终态任务(done/cancelled/failed/timeout)→ 9001
- 无变更 → 新 ErrCode 2015(GIT_NO_CHANGES)
- 非 editor(viewer)→ 403
- 身份回退链三档:
  * 全量(/user 返回 name+email)→ 用原值
  * 缺失 email → 回退 {gitlab_username}@zhanqi.com
  * /user 整体失败 → 回退链不阻塞 commit(用 gitlab_username/手机号兜底)
- runner 消息捕获断言(type=git_commit/git_push,含 message_b64、author、repo、branch)
"""
import base64
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.project_member import ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import file_service
from app.services.runner_service import runner_registry


async def _setup_task_with_container(
    db_session, user_id, *, status="running", role="main",
    base_branch="main", work_branch="feat/x",
):
    project = Project(
        name=f"r39-{uuid.uuid4().hex[:6]}",
        slug=f"r39-{uuid.uuid4().hex[:6]}",
        owner_id=user_id, default_branch="main",
    )
    db_session.add(project)
    await db_session.flush()
    repo = ProjectRepo(
        project_id=project.project_id, role=role,
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=739, gitlab_bind_type="manual",
        created_by=user_id,
    )
    db_session.add(repo)
    await db_session.flush()
    task = Task(
        task_id=f"task-r39-{uuid.uuid4().hex[:8]}",
        req_id=f"req-r39-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        type="dev", title="r39", description="r39", status=status,
        base_branch=base_branch, work_branch=work_branch,
        created_by=user_id,
    )
    db_session.add(task)
    await db_session.flush()
    container = Container(
        container_id=f"docker-r39-{uuid.uuid4().hex[:10]}",
        task_id=task.task_id, runner_id=f"runner-r39-{uuid.uuid4().hex[:4]}",
        project_id=project.project_id, status="running", exposed_ports=[],
    )
    db_session.add(container)
    await db_session.flush()
    return project, task, container


# ---------------------------------------------------------------------------
# 路由存在性(预期:ImportError / 404 → 红)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commit_route_exists(client, auth_headers, db_session, registered_user):
    """POST /api/tasks/{tid}/git/commit 必须存在"""
    project, task, _ = await _setup_task_with_container(db_session, registered_user["user_id"])
    runner_registry.register(task.task_id, "worker", None, "10.0.0.39")
    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "test"}, headers=auth_headers)
    # 不应 404(路由不存在)或 405(方法不允许)
    assert resp.status_code not in (404, 405), f"路由不存在:{resp.status_code}"
    runner_registry.unregister(task.task_id)


@pytest.mark.asyncio
async def test_push_route_exists(client, auth_headers, db_session, registered_user):
    """POST /api/tasks/{tid}/git/push 必须存在"""
    project, task, _ = await _setup_task_with_container(db_session, registered_user["user_id"])
    runner_registry.register(task.task_id, "worker", None, "10.0.0.40")
    resp = await client.post(f"/api/tasks/{task.task_id}/git/push",
                             json={}, headers=auth_headers)
    assert resp.status_code not in (404, 405)
    runner_registry.unregister(task.task_id)


# ---------------------------------------------------------------------------
# 终态任务 → 9001
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commit_on_terminal_task_returns_9001(
    client, auth_headers, db_session, registered_user,
):
    """终态任务(done)commit → 9001(容器已销毁)"""
    for status in ("done", "cancelled", "failed", "timeout"):
        _, task, _ = await _setup_task_with_container(
            db_session, registered_user["user_id"], status=status)
        resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                                 json={"message": "m"}, headers=auth_headers)
        body = resp.json()
        assert body.get("code") == 9001, f"status={status} 应返回 9001,实际:{body}"


@pytest.mark.asyncio
async def test_push_on_terminal_task_returns_9001(
    client, auth_headers, db_session, registered_user,
):
    """终态任务 push → 9001"""
    _, task, _ = await _setup_task_with_container(
        db_session, registered_user["user_id"], status="done")
    resp = await client.post(f"/api/tasks/{task.task_id}/git/push",
                             json={}, headers=auth_headers)
    assert resp.json().get("code") == 9001


# ---------------------------------------------------------------------------
# 非 editor → 403
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commit_by_viewer_returns_403(
    client, db_session, registered_user,
):
    """viewer 调 commit → 403"""
    # 创建另一个用户作 viewer
    from app.core.security import hash_password
    viewer_phone = "13900000099"
    resp_reg = await client.post("/api/auth/register", json={
        "phone": viewer_phone, "password": "Test1234!", "role": "user"})
    viewer_id = resp_reg.json()["data"]["user_id"]

    project, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    # 把 registered_user 设为 owner,viewer 设为 viewer
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=registered_user["user_id"],
        role="owner", invited_by=registered_user["user_id"], joined_at="2024-01-01"))
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=viewer_id,
        role="viewer", invited_by=registered_user["user_id"], joined_at="2024-01-01"))
    await db_session.flush()

    runner_registry.register(container.runner_id, "worker", None, "10.0.0.41")
    # viewer 登录
    viewer_headers = (await client.post("/api/auth/login", json={
        "phone": viewer_phone, "password": "Test1234!"})).json()["data"]
    viewer_headers = {"Authorization": f"Bearer {viewer_headers['access_token']}"}

    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "m"}, headers=viewer_headers)
    assert resp.status_code == 403 or resp.json().get("code") in (403, 1006)
    runner_registry.unregister(task.task_id)


# ---------------------------------------------------------------------------
# 无变更 → 2015(新 ErrCode)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commit_no_changes_returns_2015(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """runner 返回无变更 → 2015 GIT_NO_CHANGES"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.42")

    # 给 registered_user 设 gitlab token(测试用假加密值)
    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_token_encrypted = "enc"
    await db_session.flush()

    # mock decrypt_token 避免真实解密失败
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    async def fake_request(db, c, message, timeout=15.0):
        # runner 返回 commit="none" 表示无变更
        return {"commit": "none"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "m"}, headers=auth_headers)
    body = resp.json()
    assert body.get("code") == 2015, f"应返回 2015,实际:{body}"
    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# 身份回退链三档
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_identity_full_profile_uses_original(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """/user 全量返回 → 用原 name/email"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.43")

    # 设 gitlab token + mock 解密
    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_token_encrypted = "enc"
    await db_session.flush()
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    # mock gitlab_service.get_user_profile 返回全量
    from app.services import gitlab_service

    async def fake_profile(token, api_base=None):
        return {"name": "Alice", "email": "alice@real.com", "username": "aliceu"}

    monkeypatch.setattr(gitlab_service, "get_user_profile", fake_profile)

    seen = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"commit": "abc1234", "author_name": "Alice", "author_email": "alice@real.com"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "m"}, headers=auth_headers)
    assert resp.status_code == 200
    # runner 消息必须含真实身份(b64 编码)
    assert "author_name_b64" in seen[0]
    assert "author_email_b64" in seen[0]
    assert base64.b64decode(seen[0]["author_name_b64"]).decode() == "Alice"
    assert base64.b64decode(seen[0]["author_email_b64"]).decode() == "alice@real.com"
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_identity_missing_email_falls_back_to_gitlab_username(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """/user 返回 name 但 email 空 → email 回退 {gitlab_username}@zhanqi.com"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.44")

    # 给 registered_user 设 gitlab_username
    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_username = "mygitlab"
    user.gitlab_token_encrypted = "enc"
    await db_session.flush()
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    from app.services import gitlab_service

    async def fake_profile(token, api_base=None):
        return {"name": "Bob", "email": "", "username": "mygitlab"}

    monkeypatch.setattr(gitlab_service, "get_user_profile", fake_profile)

    seen = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"commit": "abc"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "m"}, headers=auth_headers)
    assert resp.status_code == 200
    assert "author_email_b64" in seen[0]
    assert base64.b64decode(seen[0]["author_email_b64"]).decode() == "mygitlab@zhanqi.com"
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_identity_profile_call_fails_falls_back_chain(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """/user 整体失败(网络/1012)→ 回退链不阻塞 commit,用 gitlab_username/手机号兜底"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.45")

    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_username = "fbuser"
    user.gitlab_token_encrypted = "enc"
    user.phone = "13800000099"
    await db_session.flush()
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    from app.services import gitlab_service

    async def fake_profile(token, api_base=None):
        raise RuntimeError("GitLab unreachableable")

    monkeypatch.setattr(gitlab_service, "get_user_profile", fake_profile)

    seen = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"commit": "abc"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    resp = await client.post(f"/api/tasks/{task.task_id}/git/commit",
                             json={"message": "m"}, headers=auth_headers)
    # 不阻塞 → 200
    assert resp.status_code == 200
    # 回退到 gitlab_username@zhanqi.com (b64 编码)
    assert "author_email_b64" in seen[0]
    assert "author_name_b64" in seen[0]
    assert base64.b64decode(seen[0]["author_email_b64"]).decode() == "fbuser@zhanqi.com"
    assert base64.b64decode(seen[0]["author_name_b64"]).decode() == "fbuser"
    runner_registry.unregister(container.runner_id)


# ---------------------------------------------------------------------------
# runner 消息格式断言
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commit_runner_message_format(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """commit 消息格式:type=git_commit + message_b64 + author + repo_path"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"])
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.46")

    # 设 gitlab token + mock 解密
    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_token_encrypted = "enc"
    await db_session.flush()
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    seen = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"commit": "abc"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    await client.post(f"/api/tasks/{task.task_id}/git/commit",
                      json={"message": "feat: 测试"}, headers=auth_headers)
    assert seen[0]["type"] == "git_commit"
    # message 走 base64 通道
    assert "message_b64" in seen[0]
    decoded = base64.b64decode(seen[0]["message_b64"]).decode()
    assert decoded == "feat: 测试"
    # 身份字段也走 b64 通道
    assert "author_name_b64" in seen[0]
    assert "author_email_b64" in seen[0]
    assert "repo_path" in seen[0] or "repos" in seen[0]
    runner_registry.unregister(container.runner_id)


@pytest.mark.asyncio
async def test_push_runner_message_format(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """push 消息格式:type=git_push + branch + repo_path"""
    _, task, container = await _setup_task_with_container(
        db_session, registered_user["user_id"], work_branch="feat/push")
    runner_registry.register(container.runner_id, "worker", None, "10.0.0.47")

    # 设 gitlab token + mock 解密
    from sqlalchemy import select as _select
    res = await db_session.execute(_select(User).where(User.user_id == registered_user["user_id"]))
    user = res.scalar_one()
    user.gitlab_token_encrypted = "enc"
    await db_session.flush()
    from app.core import encryption
    monkeypatch.setattr(encryption, "decrypt_token", lambda x: "fake_token")

    seen = []

    async def fake_request(db, c, message, timeout=15.0):
        seen.append(message)
        return {"branch": "feat/push"}

    monkeypatch.setattr(file_service, "_request_container", fake_request)
    await client.post(f"/api/tasks/{task.task_id}/git/push",
                      json={}, headers=auth_headers)
    assert seen[0]["type"] == "git_push"
    assert seen[0]["branch"] == "feat/push"
    assert "repo_path" in seen[0] or "repos" in seen[0]
    runner_registry.unregister(container.runner_id)
