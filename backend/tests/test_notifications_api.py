"""
R18 站内信与通知测试
==========================
- 发送通知(写表)+ 未读计数
- 已读/全部已读/删除
- 个人通知设置读写 + 测试钉钉(mock httpx)
- 项目钉钉设置(owner)
- critical 触发钉钉(fake)+ 连续失败 3 次停用
"""
import uuid

import httpx

from app.models.project import Project
import pytest
import sqlalchemy

from app.models.notification import Notification, UserNotificationSettings
from app.models.project import Project
from app.services import notification_service
from tests.test_projects_api import _insert_project, _seed_gitlab_settings


async def _setup_project(db_session, registered_user):
    await _seed_gitlab_settings(db_session)
    return await _insert_project(db_session, registered_user['user_id'])


@pytest.mark.asyncio
async def test_send_notification_success(client, auth_headers, db_session, registered_user):
    """发送通知:写表;未读计数正确;已读后计数减"""
    project = await _setup_project(db_session, registered_user)
    notification = await notification_service.send_notification(
        db_session,
        recipient_id=registered_user["user_id"],
        type="task_failed",
        level="normal",
        title="任务失败",
        content="任务 xxx 执行失败",
        link="/tasks/t-1",
        project_id=project.project_id,
        task_id="t-1",
    )
    assert notification.notification_id

    resp = await client.get("/api/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["unread_count"] == 1

    # 已读
    resp = await client.post(
        f"/api/notifications/{notification.notification_id}/read", headers=auth_headers
    )
    assert resp.json()["code"] == 0
    resp = await client.get("/api/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_all_read_and_delete(client, auth_headers, db_session, registered_user):
    """全部已读 + 删除"""
    project = await _setup_project(db_session, registered_user)
    for i in range(3):
        await notification_service.send_notification(
            db_session, recipient_id=registered_user["user_id"], type="task_failed",
            level="normal", title=f"t{i}", content="c",
            project_id=project.project_id,
        )
    resp = await client.post("/api/notifications/read-all", headers=auth_headers)
    assert resp.json()["code"] == 0
    resp = await client.get("/api/notifications/unread-count", headers=auth_headers)
    assert resp.json()["data"]["unread_count"] == 0

    # 删除一条
    resp = await client.get("/api/notifications", headers=auth_headers)
    items = resp.json()["data"]["items"]
    first = items[0]["notification_id"]
    resp = await client.delete(f"/api/notifications/{first}", headers=auth_headers)
    assert resp.json()["code"] == 0
    resp = await client.get("/api/notifications", headers=auth_headers)
    assert resp.json()["data"]["total"] == 2


@pytest.mark.asyncio
async def test_notification_settings_and_test_dingtalk(client, auth_headers, db_session, registered_user, monkeypatch):
    """个人通知设置读写 + 测试钉钉(mock 成功/失败)"""
    # 保存设置
    resp = await client.put(
        "/api/users/me/notification-settings",
        headers=auth_headers,
        json={"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=x",
              "dingtalk_enabled": True},
    )
    assert resp.json()["code"] == 0

    # 测试钉钉:mock 成功
    import httpx as _httpx

    class FakeResp:
        status_code = 200

    def make_client(*a, **kw):
        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kw):
                return FakeResp()

        return FakeClient()

    real = _httpx.AsyncClient
    _httpx.AsyncClient = make_client
    try:
        resp = await client.post(
            "/api/users/me/notification-settings/test-dingtalk",
            headers=auth_headers,
            json={"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=x"},
        )
    finally:
        _httpx.AsyncClient = real
    assert resp.json()["code"] == 0
    assert "测试消息已发送" in resp.json()["message"]

    # 无效 webhook(mock 4xx)→ 18001
    class BadResp:
        status_code = 400

    def make_bad_client(*a, **kw):
        class BadClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kw):
                return BadResp()

        return BadClient()

    _httpx.AsyncClient = make_bad_client
    try:
        resp = await client.post(
            "/api/users/me/notification-settings/test-dingtalk",
            headers=auth_headers,
            json={"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=bad"},
        )
    finally:
        _httpx.AsyncClient = real
    assert resp.json()["code"] == 18001


@pytest.mark.asyncio
async def test_dingtalk_fail_3_times_disables(client, auth_headers, db_session, registered_user, monkeypatch):
    """critical 通知:钉钉连续失败 3 次 → 自动停用(dingtalk_enabled=False)"""
    project = await _setup_project(db_session, registered_user)

    # 预置启用钉钉的设置行
    settings = UserNotificationSettings(
        user_id=registered_user["user_id"], dingtalk_enabled=True,
        dingtalk_webhook="https://oapi.dingtalk.com/robot/send?access_token=x",
    )
    db_session.add(settings)
    await db_session.flush()

    async def fake_post_fail(webhook, notification):
        return False

    monkeypatch.setattr(notification_service, "_post_dingtalk", fake_post_fail)
    for _ in range(3):
        await notification_service.send_notification(
            db_session, recipient_id=registered_user["user_id"], type="deploy_failed",
            level="critical", title="部署失败", content="c",
            project_id=project.project_id,
        )

    await db_session.refresh(settings)
    assert settings.dingtalk_enabled is False
    assert settings.dingtalk_fail_count >= 3


@pytest.mark.asyncio
async def test_project_dingtalk_settings_owner_only(client, auth_headers, db_session, registered_user):
    """owner 配置项目钉钉;非 owner 403"""
    project = await _setup_project(db_session, registered_user)
    resp = await client.put(
        f"/api/projects/{project.project_id}/dingtalk-settings",
        headers=auth_headers,
        json={"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=p",
              "dingtalk_enabled": True},
    )
    assert resp.json()["code"] == 0

    from tests.test_projects_api import _register_and_login

    other_headers, _uid = await _register_and_login(client)
    resp = await client.put(
        f"/api/projects/{project.project_id}/dingtalk-settings",
        headers=other_headers,
        json={"dingtalk_webhook": "https://oapi.dingtalk.com/robot/send?access_token=p"},
    )
    assert resp.status_code == 403
