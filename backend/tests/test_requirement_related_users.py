"""
R1 关联用户字段(创建+存储)— TDD Red 测试
==========================================
覆盖(DEVPLAN/R1.md 完成判据):
1. 创建需求带 related_user_ids=[2 名项目成员] → 200,详情返回 2 项
2. 不传 / 空数组 → 创建成功,related_user_ids 为 []
3. 含非项目成员 id → 创建 200 且该 id 被静默剔除(不 400)
4. 含重复 id → 去重
5. ErrCode import 修复回归:
   - api/requirements.py:124(PATCH 评审中需求改标题)→ code=3002 而非 500
   - api/requirements.py:227(非 owner 取消需求)→ HTTP 403 / code=1901 而非 500

注意(Red 阶段):requirements.related_user_ids 列 / schema 字段 / service 剔重逻辑
均未实现 —— 用例 1-4 预期失败(KeyError / 断言不符);用例 5 预期 500(ErrCode
未 import,NameError 走全局兜底)。Green 后全部转绿。
"""
import uuid

import httpx
import pytest

from app.models.requirement import Requirement
from tests.test_requirements_api import _gitlab_branch_handler, _setup_project


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
async def _mk_user(client) -> dict:
    """注册一个普通用户(第 2+ 个注册用户 role=user,非 superadmin),返回凭据"""
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    password = "Test1234"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    return {"user_id": body["data"]["user_id"], "phone": phone, "password": password}


def _add_member(db_session, project_id: str, user_id: str, role: str = "editor") -> None:
    """直接 ORM 补项目成员行(邀请接口走 GitLab 同步,单测不需要)"""
    from app.models.project_member import ProjectMember

    db_session.add(ProjectMember(
        project_id=project_id, user_id=user_id, role=role, invited_by=user_id,
    ))


async def _create_requirement(client, auth_headers, project, payload: dict) -> dict:
    """创建需求(GitLab mock 建分支),返回响应 body"""
    calls: list = []
    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json=payload,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _get_detail(client, auth_headers, req_id: str) -> dict:
    resp = await client.get(f"/api/requirements/{req_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _assert_id_set(actual, expected: list) -> None:
    """related_user_ids 口径:数量 + 集合一致(顺序不强约定,按实现)"""
    assert isinstance(actual, list), f"related_user_ids 应为列表,实际 {actual!r}"
    assert len(actual) == len(expected), f"数量不符: {actual!r} vs {expected!r}"
    assert sorted(actual) == sorted(expected), f"内容不符: {actual!r} vs {expected!r}"


# ---------------------------------------------------------------------------
# 1. 创建带 2 名项目成员 → 详情返回 2 项
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_two_related_members(client, auth_headers, db_session, registered_user):
    """创建需求带 2 名项目成员关联 → 200,详情返回 related_user_ids 2 项"""
    project = await _setup_project(db_session, registered_user)
    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    _add_member(db_session, project.project_id, u1["user_id"], role="editor")
    _add_member(db_session, project.project_id, u2["user_id"], role="viewer")
    await db_session.flush()

    body = await _create_requirement(client, auth_headers, project, {
        "title": "关联用户需求",
        "description": "d",
        "related_user_ids": [u1["user_id"], u2["user_id"]],
    })
    assert body["code"] == 0, body

    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    _assert_id_set(detail["related_user_ids"], [u1["user_id"], u2["user_id"]])


# ---------------------------------------------------------------------------
# 2. 不传 / 空数组 → 默认 []
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_without_related_users_defaults_empty(client, auth_headers, db_session, registered_user):
    """不传 related_user_ids 或传空数组 → 创建成功,详情 related_user_ids 为 []"""
    project = await _setup_project(db_session, registered_user)

    # 不传(默认 [])
    body = await _create_requirement(client, auth_headers, project, {
        "title": "不传关联用户", "description": "d",
    })
    assert body["code"] == 0, body
    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    assert detail["related_user_ids"] == [], detail

    # 显式空数组
    body = await _create_requirement(client, auth_headers, project, {
        "title": "空数组关联用户", "description": "d",
        "related_user_ids": [],
    })
    assert body["code"] == 0, body
    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    assert detail["related_user_ids"] == [], detail


# ---------------------------------------------------------------------------
# 3. 非项目成员 id 静默剔除(不 400)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_non_member_id_silently_dropped(client, auth_headers, db_session, registered_user):
    """related_user_ids 混入非成员 id → 创建仍 200,该 id 被静默剔除"""
    project = await _setup_project(db_session, registered_user)
    u1 = await _mk_user(client)
    _add_member(db_session, project.project_id, u1["user_id"], role="editor")
    outsider_id = str(uuid.uuid4())  # 未加入项目的用户 id(甚至不存在)
    await db_session.flush()

    body = await _create_requirement(client, auth_headers, project, {
        "title": "含非成员关联",
        "description": "d",
        "related_user_ids": [u1["user_id"], outsider_id],
    })
    assert body["code"] == 0, body  # 不 400

    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    _assert_id_set(detail["related_user_ids"], [u1["user_id"]])


# ---------------------------------------------------------------------------
# 4. 重复 id 去重
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_duplicate_ids_dedup(client, auth_headers, db_session, registered_user):
    """related_user_ids 含重复 → 去重后存储"""
    project = await _setup_project(db_session, registered_user)
    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    _add_member(db_session, project.project_id, u1["user_id"], role="editor")
    _add_member(db_session, project.project_id, u2["user_id"], role="editor")
    await db_session.flush()

    body = await _create_requirement(client, auth_headers, project, {
        "title": "重复关联用户",
        "description": "d",
        "related_user_ids": [u1["user_id"], u1["user_id"], u2["user_id"], u1["user_id"]],
    })
    assert body["code"] == 0, body

    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    _assert_id_set(detail["related_user_ids"], [u1["user_id"], u2["user_id"]])


# ---------------------------------------------------------------------------
# 5. ErrCode import 修复回归(api/requirements.py :124 / :227)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_reviewing_requirement_code_3002_not_500(client, auth_headers, db_session, registered_user):
    """:124 分支:PATCH 评审中需求改 title → code=3002(NOT_IN_POLISHING),不再 500"""
    project = await _setup_project(db_session, registered_user)
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="评审中需求", description="d", status="reviewing",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=registered_user["user_id"], project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()

    resp = await client.patch(
        f"/api/requirements/{req.req_id}",
        headers=auth_headers,
        json={"title": "评审期改名"},
    )
    body = resp.json()
    assert resp.status_code != 500, f"ErrCode 未 import → NameError → 500: {body}"
    assert body["code"] == 3002, body  # ErrCode.NOT_IN_POLISHING
    assert "评审中" in body["message"], body


@pytest.mark.asyncio
async def test_cancel_by_non_owner_code_1901_not_500(client, db_session, registered_user):
    """:227 分支:非 owner(viewer 成员)取消需求 → HTTP 403 / code=1901,不再 500"""
    project = await _setup_project(db_session, registered_user)
    viewer = await _mk_user(client)  # 第 2 个注册用户,role=user(非 superadmin)
    _add_member(db_session, project.project_id, viewer["user_id"], role="viewer")
    await db_session.flush()

    resp = await client.post("/api/auth/login", json={
        "phone": viewer["phone"], "password": viewer["password"],
    })
    assert resp.json()["code"] == 0, resp.text
    viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="待取消", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=registered_user["user_id"], project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()

    resp = await client.post(
        f"/api/requirements/{req.req_id}/cancel",
        headers=viewer_headers,
        json={"reason": "优先级调整"},
    )
    body = resp.json()
    assert resp.status_code != 500, f"ErrCode 未 import → NameError → 500: {body}"
    assert resp.status_code == 403, body
    assert body["code"] == 1901, body  # ErrCode.NO_PROJECT_PERMISSION
