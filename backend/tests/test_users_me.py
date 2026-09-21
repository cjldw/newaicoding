"""
R1 用户信息接口测试 — GET/PATCH /api/users/me
===============================================
覆盖场景:
- 获取当前用户信息(需 JWT 鉴权)
- 手机号打码验证(前3位 + **** + 后4位)
- 响应最小化(不含 password_hash、gitlab_token_encrypted)
- 更新个人信息(nickname、avatar_url)
- 未登录访问返回 401
- token_version 失效后返回 401
"""
import pytest


# ---------------------------------------------------------------------------
# 获取当前用户信息 — GET /api/users/me
# ---------------------------------------------------------------------------
class TestGetUserInfo:
    """获取当前用户信息"""

    @pytest.mark.asyncio
    async def test_get_me_success(self, client, auth_headers, registered_user):
        """已登录用户获取自身信息"""
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["user_id"] == registered_user["user_id"]
        # 手机号打码
        assert data["data"]["phone"] == registered_user["phone_masked"]
        # 包含 GitLab 相关字段
        assert "gitlab_username" in data["data"]
        assert "gitlab_token_bound" in data["data"]
        assert "gitlab_token_scopes" in data["data"]
        assert "gitlab_token_bound_at" in data["data"]

    @pytest.mark.asyncio
    async def test_get_me_phone_masking(self, client, auth_headers, registered_user):
        """GET /api/users/me 手机号打码格式正确"""
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        phone = resp.json()["data"]["phone"]
        # 格式:前3位 + **** + 后4位
        assert len(phone) == 11
        assert phone[:3] == registered_user["phone"][:3]
        assert phone[3:7] == "****"
        assert phone[-4:] == registered_user["phone"][-4:]

    @pytest.mark.asyncio
    async def test_get_me_response_no_sensitive_fields(self, client, auth_headers):
        """GET /api/users/me 响应最小化:不含敏感字段"""
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        resp_text = str(data)
        # 不含密码哈希
        assert "password_hash" not in resp_text
        # 不含加密的 GitLab token
        assert "gitlab_token_encrypted" not in resp_text
        # 不含原始密码
        assert "password" not in data.get("data", {})

    @pytest.mark.asyncio
    async def test_get_me_no_auth_returns_401(self, client):
        """未登录访问 GET /api/users/me:返回 401"""
        resp = await client.get("/api/users/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token_returns_401(self, client):
        """无效 JWT 访问:返回 401"""
        resp = await client.get("/api/users/me", headers={
            "Authorization": "Bearer invalid-token",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_expired_token_returns_401(self, client, registered_user):
        """过期 JWT 访问:返回 401"""
        import time
        import jwt as pyjwt
        import os

        secret = os.environ["JWT_SECRET_KEY"]
        expired_token = pyjwt.encode(
            {
                "user_id": registered_user["user_id"],
                "exp": int(time.time()) - 3600,
            },
            secret,
            algorithm="HS256",
        )
        resp = await client.get("/api/users/me", headers={
            "Authorization": f"Bearer {expired_token}",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_token_version_mismatch_returns_401(
        self, client, db_session, registered_user, auth_headers
    ):
        """token_version 不匹配(如被禁用后恢复):旧 token 返回 401"""
        from app.models.user import User
        from sqlalchemy import select

        # 修改用户 token_version(模拟禁用/改密等操作)
        result = await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )
        user = result.scalar_one()
        original_version = user.token_version
        user.token_version = original_version + 1
        await db_session.commit()

        # 用旧 token 访问(旧 token 中 token_version 不匹配)
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_gitlab_token_bound_false_by_default(self, client, auth_headers):
        """默认未绑定 GitLab token,gitlab_token_bound 为 false"""
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["gitlab_token_bound"] is False
        assert data["gitlab_username"] is None
        assert data["gitlab_token_scopes"] in (None, [])
        assert data["gitlab_token_bound_at"] is None


# ---------------------------------------------------------------------------
# 更新个人信息 — PATCH /api/users/me
# ---------------------------------------------------------------------------
class TestUpdateUserInfo:
    """更新个人信息"""

    @pytest.mark.asyncio
    async def test_update_nickname_success(self, client, auth_headers):
        """更新 nickname 成功"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={
            "nickname": "测试用户",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 验证更新已持久化:通过 GET 重新获取
        get_resp = await client.get("/api/users/me", headers=auth_headers)
        assert get_resp.json()["data"]["nickname"] == "测试用户"

    @pytest.mark.asyncio
    async def test_update_avatar_url_success(self, client, auth_headers):
        """更新 avatar_url 成功"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={
            "avatar_url": "https://example.com/avatar.png",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 验证更新已持久化:通过 GET 重新获取
        get_resp = await client.get("/api/users/me", headers=auth_headers)
        assert get_resp.json()["data"]["avatar_url"] == "https://example.com/avatar.png"

    @pytest.mark.asyncio
    async def test_update_both_fields_success(self, client, auth_headers):
        """同时更新 nickname 和 avatar_url"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={
            "nickname": "新昵称",
            "avatar_url": "https://example.com/new-avatar.png",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 验证更新已持久化:通过 GET 重新获取
        get_resp = await client.get("/api/users/me", headers=auth_headers)
        get_data = get_resp.json()["data"]
        assert get_data["nickname"] == "新昵称"
        assert get_data["avatar_url"] == "https://example.com/new-avatar.png"

    @pytest.mark.asyncio
    async def test_update_empty_body_success(self, client, auth_headers):
        """空请求体:不更新任何字段,返回当前信息"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_update_no_auth_returns_401(self, client):
        """未登录更新:返回 401"""
        resp = await client.patch("/api/users/me", json={
            "nickname": "test",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_response_no_sensitive_fields(self, client, auth_headers):
        """更新响应最小化:不含敏感字段"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={
            "nickname": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        resp_text = str(data)
        assert "password_hash" not in resp_text
        assert "gitlab_token_encrypted" not in resp_text

    @pytest.mark.asyncio
    async def test_update_persisted_across_requests(self, client, auth_headers):
        """更新后,再次 GET 能获取到更新后的值"""
        # 更新
        await client.patch("/api/users/me", headers=auth_headers, json={
            "nickname": "持久化测试",
        })
        # 获取
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["nickname"] == "持久化测试"
