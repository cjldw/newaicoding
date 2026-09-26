"""
R3 评审通过站内通知 — TDD Red 测试
====================================================
覆盖(DEVPLAN/R3.md 完成判据 + 任务点;评审动作 POST /api/requirements/{id}/review 通过分支):
1. 关联 2 人评审通过 → send_notification 被调 2 次,kwargs:recipient_id 各为成员 /
   type=review_approved / title 含需求名 / link=/requirements/{id}
2. 操作人在名单内 → 操作人未收到(只调 1 次,给另一人)
3. 名单含已移出项目成员 → 该人未收到,其余正常
4. 空名单 → send_notification 零调用,评审本身成功
5. mock send_notification 抛异常 → 评审仍 200 且状态 approved(失败不阻塞)
6. 存量需求 related_user_ids=NULL → 视同空名单(零调用 + 评审成功)

mock 口径:unittest.mock.patch("app.services.notification_service.send_notification",
new_callable=AsyncMock)(先例:test_notifications_api.py monkeypatch notification_service
模块属性、test_r9f1_claude_session.py patch app.services.* 服务函数)。

注意(Red 阶段):requirement_service.review_requirement approved 分支尚未挂钩通知
(置状态后直接 audit → flush),用例 1-3 预期失败(await_count=0 与预期次数不符);
用例 4/5/6 为负向守卫,Red 阶段零调用即天然满足,预期通过,Green 后继续把守。
"""
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy

from app.core.encryption import encrypt_token
from app.models.requirement import Requirement
from app.models.user import User
from tests.test_requirement_related_users import (
    _add_member,
    _create_requirement,
    _mk_user,
)
from tests.test_requirements_api import _setup_project


# ---------------------------------------------------------------------------
# 辅助(fixture 口径照抄 test_requirement_related_users_patch.py)
# ---------------------------------------------------------------------------
async def _get_req_orm(db_session, req_id: str) -> Requirement:
    return (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req_id)
    )).scalars().first()


async def _mk_reviewing_requirement(client, db_session, auth_headers, registered_user,
                                    related: list) -> dict:
    """建项目 + 建需求(带名单)+ 置 reviewing + 评审人绑 token。

    related:关联用户凭据列表(成员行在此统一 _add_member 后再建需求——R1 名单存储
    按项目成员过滤,非成员在创建期即被静默剔除;操作人已在下面补行,跳重)。
    操作人 = registered_user(owner,同时补成员行保证名单存储/过滤口径不含偏差)。
    related 传 [] → 创建空名单;传 None → 不传字段(配合用例 6 ORM 置 NULL)。
    返回 {"project", "req": Requirement ORM}。
    """
    project = await _setup_project(db_session, registered_user)
    # owner 补成员行:R1 名单存储按项目成员过滤,操作人须在成员表内才可能留在名单里
    _add_member(db_session, project.project_id, registered_user["user_id"], role="editor")
    # 关联用户补成员行(R1 样板口径 test_requirement_related_users.py:84-85;操作人跳重)
    for u in related or []:
        if u["user_id"] != registered_user["user_id"]:
            _add_member(db_session, project.project_id, u["user_id"], role="editor")
    await db_session.flush()

    payload = {"title": "评审通知需求", "description": "d"}
    if related is not None:
        payload["related_user_ids"] = [u["user_id"] for u in related]
    body = await _create_requirement(client, auth_headers, project, payload)
    assert body["code"] == 0, body
    req = await _get_req_orm(db_session, body["data"]["req_id"])
    assert req is not None, body

    # 评审人(owner)绑定 GitLab token(通过分支 1012 校验)+ 置 reviewing
    reviewer = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    reviewer.gitlab_token_encrypted = encrypt_token("glpat-reviewer")
    req.status = "reviewing"
    await db_session.flush()
    return {"project": project, "req": req}


async def _review_approve(client, auth_headers, req_id: str):
    """评审通过(容器不存在:走跳过 commit 的异常路径,仅状态流转)"""
    return await client.post(
        f"/api/requirements/{req_id}/review",
        headers=auth_headers,
        json={"approved": True},
    )


def _kwargs_of(call) -> dict:
    return call.kwargs


# ---------------------------------------------------------------------------
# 1. 关联 2 人评审通过 → 2 次通知,内容/链接正确
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_notifies_two_related_users(client, auth_headers, db_session, registered_user):
    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env = await _mk_reviewing_requirement(client, db_session, auth_headers, registered_user, [u1, u2])
    project, req = env["project"], env["req"]

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.text
    await db_session.refresh(req)
    assert req.status == "approved"

    # 2 人各收到 1 条
    assert mock_send.await_count == 2, f"期望 2 次通知,实际 {mock_send.await_count}"
    recipients = set()
    for call in mock_send.await_args_list:
        kw = _kwargs_of(call)
        recipients.add(kw["recipient_id"])
        assert kw["type"] == "review_approved", kw
        assert kw["level"] == "normal", kw
        assert "评审通知需求" in kw["title"], kw  # title 含需求名
        assert kw["content"] == "可以开始开发了", kw  # 契约固定文案
        assert kw["link"] == f"/requirements/{req.req_id}", kw
        assert kw["project_id"] == project.project_id, kw
    assert recipients == {u1["user_id"], u2["user_id"]}, recipients


# ---------------------------------------------------------------------------
# 2. 操作人在名单内 → 操作人未收到(只调 1 次,给另一人)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_excludes_operator(client, auth_headers, db_session, registered_user):
    u1 = await _mk_user(client)
    # 名单混入操作人(owner 自身凭据 shape;成员行已在 helper 补过)
    env = await _mk_reviewing_requirement(
        client, db_session, auth_headers, registered_user,
        [u1, {"user_id": registered_user["user_id"]}],
    )
    req = env["req"]

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert mock_send.await_count == 1, f"操作人应被排除,期望 1 次通知,实际 {mock_send.await_count}"
    kw = _kwargs_of(mock_send.await_args_list[0])
    assert kw["recipient_id"] == u1["user_id"], kw
    assert kw["recipient_id"] != registered_user["user_id"], kw


# ---------------------------------------------------------------------------
# 3. 名单含已移出项目成员 → 该人未收到,其余正常
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_skips_removed_member(client, auth_headers, db_session, registered_user):
    from app.models.project_member import ProjectMember

    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env = await _mk_reviewing_requirement(client, db_session, auth_headers, registered_user, [u1, u2])
    project, req = env["project"], env["req"]

    # 评审前把 u2 移出项目(删成员行)
    u2_member = (await db_session.execute(
        sqlalchemy.select(ProjectMember).where(
            ProjectMember.project_id == project.project_id,
            ProjectMember.user_id == u2["user_id"],
        )
    )).scalars().first()
    assert u2_member is not None
    await db_session.delete(u2_member)
    await db_session.flush()

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert mock_send.await_count == 1, f"已移出成员应被跳过,期望 1 次,实际 {mock_send.await_count}"
    kw = _kwargs_of(mock_send.await_args_list[0])
    assert kw["recipient_id"] == u1["user_id"], kw
    assert kw["recipient_id"] != u2["user_id"], kw


# ---------------------------------------------------------------------------
# 4. 空名单 → 零调用,评审本身成功(负向守卫)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_empty_list_no_notify(client, auth_headers, db_session, registered_user):
    env = await _mk_reviewing_requirement(client, db_session, auth_headers, registered_user, [])
    req = env["req"]

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.text
    await db_session.refresh(req)
    assert req.status == "approved"
    assert mock_send.await_count == 0, f"空名单应零通知,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 5. mock send_notification 抛异常 → 评审仍 200 且 approved(失败不阻塞)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_survives_notification_error(client, auth_headers, db_session, registered_user):
    u1 = await _mk_user(client)
    env = await _mk_reviewing_requirement(client, db_session, auth_headers, registered_user, [u1])
    req = env["req"]

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = RuntimeError("notify boom")
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.text
    await db_session.refresh(req)
    assert req.status == "approved", req.status


# ---------------------------------------------------------------------------
# 6. 存量需求 related_user_ids=NULL → 视同空名单
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_approve_null_related_user_ids_treated_as_empty(client, auth_headers, db_session, registered_user):
    env = await _mk_reviewing_requirement(client, db_session, auth_headers, registered_user, None)
    req = env["req"]
    # 模拟存量数据:直接 ORM 置 NULL
    req.related_user_ids = None
    await db_session.flush()

    with patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        resp = await _review_approve(client, auth_headers, req.req_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.text
    await db_session.refresh(req)
    assert req.status == "approved"
    assert mock_send.await_count == 0, f"NULL 名单应视同空名单零通知,实际 {mock_send.await_count}"
