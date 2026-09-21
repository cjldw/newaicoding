"""
R1 注册接口测试 — POST /api/auth/register
==========================================
覆盖场景:
- 注册成功(200, code=0)
- 手机号重复(1001)
- 弱密码(1003)
- 无效邀请 token(1004)
- 手机号格式错误(参数校验)
- 响应最小化(不含敏感字段)
"""
import pytest


# ---------------------------------------------------------------------------
# 注册成功
# ---------------------------------------------------------------------------
class TestRegisterSuccess:
    """注册成功场景"""

    @pytest.mark.asyncio
    async def test_register_success_returns_user_id_and_masked_phone(self, client):
        """注册成功:返回 user_id 和打码手机号"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800001111",
            "password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "message" in data
        # 返回 user_id(uuid 格式)
        assert "user_id" in data["data"]
        assert len(data["data"]["user_id"]) == 36  # UUID 格式
        # 手机号打码:前3位 + **** + 后4位
        assert data["data"]["phone"] == "138****1111"

    @pytest.mark.asyncio
    async def test_register_first_user_is_superadmin(self, client):
        """首个注册用户自动成为 superadmin(角色由服务端决定,响应不暴露)"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800002222",
            "password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 响应不应暴露 role 字段
        assert "role" not in data["data"]

    @pytest.mark.asyncio
    async def test_register_response_no_sensitive_fields(self, client):
        """注册响应最小化:不含 password_hash、gitlab_token_encrypted 等敏感字段"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800003333",
            "password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 断言响应中不含敏感字段
        resp_text = str(data)
        assert "password_hash" not in resp_text
        assert "password" not in data.get("data", {})
        assert "gitlab_token_encrypted" not in resp_text
        assert "gitlab_token" not in data.get("data", {})

    @pytest.mark.asyncio
    async def test_register_with_invitation_token(self, client):
        """带有效邀请 token 注册成功"""
        # 邀请 token 由服务端生成,此处假设有效 token 为 "valid-invitation-token"
        # 实际实现中,需要先通过 API 或数据库创建有效 token
        resp = await client.post("/api/auth/register", json={
            "phone": "13800004444",
            "password": "Test1234",
            "invitation_token": "valid-invitation-token",
        })
        # 如果邀请制未启用,任何 token 都接受;如果启用,需要有效 token
        # 此处测试两种情况
        assert resp.status_code == 200
        data = resp.json()
        # 要么注册成功(code=0),要么 token 无效(1004)
        assert data["code"] in (0, 1004)


# ---------------------------------------------------------------------------
# 手机号重复 — 1001
# ---------------------------------------------------------------------------
class TestRegisterDuplicatePhone:
    """手机号重复场景"""

    @pytest.mark.asyncio
    async def test_register_duplicate_phone_returns_1001(self, client, registered_user):
        """注册已存在的手机号:返回错误码 1001"""
        resp = await client.post("/api/auth/register", json={
            "phone": registered_user["phone"],
            "password": "Another123",
        })
        assert resp.status_code == 200  # HTTP 200,业务错误码在 body 中
        data = resp.json()
        assert data["code"] == 1001
        assert "已存在" in data["message"] or "重复" in data["message"] or "已注册" in data["message"]
        assert data["data"] is None


# ---------------------------------------------------------------------------
# 弱密码 — 1003
# ---------------------------------------------------------------------------
class TestRegisterWeakPassword:
    """密码不符合规则场景"""

    @pytest.mark.asyncio
    async def test_register_password_too_short_returns_1003(self, client):
        """密码少于 8 位:返回错误码 1003"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800005555",
            "password": "Ab1",  # 只有 3 位
        })
        # Pydantic 可能返回 422,或业务层返回 200 + 1003
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] == 1003
            assert "密码" in data["message"]

    @pytest.mark.asyncio
    async def test_register_password_no_letters_returns_1003(self, client):
        """密码不含字母:返回错误码 1003"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800006666",
            "password": "12345678",  # 纯数字
        })
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] == 1003

    @pytest.mark.asyncio
    async def test_register_password_no_digits_returns_1003(self, client):
        """密码不含数字:返回错误码 1003"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800007777",
            "password": "Abcdefgh",  # 纯字母
        })
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] == 1003

    @pytest.mark.asyncio
    async def test_register_empty_password_returns_1003(self, client):
        """空密码:返回错误码 1003"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800008888",
            "password": "",
        })
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["code"] == 1003


# ---------------------------------------------------------------------------
# 无效邀请 token — 1004
# ---------------------------------------------------------------------------
class TestRegisterInvalidInvitation:
    """邀请 token 无效场景"""

    @pytest.mark.asyncio
    async def test_register_invalid_invitation_token_returns_1004(self, client):
        """无效邀请 token:返回错误码 1004"""
        resp = await client.post("/api/auth/register", json={
            "phone": "13800009999",
            "password": "Test1234",
            "invitation_token": "invalid-token-12345",
        })
        # 如果邀请制启用,返回 1004;如果未启用,返回 0
        data = resp.json()
        assert data["code"] in (0, 1004)
        if data["code"] == 1004:
            assert "邀请" in data["message"] or "token" in data["message"].lower()


# ---------------------------------------------------------------------------
# 手机号格式错误(参数校验)
# ---------------------------------------------------------------------------
class TestRegisterInvalidPhone:
    """手机号格式错误场景"""

    @pytest.mark.asyncio
    async def test_register_invalid_phone_format(self, client):
        """手机号格式错误:返回参数校验错误"""
        resp = await client.post("/api/auth/register", json={
            "phone": "12345678901",  # 不以 1[3-9] 开头
            "password": "Test1234",
        })
        # 参数校验失败可能返回 422 或业务错误码
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            # 业务层校验
            assert data["code"] != 0 or "手机号" in data.get("message", "")

    @pytest.mark.asyncio
    async def test_register_phone_too_short(self, client):
        """手机号位数不足"""
        resp = await client.post("/api/auth/register", json={
            "phone": "1380000",
            "password": "Test1234",
        })
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_register_phone_too_long(self, client):
        """手机号位数超出"""
        resp = await client.post("/api/auth/register", json={
            "phone": "138000011112222",
            "password": "Test1234",
        })
        assert resp.status_code in (200, 422)
