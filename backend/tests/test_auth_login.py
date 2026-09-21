"""
R1 登录接口测试 — POST /api/auth/login
========================================
覆盖场景:
- 登录成功(返回 JWT 双 token + 用户信息)
- 密码错误(1005)
- 账号锁定(1006,连续 5 次错误)
- 账号禁用(1007)
- 手机号不存在(1005)
- 响应最小化(不含敏感字段)
- 手机号打码验证
"""
import pytest


# ---------------------------------------------------------------------------
# 登录成功
# ---------------------------------------------------------------------------
class TestLoginSuccess:
    """登录成功场景"""

    @pytest.mark.asyncio
    async def test_login_success_returns_jwt_tokens(self, client, registered_user):
        """登录成功:返回 access_token 和 refresh_token"""
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "message" in data
        # 返回 JWT 双 token
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        # JWT 格式:三段 base64 用 . 连接
        assert data["data"]["access_token"].count(".") == 2
        assert data["data"]["refresh_token"].count(".") == 2

    @pytest.mark.asyncio
    async def test_login_success_returns_user_info(self, client, registered_user):
        """登录成功:返回用户信息(打码手机号)"""
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        user = data["data"]["user"]
        assert user["user_id"] == registered_user["user_id"]
        # 手机号打码:前3位 + **** + 后4位
        assert user["phone"] == registered_user["phone"][:3] + "****" + registered_user["phone"][-4:]
        # nickname 和 avatar_url 可能为 null
        assert "nickname" in user
        assert "avatar_url" in user

    @pytest.mark.asyncio
    async def test_login_response_no_sensitive_fields(self, client, registered_user):
        """登录响应最小化:不含 password_hash、gitlab_token_encrypted"""
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 断言响应中不含敏感字段
        resp_text = str(data)
        assert "password_hash" not in resp_text
        assert "password" not in data.get("data", {}).get("user", {})
        assert "gitlab_token_encrypted" not in resp_text
        assert "gitlab_token" not in data.get("data", {}).get("user", {})

    @pytest.mark.asyncio
    async def test_login_phone_masking_format(self, client, registered_user):
        """登录响应中手机号打码格式正确"""
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        phone_masked = data["data"]["user"]["phone"]
        # 格式:前3位 + **** + 后4位,总长度 11
        assert len(phone_masked) == 11
        assert phone_masked[3:7] == "****"
        assert phone_masked[:3] == registered_user["phone"][:3]
        assert phone_masked[-4:] == registered_user["phone"][-4:]


# ---------------------------------------------------------------------------
# 密码错误 — 1005
# ---------------------------------------------------------------------------
class TestLoginWrongPassword:
    """密码错误场景"""

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_1005(self, client, registered_user):
        """密码错误:返回错误码 1005"""
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": "WrongPassword1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1005
        assert "手机号或密码错误" in data["message"]
        assert data["data"] is None

    @pytest.mark.asyncio
    async def test_login_nonexistent_phone_returns_1005(self, client):
        """手机号不存在:返回错误码 1005(与密码错误统一提示,防枚举)"""
        resp = await client.post("/api/auth/login", json={
            "phone": "13900009999",
            "password": "AnyPassword1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1005
        # 统一提示,不暴露手机号是否存在
        assert "手机号或密码错误" in data["message"]


# ---------------------------------------------------------------------------
# 账号锁定 — 1006
# ---------------------------------------------------------------------------
class TestLoginLockout:
    """账号锁定场景(连续 5 次密码错误)"""

    @pytest.mark.asyncio
    async def test_login_lockout_after_5_failed_attempts(self, client, registered_user):
        """连续 5 次密码错误,第 5 次即返回 1006 账号锁定"""
        # 前 4 次:密码错误 1005
        for i in range(4):
            resp = await client.post("/api/auth/login", json={
                "phone": registered_user["phone"],
                "password": f"WrongPass{i}",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 1005  # 前 4 次都是密码错误

        # 第 5 次:达到锁定阈值,返回 1006
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": "WrongPass4",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1006
        assert "锁定" in data["message"] or "重试" in data["message"]
        # 返回 remaining_seconds
        assert "remaining_seconds" in data.get("data", {})
        assert data["data"]["remaining_seconds"] > 0

    @pytest.mark.asyncio
    async def test_login_lockout_prevents_correct_password(self, client, registered_user):
        """锁定期间,即使密码正确也返回 1006"""
        # 先锁定账号:4 次 1005 + 第 5 次 1006
        for i in range(4):
            resp = await client.post("/api/auth/login", json={
                "phone": registered_user["phone"],
                "password": f"WrongPass{i}",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 1005

        # 第 5 次:锁定
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": "WrongPass4",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1006

        # 用正确密码登录,仍返回 1006
        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1006


# ---------------------------------------------------------------------------
# 账号禁用 — 1007
# ---------------------------------------------------------------------------
class TestLoginDisabled:
    """账号禁用场景"""

    @pytest.mark.asyncio
    async def test_login_disabled_account_returns_1007(self, client, db_session, registered_user):
        """禁用账号登录:返回错误码 1007"""
        from app.models.user import User
        from sqlalchemy import select

        # 将用户状态设为 disabled
        result = await db_session.execute(
            select(User).where(User.phone == registered_user["phone"])
        )
        user = result.scalar_one()
        user.status = "disabled"
        await db_session.commit()

        resp = await client.post("/api/auth/login", json={
            "phone": registered_user["phone"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1007
        assert "禁用" in data["message"]


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------
class TestLoginValidation:
    """登录参数校验"""

    @pytest.mark.asyncio
    async def test_login_empty_phone(self, client):
        """手机号为空"""
        resp = await client.post("/api/auth/login", json={
            "phone": "",
            "password": "Test1234",
        })
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_login_empty_password(self, client):
        """密码为空"""
        resp = await client.post("/api/auth/login", json={
            "phone": "13800001111",
            "password": "",
        })
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_login_invalid_phone_format(self, client):
        """手机号格式错误"""
        resp = await client.post("/api/auth/login", json={
            "phone": "12345",
            "password": "Test1234",
        })
        assert resp.status_code in (200, 422)
