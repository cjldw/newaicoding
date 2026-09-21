"""
R12 项目成员与协作接口测试
==========================
覆盖:
- 邀请(成功/12001 未注册/12002 已是成员/12003 超限)
- 移除(成功/12004 最后一个 owner)
- 改角色(成功/12004 降级最后 owner)
- 转让 owner(成功/12005 非成员)
- viewer 写操作拦截(前后端双重校验的后端侧)
- 手机号精确搜索 /api/users/search

说明:R1 bootstrap 逻辑"首个注册用户=superadmin"——
auth_headers 用户即项目 owner 兼首位用户;second/third 用普通用户。
GitLab 同步为非关键路径(失败仅告警),同步类用例用 mock 走通代码路径即可。
"""
import uuid

import pytest
import httpx

from tests.test_projects_api import (
    _insert_project,
    _insert_repo,
    _seed_gitlab_settings,
)


async def _register_user(client):
    """注册普通用户(非首位),返回 {headers, phone, user_id}"""
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    return {"headers": headers, "phone": phone, "user_id": user_id}


async def _insert_member(db_session, project_id, user_id, role="viewer", invited_by=None):
    """直插成员行(造数据用,绕过邀请流程)"""
    from app.models.project_member import ProjectMember

    m = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by or user_id,
    )
    db_session.add(m)
    await db_session.flush()
    return m


# ---------------------------------------------------------------------------
# 邀请成员
# ---------------------------------------------------------------------------
class TestInviteMember:
    @pytest.mark.asyncio
    async def test_invite_member_success(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """邀请成员成功(手机号精确匹配)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": target["phone"], "role": "editor"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["user_id"] == target["user_id"]
        assert data["data"]["role"] == "editor"
        assert "邀请成功" in data["message"]

        # 列表应含 owner(懒回填)+ 新成员
        resp = await client.get(f"/api/projects/{project.project_id}/members", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 2
        roles = {i["user_id"]: i["role"] for i in items}
        assert roles[registered_user["user_id"]] == "owner"
        assert roles[target["user_id"]] == "editor"

    @pytest.mark.asyncio
    async def test_invite_member_user_not_found(self, client, auth_headers, db_session, registered_user):
        """用户不存在:返回 12001"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": "19900000000", "role": "viewer"},
        )
        data = resp.json()
        assert data["code"] == 12001
        assert "未注册" in data["message"]

    @pytest.mark.asyncio
    async def test_invite_member_already_member(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """用户已是成员:返回 12002"""
        project = await _insert_project(db_session, registered_user["user_id"])
        target = await _register_user(client)
        for _ in range(2):
            resp = await client.post(
                f"/api/projects/{project.project_id}/members",
                headers=auth_headers,
                json={"phone": target["phone"], "role": "viewer"},
            )
        assert resp.json()["code"] == 12002

    @pytest.mark.asyncio
    async def test_invite_member_limit_exceeded(self, client, auth_headers, db_session, registered_user):
        """成员数超限(>50):返回 12003"""
        project = await _insert_project(db_session, registered_user["user_id"])
        owner_row = await _insert_member(db_session, project.project_id, registered_user["user_id"], "owner")
        for i in range(49):
            await _insert_member(db_session, project.project_id, f"00000000-0000-0000-0000-{i:012d}", "viewer")
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": "19900000000", "role": "viewer"},
        )
        # 未注册用户应先于超限校验?分片顺序:查用户→已成员→超限。这里用已注册手机号测超限
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": target["phone"], "role": "viewer"},
        )
        assert resp.json()["code"] == 12003

    @pytest.mark.asyncio
    async def test_invite_by_non_owner_denied(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """非 owner(非成员)邀请:403"""
        project = await _insert_project(db_session, registered_user["user_id"])
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=second_user_headers,
            json={"phone": target["phone"], "role": "viewer"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901


# ---------------------------------------------------------------------------
# 移除成员
# ---------------------------------------------------------------------------
class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_remove_member_success(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """移除成员成功"""
        project = await _insert_project(db_session, registered_user["user_id"])
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": target["phone"], "role": "viewer"},
        )
        assert resp.json()["code"] == 0
        resp = await client.delete(
            f"/api/projects/{project.project_id}/members/{target['user_id']}",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["code"] == 0
        assert "移除" in data["message"]
        # 列表只剩 owner
        resp = await client.get(f"/api/projects/{project.project_id}/members", headers=auth_headers)
        assert len(resp.json()["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_remove_last_owner(self, client, auth_headers, db_session, registered_user):
        """移除最后一个 owner:返回 12004"""
        project = await _insert_project(db_session, registered_user["user_id"])
        # 先拉列表触发 owner 行懒回填
        await client.get(f"/api/projects/{project.project_id}/members", headers=auth_headers)
        resp = await client.delete(
            f"/api/projects/{project.project_id}/members/{registered_user['user_id']}",
            headers=auth_headers,
        )
        assert resp.json()["code"] == 12004
        assert "所有者" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 改角色
# ---------------------------------------------------------------------------
class TestChangeRole:
    @pytest.mark.asyncio
    async def test_change_role_success(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """改角色成功(viewer → editor)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": target["phone"], "role": "viewer"},
        )
        assert resp.json()["code"] == 0
        resp = await client.patch(
            f"/api/projects/{project.project_id}/members/{target['user_id']}",
            headers=auth_headers,
            json={"role": "editor"},
        )
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["role"] == "editor"
        assert "角色已更新" in data["message"]

    @pytest.mark.asyncio
    async def test_change_last_owner_role_denied(self, client, auth_headers, db_session, registered_user):
        """降级最后一个 owner:返回 12004"""
        project = await _insert_project(db_session, registered_user["user_id"])
        await client.get(f"/api/projects/{project.project_id}/members", headers=auth_headers)
        resp = await client.patch(
            f"/api/projects/{project.project_id}/members/{registered_user['user_id']}",
            headers=auth_headers,
            json={"role": "editor"},
        )
        assert resp.json()["code"] == 12004


# ---------------------------------------------------------------------------
# 转让 owner
# ---------------------------------------------------------------------------
class TestTransferOwnership:
    @pytest.mark.asyncio
    async def test_transfer_ownership_success(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """转让 owner 成功:自己降为 editor,目标成为 owner

        注意:owner 用 _register_user 注册的普通用户(auth_headers 用户是首位注册用户=
        superadmin 虚拟 owner,D16 超管转让不建成员行,列表无其记录)。
        """
        owner_user = await _register_user(client)
        project = await _insert_project(db_session, owner_user["user_id"])
        target = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=owner_user["headers"],
            json={"phone": target["phone"], "role": "editor"},
        )
        assert resp.json()["code"] == 0
        resp = await client.post(
            f"/api/projects/{project.project_id}/transfer-ownership",
            headers=owner_user["headers"],
            json={"new_owner_user_id": target["user_id"]},
        )
        data = resp.json()
        assert data["code"] == 0
        assert "转让成功" in data["message"]
        # 成员列表角色对调
        resp = await client.get(f"/api/projects/{project.project_id}/members", headers=owner_user["headers"])
        roles = {i["user_id"]: i["role"] for i in resp.json()["data"]["items"]}
        assert roles[target["user_id"]] == "owner"
        assert roles[owner_user["user_id"]] == "editor"

    @pytest.mark.asyncio
    async def test_transfer_ownership_to_non_member(self, client, auth_headers, db_session, registered_user):
        """转让给非成员:返回 12005"""
        project = await _insert_project(db_session, registered_user["user_id"])
        outsider = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/transfer-ownership",
            headers=auth_headers,
            json={"new_owner_user_id": outsider["user_id"]},
        )
        assert resp.json()["code"] == 12005


# ---------------------------------------------------------------------------
# viewer 写操作拦截(验收 7:后端侧)
# ---------------------------------------------------------------------------
class TestViewerWriteInterception:
    @pytest.mark.asyncio
    async def test_viewer_cannot_add_repo(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """viewer 追加绑定仓库:403(双重拦截的后端侧)"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        viewer = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": viewer["phone"], "role": "viewer"},
        )
        assert resp.json()["code"] == 0
        # 权限拦截发生在 GitLab 调用之前,无需 mock
        resp = await client.post(
            f"/api/projects/{project.project_id}/repos",
            headers=viewer["headers"],
            json={"role": "test", "gitlab_repo_url": "https://gitlab.example.com/g/r.git"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901

    @pytest.mark.asyncio
    async def test_editor_can_add_repo(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """editor 可追加绑定仓库(R2 权限矩阵:owner/editor ✅)"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        editor = await _register_user(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": editor["phone"], "role": "editor"},
        )
        assert resp.json()["code"] == 0

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and "/api/v4/projects/" in str(request.url):
                return httpx.Response(200, json={
                    "id": 999,
                    "http_url_to_repo": "https://gitlab.example.com/g/r.git",
                    "permissions": {"project_access": {"access_level": 40}},
                })
            return httpx.Response(404)

        with httpx.MockTransport(handler):
            resp = await client.post(
                f"/api/projects/{project.project_id}/repos",
                headers=editor["headers"],
                json={"role": "test", "gitlab_repo_url": "https://gitlab.example.com/g/r.git"},
            )
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["gitlab_repo_id"] == 999


# ---------------------------------------------------------------------------
# GitLab 同步路径(非关键,走通即可)
# ---------------------------------------------------------------------------
class TestGitlabMemberSync:
    @pytest.mark.asyncio
    async def test_invite_syncs_to_bound_repo(self, client, auth_headers, db_session, registered_user):
        """邀请后同步:目标用户绑定了 GitLab username → 走 lookup+add 成员路径"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        await _insert_repo(db_session, project.project_id, registered_user["user_id"], role="main", gitlab_repo_id=555)

        target = await _register_user(client)
        # 给目标用户绑定 gitlab_username(直改 DB)
        from sqlalchemy import text
        await db_session.execute(
            text("UPDATE users SET gitlab_username = 'syncuser' WHERE user_id = :uid"),
            {"uid": target["user_id"]},
        )
        await db_session.flush()

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, str(request.url)))
            if request.method == "GET" and "/api/v4/users" in str(request.url):
                return httpx.Response(200, json=[{"id": 7, "username": "syncuser"}])
            if request.method == "POST" and "/members" in str(request.url):
                return httpx.Response(201, json={"id": 7, "access_level": 30})
            return httpx.Response(404)

        with httpx.MockTransport(handler):
            resp = await client.post(
                f"/api/projects/{project.project_id}/members",
                headers=auth_headers,
                json={"phone": target["phone"], "role": "editor"},
            )
        assert resp.json()["code"] == 0
        # 至少发生了 lookup 与 add member 调用
        assert any(m == "GET" and "/api/v4/users" in u for m, u in calls)
        assert any(m == "POST" and "/members" in u for m, u in calls)


# ---------------------------------------------------------------------------
# 手机号精确搜索
# ---------------------------------------------------------------------------
class TestSearchUserByPhone:
    @pytest.mark.asyncio
    async def test_search_found(self, client, auth_headers, registered_user):
        """精确命中"""
        # registered_user 的手机号已被 fixture 返回
        phone = registered_user["phone"]
        resp = await client.get(f"/api/users/search?phone={phone}", headers=auth_headers)
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["user_id"] == registered_user["user_id"]
        assert data["data"]["phone_masked"].endswith(registered_user["phone_masked"][-4:])

    @pytest.mark.asyncio
    async def test_search_not_found(self, client, auth_headers):
        """未命中返回 null"""
        resp = await client.get("/api/users/search?phone=19900000000", headers=auth_headers)
        assert resp.json()["code"] == 0
        assert resp.json()["data"] is None

    @pytest.mark.asyncio
    async def test_search_partial_phone_returns_null(self, client, auth_headers):
        """不足 11 位不查询,返回 null(防前缀枚举)"""
        resp = await client.get("/api/users/search?phone=138", headers=auth_headers)
        assert resp.json()["data"] is None

    @pytest.mark.asyncio
    async def test_search_no_auth_returns_401(self, client):
        resp = await client.get("/api/users/search?phone=13800000000")
        assert resp.status_code == 401
