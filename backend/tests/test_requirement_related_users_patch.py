"""
R2 关联用户详情可编辑(PATCH 侧)— TDD Red 测试
====================================================
覆盖(DEVPLAN/R2.md 完成判据 + 任务点):
1. PATCH related_user_ids 增(加 1 人)→ 200,详情含新名单
2. PATCH 删(减 1 人)→ 生效
3. PATCH 置空数组 → 清空(合法)
4. PATCH 含非成员 id → 静默剔除(与 R1 create 同口径,不 400)
5. viewer 调 PATCH → HTTP 403 / code=1901(鉴权口径不变,守卫回归)
6. 非 owner 的 editor 正常可改(现有 editor+ 权限口径)

注意(Red 阶段):UpdateRequirementRequest 尚无 related_user_ids 字段
(schemas/requirement.py:21-27),api/requirements.py PATCH 逐字段赋值处也未接 ——
用例 1-4 预期失败(详情断言不符:名单不变);用例 5/6 为权限守卫,现口径即应通过。
Green 后 1-4 转绿。
"""
import uuid

import httpx
import pytest

from tests.test_requirement_related_users import (
    _add_member,
    _assert_id_set,
    _create_requirement,
    _get_detail,
    _mk_user,
)
from tests.test_requirements_api import _setup_project


async def _patch_requirement(client, auth_headers, req_id: str, payload: dict):
    """PATCH /api/requirements/{req_id},返回 httpx.Response(不断言,交给用例)"""
    return await client.patch(
        f"/api/requirements/{req_id}", headers=auth_headers, json=payload,
    )


async def _mk_project_with_members(client, db_session, registered_user, member_roles: dict) -> dict:
    """建项目 + 批量补成员,返回 {project, users:{alias: user_cred}}"""
    project = await _setup_project(db_session, registered_user)
    users = {}
    for alias, role in member_roles.items():
        u = await _mk_user(client)
        _add_member(db_session, project.project_id, u["user_id"], role=role)
        users[alias] = u
    await db_session.flush()
    return {"project": project, "users": users}


# ---------------------------------------------------------------------------
# 1. PATCH 增:加 1 名成员 → 200,详情含新名单
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_add_one_related_user(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(client, db_session, registered_user, {"u1": "editor"})
    project, u1 = env["project"], env["users"]["u1"]

    body = await _create_requirement(client, auth_headers, project, {
        "title": "增关联用户", "description": "d",
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await _patch_requirement(client, auth_headers, req_id, {
        "related_user_ids": [u1["user_id"]],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0, resp.text

    detail = await _get_detail(client, auth_headers, req_id)
    _assert_id_set(detail["related_user_ids"], [u1["user_id"]])


# ---------------------------------------------------------------------------
# 2. PATCH 删:减 1 人 → 生效
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_remove_one_related_user(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(
        client, db_session, registered_user, {"u1": "editor", "u2": "viewer"},
    )
    project, u1, u2 = env["project"], env["users"]["u1"], env["users"]["u2"]

    body = await _create_requirement(client, auth_headers, project, {
        "title": "删关联用户", "description": "d",
        "related_user_ids": [u1["user_id"], u2["user_id"]],
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await _patch_requirement(client, auth_headers, req_id, {
        "related_user_ids": [u1["user_id"]],  # 只留 u1
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, req_id)
    _assert_id_set(detail["related_user_ids"], [u1["user_id"]])


# ---------------------------------------------------------------------------
# 3. PATCH 置空数组 → 清空(合法)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_empty_array_clears_related_users(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(client, db_session, registered_user, {"u1": "editor"})
    project, u1 = env["project"], env["users"]["u1"]

    body = await _create_requirement(client, auth_headers, project, {
        "title": "清空关联用户", "description": "d",
        "related_user_ids": [u1["user_id"]],
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await _patch_requirement(client, auth_headers, req_id, {"related_user_ids": []})
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, req_id)
    assert detail["related_user_ids"] == [], detail


# ---------------------------------------------------------------------------
# 4. PATCH 含非成员 id → 静默剔除(与 R1 create 同口径)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_with_non_member_id_silently_dropped(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(client, db_session, registered_user, {"u1": "editor"})
    project, u1 = env["project"], env["users"]["u1"]
    outsider_id = str(uuid.uuid4())  # 未加入项目的用户 id(甚至不存在)

    body = await _create_requirement(client, auth_headers, project, {
        "title": "PATCH 混入非成员", "description": "d",
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await _patch_requirement(client, auth_headers, req_id, {
        "related_user_ids": [u1["user_id"], outsider_id],
    })
    assert resp.status_code == 200, resp.text  # 不 400
    assert resp.json()["code"] == 0, resp.text

    detail = await _get_detail(client, auth_headers, req_id)
    _assert_id_set(detail["related_user_ids"], [u1["user_id"]])  # outsider 被剔除


# ---------------------------------------------------------------------------
# 5. viewer 调 PATCH → 403 / code=1901(鉴权口径不变,守卫)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_related_users_by_viewer_403(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(client, db_session, registered_user, {"vw": "viewer"})
    project, vw = env["project"], env["users"]["vw"]

    body = await _create_requirement(client, auth_headers, project, {
        "title": "viewer 禁改", "description": "d",
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await client.post("/api/auth/login", json={
        "phone": vw["phone"], "password": vw["password"],
    })
    assert resp.json()["code"] == 0, resp.text
    viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    resp = await _patch_requirement(client, viewer_headers, req_id, {
        "related_user_ids": [vw["user_id"]],
    })
    body = resp.json()
    assert resp.status_code == 403, body
    assert body["code"] == 1901, body  # ErrCode.NO_PROJECT_PERMISSION

    # 名单未被改动
    detail = await _get_detail(client, auth_headers, req_id)
    assert detail["related_user_ids"] == [], detail


# ---------------------------------------------------------------------------
# 6. 非 owner 的 editor 正常可改(现有 editor+ 口径)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_related_users_by_non_owner_editor(client, auth_headers, db_session, registered_user):
    env = await _mk_project_with_members(client, db_session, registered_user, {"ed": "editor"})
    project, ed = env["project"], env["users"]["ed"]

    body = await _create_requirement(client, auth_headers, project, {
        "title": "editor 可改", "description": "d",
    })
    assert body["code"] == 0, body
    req_id = body["data"]["req_id"]

    resp = await client.post("/api/auth/login", json={
        "phone": ed["phone"], "password": ed["password"],
    })
    assert resp.json()["code"] == 0, resp.text
    editor_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    resp = await _patch_requirement(client, editor_headers, req_id, {
        "related_user_ids": [ed["user_id"]],
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, editor_headers, req_id)
    _assert_id_set(detail["related_user_ids"], [ed["user_id"]])
