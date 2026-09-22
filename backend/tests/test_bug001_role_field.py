"""
BUG-001 修复验证测试 — role 字段传递
=====================================
验证:
1. 登录响应包含 role 字段
2. GET /api/users/me 响应包含 role 字段
3. superadmin 账号 role='superadmin',普通账号 role='user'
"""
import pytest


# ---------------------------------------------------------------------------
# 登录响应包含 role 字段
# ---------------------------------------------------------------------------
class TestLoginResponseContainsRole:
    """登录响应 role 字段验证"""

    @pytest.mark.asyncio
    async def test_login_response_contains_role_for_superadmin(
        self, client, db_session
    ):
        """superadmin 登录后,响应 user.role == 'superadmin'"""
        import uuid
        from sqlalchemy import text

        # 注册用户
        phone = f"139{str(uuid.uuid4().int)[:8]}"
        password = "Admin1234"
        resp = await client.post(
            "/api/auth/register", json={"phone": phone, "password": password}
        )
        assert resp.status_code == 200
        user_id = resp.json()["data"]["user_id"]

        # 提升为 superadmin
        await db_session.execute(
            text("UPDATE users SET role = 'superadmin' WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await db_session.commit()

        # 登录
        resp = await client.post(
            "/api/auth/login", json={"phone": phone, "password": password}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

        # 断言:role 字段存在且为 'superadmin'
        user = data["data"]["user"]
        assert "role" in user, "登录响应 user 对象必须包含 role 字段"
        assert user["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_login_response_contains_role_for_normal_user(
        self, client, registered_user, db_session
    ):
        """普通用户登录后,响应 user.role == 'user'"""
        from sqlalchemy import text

        # registered_user 可能是首个注册用户(自动成为 superadmin),
        # 显式降级为普通用户以验证普通用户路径
        await db_session.execute(
            text("UPDATE users SET role = 'user' WHERE user_id = :uid"),
            {"uid": registered_user["user_id"]},
        )
        await db_session.commit()

        resp = await client.post(
            "/api/auth/login",
            json={
                "phone": registered_user["phone"],
                "password": registered_user["password"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

        # 断言:role 字段存在且为 'user'
        user = data["data"]["user"]
        assert "role" in user, "登录响应 user 对象必须包含 role 字段"
        assert user["role"] == "user"


# ---------------------------------------------------------------------------
# GET /api/users/me 响应包含 role 字段
# ---------------------------------------------------------------------------
class TestMeResponseContainsRole:
    """GET /api/users/me 响应 role 字段验证"""

    @pytest.mark.asyncio
    async def test_me_response_contains_role_for_superadmin(
        self, client, db_session, superadmin_headers
    ):
        """superadmin 调用 /me,响应 role == 'superadmin'"""
        resp = await client.get("/api/users/me", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

        # 断言:role 字段存在且为 'superadmin'
        assert "role" in data["data"], "/me 响应必须包含 role 字段"
        assert data["data"]["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_me_response_contains_role_for_normal_user(
        self, client, auth_headers, registered_user, db_session
    ):
        """普通用户调用 /me,响应 role == 'user'"""
        from sqlalchemy import text

        # auth_headers 依赖 registered_user,同样可能是首个用户(superadmin)
        # 显式降级后重新登录以获取普通用户 token
        await db_session.execute(
            text("UPDATE users SET role = 'user' WHERE user_id = :uid"),
            {"uid": registered_user["user_id"]},
        )
        await db_session.commit()

        # 重新登录获取新 token(角色已变更)
        resp = await client.post(
            "/api/auth/login",
            json={
                "phone": registered_user["phone"],
                "password": registered_user["password"],
            },
        )
        assert resp.status_code == 200
        new_token = resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {new_token}"}

        resp = await client.get("/api/users/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

        # 断言:role 字段存在且为 'user'
        assert "role" in data["data"], "/me 响应必须包含 role 字段"
        assert data["data"]["role"] == "user"
