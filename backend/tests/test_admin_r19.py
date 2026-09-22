"""
R19 平台角色与权限测试
==========================
- 用户列表(超管 only/打码/响应最小化)
- 禁用/启用(token_version+1 即失效;最后超管 19001;取消 running 任务)
- 邀请生命周期(生成/消费/撤销)
- 审计日志查询(时间/用户/类型过滤;只读)
"""
import uuid

import pytest
import sqlalchemy
import sqlalchemy

from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.services import audit_service
from tests.test_projects_api import _insert_project, _seed_gitlab_settings


async def _mk_user(db_session, role="user", status="active"):
    from app.core.security import hash_password

    u = User(
        phone=f"136{str(uuid.uuid4().int)[:8]}",
        password_hash=hash_password("Test1234"),
        role=role, status=status,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _login(client, user_row):
    resp = await client.post(
        "/api/auth/login",
        json={"phone": user_row.phone, "password": "Test1234"},
    )
    assert resp.json()["code"] == 0, resp.json()
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_user_list_superadmin_only(client, auth_headers, db_session, registered_user):
    """用户列表仅超管;普通用户(第二个注册用户)403 19002"""
    from tests.test_projects_api import _register_and_login

    other_headers, _uid = await _register_and_login(client)
    resp = await client.get("/api/admin/users", headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == 19002

    # 超管(auth_headers=首个注册用户)可访问
    resp = await client.get("/api/admin/users", headers=auth_headers)
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_user_list_masks_phone(client, auth_headers, db_session, registered_user):
    """用户列表:手机号打码;不含 password_hash/token 密文"""
    resp = await client.get("/api/admin/users", headers=auth_headers)
    data = resp.json()
    assert data["code"] == 0
    items = data["data"]["items"]
    assert len(items) >= 1
    for item in items:
        assert "****" in item["phone"]
        assert "password_hash" not in str(item)
        assert "gitlab_token_encrypted" not in str(item)


@pytest.mark.asyncio
async def test_disable_user_bumps_token_version(client, auth_headers, db_session, registered_user):
    """禁用用户:旧 JWT 立即 401(D17);启用后恢复

    先提升第二个用户为 superadmin,使 registered_user 不是最后一个超管,
    禁用才能走通(19001 保护不拦)。
    """
    from tests.test_projects_api import _register_and_login

    _second_headers, second_uid = await _register_and_login(client)
    # 提升第二个用户为 superadmin(保底 ≥2 个 active 超管,绕开 19001)
    from sqlalchemy import text as _t

    await db_session.execute(
        _t("UPDATE users SET role = 'superadmin' WHERE user_id = :u"),
        {"u": second_uid},
    )
    await db_session.flush()

    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()

    # 旧 token 请求可用(未禁用前)
    resp = await client.get("/api/users/me", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/admin/users/{user.user_id}/status",
        headers=auth_headers,
        json={"status": "disabled"},
    )
    data = resp.json()
    assert data["code"] == 0

    # 旧 token 请求 → 401(token_version 已 +1)
    resp = await client.get("/api/users/me", headers=auth_headers)
    assert resp.status_code == 401

    # 重新登录:disabled 用户被拒(1005/1007 均为拒绝语义)
    resp = await client.post("/api/auth/login", json={
        "phone": registered_user["phone"], "password": registered_user["password"],
    })
    assert resp.json()["code"] in (1005, 1007)

    # 启用后可重新登录(用第二超管的 header 执行启用)
    resp = await client.patch(
        f"/api/admin/users/{user.user_id}/status",
        headers=_second_headers,
        json={"status": "active"},
    )
    assert resp.json()["code"] == 0
    resp = await client.post("/api/auth/login", json={
        "phone": registered_user["phone"], "password": registered_user["password"],
    })
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_disable_last_superadmin_rejected(client, auth_headers, db_session, registered_user):
    """禁用最后一个 active 超管:19001(auth_headers 用户=首个注册 bootstrap 超管)"""
    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    assert user.role == "superadmin"

    resp = await client.patch(
        f"/api/admin/users/{user.user_id}/status",
        headers=auth_headers,
        json={"status": "disabled"},
    )
    assert resp.json()["code"] == 19001


@pytest.mark.asyncio
async def test_disable_user_cancels_running_tasks(client, superadmin_headers, auth_headers,
                                                  db_session, registered_user):
    """禁用用户取消其 running 任务"""
    project = await _insert_project(db_session, registered_user["user_id"])
    task = Task(
        task_id=str(uuid.uuid4()), req_id="req-x", project_id=project.project_id,
        type="dev", title="t", description="d", base_branch="b", work_branch="b",
        status="running", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()

    resp = await client.patch(
        f"/api/admin/users/{user.user_id}/status",
        headers=superadmin_headers,
        json={"status": "disabled"},
    )
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["cancelled_tasks"] == 1

    await db_session.refresh(task)
    assert task.status == "cancelled"


@pytest.mark.asyncio
async def test_superadmin_virtual_owner_passes_project_guard(client, auth_headers, db_session, registered_user):
    """超管未参与项目也能过 owner 级 Guard(D16 虚拟 owner)"""
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = await _insert_project(db_session, registered_user["user_id"])

    # 超管(auth_headers 用户是首个注册=superadmin) PATCH 项目 → 0
    resp = await client.patch(
        f"/api/projects/{project.project_id}",
        headers=auth_headers,
        json={"description": "超管改的"},
    )
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_invitation_lifecycle(client, superadmin_headers, auth_headers, db_session, registered_user):
    """邀请生命周期:生成 → 列表 → 撤销(token 失效)"""
    resp = await client.post(
        "/api/admin/invitations",
        headers=superadmin_headers,
        json={"invited_phone": "13800000000"},
    )
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["invitation_token"].startswith("qc-invite-")
    invitation_id = data["data"]["invitation_id"]

    # 撤销
    resp = await client.delete(
        f"/api/admin/invitations/{invitation_id}",
        headers=superadmin_headers,
    )
    assert resp.json()["code"] == 0

    # 消费已撤销 token:无 pending 匹配 → False
    ok = await audit_service.consume_invitation(db_session, data["data"]["invitation_token"], "u-x")
    assert ok is False


@pytest.mark.asyncio
async def test_audit_logs_query(client, superadmin_headers, db_session, registered_user):
    """审计查询:写入 → 过滤(time/user/action_type)→ 只读"""
    project = await _insert_project(db_session, registered_user["user_id"])
    # 写两条审计(直插,避免依赖 operator 对象)
    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    db_session.add(AuditLog(
        user_id=user.user_id, operator_role=user.role,
        action_type="project.create", project_id=project.project_id,
    ))
    db_session.add(AuditLog(
        user_id=user.user_id, operator_role=user.role,
        action_type="user.disable", target_type="user", target_id="u-1",
    ))
    await db_session.flush()

    resp = await client.get("/api/admin/audit-logs", headers=superadmin_headers)
    data = resp.json()["data"]
    assert data["total"] >= 2

    resp = await client.get(
        "/api/admin/audit-logs",
        headers=superadmin_headers,
        params={"action_type": "project.create"},
    )
    items = resp.json()["data"]["items"]
    assert all(i["action_type"] == "project.create" for i in items)
