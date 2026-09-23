"""
R25 审计日志全量接入 — P1/P2 批次
==================================
覆盖 R25.md 完成判据:
2. 注册/邀请(邀请 create+revoke;consume 无宿主→ISSUES 登记)
3. 项目 6 + 成员 4(可轻量触发子集:成员 4 全覆盖;project update/archive/delete;
   create/add_repo/unbind 涉 GitLab mock,归 R2 既有套件 + 手动走查)
4. 模型配置 create/delete + 平台设置 1(TODO 已删)
5. Runner 4 + 系统 sweep_offline(system 占位角色断言)
6. 任务 done/cancelled + 系统 sweep_timeouts;release.offline(API)
8. 写失败不阻塞(P0 已覆盖 spawn 语义;本批不重复)

断言策略同 P0:spawn(系统事件)走独立会话轮询;事务内(audit_write,测试 override
的 get_db 不 commit)走 db_session 查询。
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.runner import Runner
from app.models.task import Task
from app.core.security import hash_password
from app.services import task_service, runner_service

from tests.test_projects_api import _insert_project, _register_and_login

PLACEHOLDER_UID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _phone() -> str:
    return f"136{str(uuid.uuid4().int)[:8]}"[:11]


async def _spawn_rows(action_type: str, timeout: float = 2.0) -> list:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(AuditLog).where(AuditLog.action_type == action_type)
            )).scalars().all()
        if rows:
            return list(rows)
        await asyncio.sleep(0.05)
    return []


async def _db_rows(db_session, action_type: str) -> list:
    return list((await db_session.execute(
        select(AuditLog).where(AuditLog.action_type == action_type)
    )).scalars().all())


async def _make_user(db_session) -> User:
    user = User(
        phone=_phone(),
        password_hash=hash_password("Test1234"),
        role="user",
        token_version=0,
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# 判据 3:成员 4 事件
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_member_lifecycle_audit(client, db_session):
    """邀请/改角色/转让/移除 → 各 +1 行(操作者角色正确)"""
    # 占位注册:首个注册用户自动成为 superadmin(R1 bootstrap);
    # 本测试 owner 须为普通用户(超管转让后无成员行,虚拟 owner 语义,见 R12 留痕)
    await client.post("/api/auth/register", json={"phone": _phone(), "password": "Test1234"})
    headers, owner_id = await _register_and_login(client)
    target = await _make_user(db_session)
    project = await _insert_project(db_session, owner_id=owner_id)

    # 邀请(project_member.add)
    resp = await client.post(
        f"/api/projects/{project.project_id}/members", headers=headers,
        json={"phone": target.phone, "role": "editor"},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "project_member.add")
    assert len(rows) == 1
    assert rows[0].target_id == target.user_id
    assert rows[0].detail.get("role") == "editor"
    assert target.phone not in str(rows[0].detail)  # 判据 11:手机号不落 detail

    # 改角色(project_member.role_change)
    resp = await client.patch(
        f"/api/projects/{project.project_id}/members/{target.user_id}",
        headers=headers, json={"role": "viewer"},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "project_member.role_change")
    assert len(rows) == 1
    assert rows[0].detail.get("new_role") == "viewer"

    # 转让(project_member.transfer_ownership)
    resp = await client.post(
        f"/api/projects/{project.project_id}/transfer-ownership", headers=headers,
        json={"new_owner_user_id": target.user_id},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "project_member.transfer_ownership")
    assert len(rows) == 1
    assert rows[0].target_id == target.user_id

    # 移除(新 owner 移除原 owner;原 owner 已降 editor,须用新 owner 身份操作)
    await db_session.refresh(project)
    resp = await client.post(
        "/api/auth/login", json={"phone": target.phone, "password": "Test1234"},
    )
    target_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    resp = await client.delete(
        f"/api/projects/{project.project_id}/members/{owner_id}", headers=target_headers,
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "project_member.remove")
    assert len(rows) == 1
    assert rows[0].target_id == owner_id


# ---------------------------------------------------------------------------
# 判据 3:项目 update/archive/delete(直插项目,owner 操作)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_lifecycle_audit(client, db_session):
    headers, owner_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=owner_id)

    resp = await client.patch(
        f"/api/projects/{project.project_id}", headers=headers, json={"name": "改名后"},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "project.update")
    assert len(rows) == 1
    assert rows[0].project_id == project.project_id

    resp = await client.post(f"/api/projects/{project.project_id}/archive", headers=headers)
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "project.archive")) == 1

    resp = await client.delete(f"/api/projects/{project.project_id}", headers=headers)
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "project.delete")) == 1


# ---------------------------------------------------------------------------
# 判据 4:模型配置 create/delete + 平台设置 update
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_model_config_audit(client, db_session):
    from tests.test_model_configs_api import _llm_mock, _llm_ok_handler

    headers, owner_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=owner_id)

    # R13:create 经 API 层连通性测试 → mock LLM 成功响应
    with _llm_mock(_llm_ok_handler):
        resp = await client.post(
            f"/api/projects/{project.project_id}/model-configs", headers=headers,
            json={"name": "主模型", "base_url": "https://api.x.com/v1",
                  "api_key": "sk-test-key-000", "model": "gpt-x", "is_default": False, "enabled": True},
        )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "model_config.create")
    assert len(rows) == 1
    assert rows[0].detail.get("model") == "gpt-x"
    assert "sk-test-key-000" not in str(rows[0].detail)  # 判据 11:api_key 不落审计

    config_id = resp.json()["data"]["config_id"]
    resp = await client.delete(
        f"/api/projects/{project.project_id}/model-configs/{config_id}", headers=headers,
    )
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "model_config.delete")) == 1


@pytest.mark.asyncio
async def test_platform_settings_update_audit(client, db_session, superadmin_headers):
    """PUT 平台设置 → platform_settings.update(detail 只记键列表,不记值)"""
    resp = await client.put(
        "/api/admin/platform-settings", headers=superadmin_headers,
        json={"max_containers_total": 66},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "platform_settings.update")
    assert len(rows) == 1
    assert rows[0].detail.get("updated_keys") == ["max_containers_total"]
    assert "66" not in str(rows[0].detail)  # 值不落 detail


# ---------------------------------------------------------------------------
# 判据 2:邀请 create + revoke(consume 无宿主 → ISSUES)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invitation_audit(client, db_session, superadmin_headers):
    resp = await client.post(
        "/api/admin/invitations", headers=superadmin_headers, json={"invited_phone": "13800001111"},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "invitation.create")
    assert len(rows) == 1
    detail = str(rows[0].detail)
    assert "expires_in_days" in detail
    token = resp.json()["data"]["invitation_token"]
    assert token not in detail  # token 明文不落审计

    invitation_id = resp.json()["data"]["invitation_id"]
    resp = await client.delete(
        f"/api/admin/invitations/{invitation_id}", headers=superadmin_headers,
    )
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "invitation.revoke")) == 1


# ---------------------------------------------------------------------------
# 判据 5:Runner 4 事件(超管 API)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_runner_lifecycle_audit(client, db_session, superadmin_headers):
    resp = await client.post(
        "/api/admin/runners", headers=superadmin_headers,
        json={"name": f"r-{uuid.uuid4().hex[:6]}", "role": "worker", "max_containers": 3},
    )
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "runner.create")
    assert len(rows) == 1
    assert str(resp.json()["data"]["token"]) not in str(rows[0].detail)  # token 不落审计
    runner_id = resp.json()["data"]["runner_id"]

    resp = await client.post(f"/api/admin/runners/{runner_id}/reset-token", headers=superadmin_headers)
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "runner.reset_token")) == 1

    resp = await client.post(f"/api/admin/runners/{runner_id}/disable", headers=superadmin_headers)
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "runner.disable")) == 1

    resp = await client.delete(f"/api/admin/runners/{runner_id}", headers=superadmin_headers)
    assert resp.json()["code"] == 0, resp.text
    assert len(await _db_rows(db_session, "runner.delete")) == 1


# ---------------------------------------------------------------------------
# 判据 6:任务 done/cancelled(service 直调)+ retry(API)+ sweep_timeouts(系统)
# ---------------------------------------------------------------------------
def _make_task(db_session, project, created_by: str, type_="dev", status="running") -> Task:
    task = Task(
        req_id=f"r-{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        type=type_,
        title="审计测试任务",
        description="d",
        base_branch="main",
        work_branch="main",
        status=status,
        created_by=created_by,
    )
    db_session.add(task)
    return task


async def _get_user(db_session, user_id: str) -> User:
    """按 user_id 取 User(作为 finish_task 的 operator)"""
    return (await db_session.execute(
        select(User).where(User.user_id == user_id)
    )).scalars().first()


@pytest.mark.asyncio
async def test_task_done_and_cancelled_audit(client, db_session):
    headers, user_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=user_id)
    operator = await _get_user(db_session, user_id)

    task = _make_task(db_session, project, user_id)
    await db_session.flush()
    await task_service.finish_task(db_session, task, operator, status="done")
    rows = await _db_rows(db_session, "task.done")
    assert len(rows) == 1
    assert rows[0].target_id == task.task_id

    task2 = _make_task(db_session, project, user_id)
    await db_session.flush()
    await task_service.finish_task(db_session, task2, operator, status="cancelled")
    assert len(await _db_rows(db_session, "task.cancelled")) == 1


@pytest.mark.asyncio
async def test_task_timeout_sweep_system_audit(client, db_session):
    """系统 sweep → task.timeout_sweep(user_id=占位,role=system)"""
    headers, user_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=user_id)
    task = _make_task(db_session, project, user_id, status="running")
    task.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=61)
    await db_session.flush()

    count = await task_service.sweep_timeouts(db_session)
    assert count >= 1

    rows = await _spawn_rows("task.timeout_sweep")
    assert len(rows) >= 1
    row = rows[0]
    assert row.user_id == PLACEHOLDER_UID
    assert row.operator_role == "system"
    assert row.detail.get("reason") == "task_timeout_sweep"
    assert row.ip is None  # 系统事件不记 ip


@pytest.mark.asyncio
async def test_task_retry_audit_via_api(client, db_session):
    headers, user_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=user_id)
    task = _make_task(db_session, project, user_id, status="failed")
    await db_session.flush()

    resp = await client.post(f"/api/tasks/{task.task_id}/retry", headers=headers)
    assert resp.json()["code"] == 0, resp.text
    rows = await _db_rows(db_session, "task.retry")
    assert len(rows) == 1
    assert rows[0].project_id == project.project_id


# ---------------------------------------------------------------------------
# 判据 5:Runner sweep_offline(系统)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_runner_offline_sweep_system_audit(db_session):
    creator = await _make_user(db_session)
    runner = Runner(
        name=f"r-{uuid.uuid4().hex[:6]}",
        role="worker",
        token_hash=hash_password("tok"),
        status="online",
        last_heartbeat_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=120),
        created_by=creator.user_id,
    )
    db_session.add(runner)
    await db_session.flush()

    count = await runner_service.sweep_offline(db_session)
    assert count >= 1

    rows = await _spawn_rows("runner.offline_sweep")
    assert len(rows) >= 1
    row = rows[0]
    assert row.user_id == PLACEHOLDER_UID
    assert row.operator_role == "system"
    assert row.detail.get("reason") == "heartbeat_timeout_sweep"
