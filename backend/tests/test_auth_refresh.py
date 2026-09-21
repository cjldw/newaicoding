"""
R1 刷新 token 接口测试 — POST /api/auth/refresh
=================================================
覆盖场景:
- 刷新成功(返回新 access_token)
- refresh_token 无效(1008)
- refresh_token 过期(1008)
- token_version 失效(用户重新登录后,旧 refresh_token 失效)
- refresh_token 类型校验(不能用 access_token 刷新)
"""
import pytest
import time
import jwt


# ---------------------------------------------------------------------------
# 刷新成功
# ---------------------------------------------------------------------------
class TestRefreshSuccess:
    """刷新 token 成功场景"""

    @pytest.mark.asyncio
    async def test_refresh_success_returns_new_access_token(self, client, registered_user):
        """使用有效 refresh_token 刷新:返回新 access_token"""
        # 先登录获取 refresh_token
        login_resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["code"] == 0
        refresh_token = login_data["data"]["refresh_token"]
        old_access_token = login_data["data"]["access_token"]

        # 刷新 token
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["message"] == "ok"
        # 新 token 与旧 access_token 可能相同(同一秒内 iat/exp 相同)
        # 只验证格式正确即可
        assert "access_token" in data["data"]
        new_access_token = data["data"]["access_token"]
        # JWT 格式正确
        assert new_access_token.count(".") == 2

    @pytest.mark.asyncio
    async def test_refresh_new_access_token_is_valid(self, client, registered_user):
        """刷新后的新 access_token 可用于鉴权"""
        # 登录
        login_resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # 刷新
        refresh_resp = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        new_access_token = refresh_resp.json()["data"]["access_token"]

        # 用新 access_token 访问受保护接口
        resp = await client.get("/api/users/me", headers={
            "Authorization": f"Bearer {new_access_token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["user_id"] == registered_user["user_id"]


# ---------------------------------------------------------------------------
# refresh_token 无效 — 1008
# ---------------------------------------------------------------------------
class TestRefreshInvalidToken:
    """refresh_token 无效场景"""

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_1008(self, client):
        """无效 refresh_token:返回错误码 1008"""
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": "invalid-token-12345",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1008
        assert "无效" in data["message"] or "过期" in data["message"]

    @pytest.mark.asyncio
    async def test_refresh_empty_token_returns_1008(self, client):
        """空 refresh_token:返回错误码 1008"""
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": "",
        })
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] == 1008

    @pytest.mark.asyncio
    async def test_refresh_malformed_jwt_returns_1008(self, client):
        """格式错误的 JWT:返回错误码 1008"""
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": "not.a.jwt",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1008


# ---------------------------------------------------------------------------
# refresh_token 过期 — 1008
# ---------------------------------------------------------------------------
class TestRefreshExpiredToken:
    """refresh_token 过期场景"""

    @pytest.mark.asyncio
    async def test_refresh_expired_token_returns_1008(self, client):
        """过期 refresh_token:返回错误码 1008"""
        import os
        # 手动构造一个过期的 refresh_token
        secret = os.environ["JWT_SECRET_KEY"]
        expired_token = jwt.encode(
            {
                "user_id": "00000000-0000-0000-0000-000000000000",
                "type": "refresh",
                "exp": int(time.time()) - 3600,  # 1 小时前过期
            },
            secret,
            algorithm="HS256",
        )
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": expired_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1008


# ---------------------------------------------------------------------------
# token_version 失效
# ---------------------------------------------------------------------------
class TestRefreshTokenVersionInvalidation:
    """token_version 失效场景:用户重新登录后,旧 refresh_token 应失效"""

    @pytest.mark.asyncio
    async def test_old_refresh_token_invalid_after_relogin(self, client, registered_user):
        """重新登录后,旧的 refresh_token 应失效(token_version 变更)"""
        # 第一次登录
        login_resp1 = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        old_refresh_token = login_resp1.json()["data"]["refresh_token"]

        # 第二次登录(重新登录,token_version +1)
        login_resp2 = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert login_resp2.json()["code"] == 0

        # 用旧的 refresh_token 刷新:应返回 1008
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": old_refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1008

    @pytest.mark.asyncio
    async def test_new_refresh_token_valid_after_relogin(self, client, registered_user):
        """重新登录后,新的 refresh_token 应有效"""
        # 第一次登录
        await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })

        # 第二次登录
        login_resp2 = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        new_refresh_token = login_resp2.json()["data"]["refresh_token"]

        # 用新的 refresh_token 刷新:应成功
        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": new_refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]


# ---------------------------------------------------------------------------
# refresh_token 类型校验
# ---------------------------------------------------------------------------
class TestRefreshTokenTypeValidation:
    """refresh_token 类型校验:不能用 access_token 刷新"""

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_returns_1008(self, client, registered_user):
        """用 access_token 当 refresh_token 使用:返回 1008"""
        login_resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.post("/api/auth/refresh", json={
            "refresh_token": access_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        # access_token 没有 type=refresh,应被拒绝
        assert data["code"] == 1008
