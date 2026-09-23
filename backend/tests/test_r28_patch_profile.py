"""
R28 修复验证 — PATCH /api/users/me(F1 昵称清空 / F5 返回用户信息 / F6 外部 URL 清理)
====================================================================================
- F1:昵称清空链路。显式传空串或 null 清空昵称(回显手机号),未携带字段不修改
- F5:PATCH 响应 data 返回更新后的完整用户信息(前端 setUser 直接可用)
- F6:PATCH avatar_url 设为外部 URL 时,同步清空 avatar_file_path
"""
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.user import User


# ---------------------------------------------------------------------------
# 工具:最小 PNG 字节(魔数正确即可,后端做宽松魔数校验)
# ---------------------------------------------------------------------------
def png_bytes(size: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)


@pytest.fixture
def avatar_dir(tmp_path, monkeypatch):
    """头像存储目录指到测试临时目录,避免污染仓库工作区"""
    target = tmp_path / "avatars"
    monkeypatch.setattr(settings, "AVATAR_UPLOAD_DIR", str(target))
    return target


async def _upload_avatar(client, auth_headers) -> str:
    """上传头像,返回 avatar_url(平台相对路径)"""
    resp = await client.post(
        "/api/users/me/avatar",
        headers=auth_headers,
        files={"file": ("a.png", png_bytes(), "image/png")},
    )
    assert resp.json()["code"] == 0
    return resp.json()["data"]["avatar_url"]


async def _get_user(db_session, user_id: str) -> User:
    return (await db_session.execute(
        select(User).where(User.user_id == user_id)
    )).scalar_one()


# ---------------------------------------------------------------------------
# F1:昵称清空(空串 / null 清空,回显手机号)
# ---------------------------------------------------------------------------
class TestNicknameClearing:
    @pytest.mark.asyncio
    async def test_clear_nickname_with_empty_string(self, client, db_session, auth_headers, registered_user):
        """显式传空串 → 清空昵称(DB 为 null)"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "旧昵称"})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": ""})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname is None
        # GET 复核持久化
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.json()["data"]["nickname"] is None

    @pytest.mark.asyncio
    async def test_clear_nickname_with_explicit_null(self, client, db_session, auth_headers, registered_user):
        """显式传 null → 清空昵称"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "旧昵称"})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": None})
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname is None

    @pytest.mark.asyncio
    async def test_clear_nickname_with_whitespace(self, client, db_session, auth_headers, registered_user):
        """纯空白串(折叠后为空)→ 清空昵称"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "旧昵称"})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "   "})
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname is None

    @pytest.mark.asyncio
    async def test_missing_nickname_field_keeps_value(self, client, db_session, auth_headers, registered_user):
        """未携带 nickname 字段 → 不修改(与显式清空区分)"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "保留昵称"})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={})
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname == "保留昵称"

    @pytest.mark.asyncio
    async def test_clear_nickname_echoes_masked_phone(self, client, auth_headers, registered_user):
        """清空昵称后响应仍带脱敏手机号(前端回显手机号的依据,对齐 R1 默认值逻辑)"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": ""})
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["nickname"] is None
        assert data["phone"] == registered_user["phone_masked"]

    @pytest.mark.asyncio
    async def test_clear_then_reset_nickname(self, client, db_session, auth_headers, registered_user):
        """清空后再设置新昵称,链路可往返"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": ""})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "新昵称"})
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["nickname"] == "新昵称"

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname == "新昵称"

    @pytest.mark.asyncio
    async def test_nickname_over_32_chars_rejected(self, client, auth_headers):
        """超过 32 字符仍拒绝(422)"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "长" * 33})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_nickname_strips_surrounding_whitespace(self, client, db_session, auth_headers, registered_user):
        """正常昵称两侧空白被折叠"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "  昵称  "})
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["nickname"] == "昵称"


# ---------------------------------------------------------------------------
# F5:PATCH 响应返回更新后的用户信息
# ---------------------------------------------------------------------------
class TestPatchReturnsUserInfo:
    @pytest.mark.asyncio
    async def test_patch_response_contains_user_profile(self, client, auth_headers, registered_user):
        """响应 data 为完整 UserProfileResponse(前端 setUser 直接可用)"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "资料用户"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is not None
        assert data["user_id"] == registered_user["user_id"]
        assert data["phone"] == registered_user["phone_masked"]
        assert data["nickname"] == "资料用户"
        assert "avatar_url" in data
        assert "role" in data
        assert "gitlab_token_bound" in data

    @pytest.mark.asyncio
    async def test_patch_response_reflects_update_immediately(self, client, auth_headers):
        """响应 data 直接反映本次更新后的值(无需再 GET)"""
        resp = await client.patch(
            "/api/users/me",
            headers=auth_headers,
            json={"nickname": "即时回显", "avatar_url": "https://example.com/x.png"},
        )
        data = resp.json()["data"]
        assert data["nickname"] == "即时回显"
        assert data["avatar_url"] == "https://example.com/x.png"

    @pytest.mark.asyncio
    async def test_remove_avatar_response_has_null_avatar(self, client, auth_headers):
        """移除头像(avatar_url=null)响应 data.avatar_url 为 null"""
        await _upload_avatar(client, auth_headers)
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"avatar_url": None})
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_empty_body_response_returns_current_profile(self, client, auth_headers, registered_user):
        """空请求体不改任何字段,响应 data 返回当前信息"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={})
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["user_id"] == registered_user["user_id"]

    @pytest.mark.asyncio
    async def test_patch_response_no_sensitive_fields(self, client, auth_headers):
        """PATCH 响应最小化:不含敏感字段"""
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "x"})
        resp_text = str(resp.json())
        assert "password_hash" not in resp_text
        assert "gitlab_token_encrypted" not in resp_text


# ---------------------------------------------------------------------------
# F6:PATCH 设外部 URL 时同步清理 avatar_file_path
# ---------------------------------------------------------------------------
class TestExternalUrlClearsFilePath:
    @pytest.mark.asyncio
    async def test_external_url_clears_avatar_file_path(self, client, db_session, auth_headers, registered_user):
        """上传后 PATCH 外部 URL:avatar_url 更新,avatar_file_path 同步清空"""
        url = await _upload_avatar(client, auth_headers)
        user = await _get_user(db_session, registered_user["user_id"])
        assert user.avatar_file_path is not None  # 前置:上传已写入文件路径

        resp = await client.patch(
            "/api/users/me",
            headers=auth_headers,
            json={"avatar_url": "https://example.com/external.png"},
        )
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["avatar_url"] == "https://example.com/external.png"

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.avatar_url == "https://example.com/external.png"
        assert user.avatar_file_path is None

    @pytest.mark.asyncio
    async def test_same_platform_url_keeps_avatar_file_path(self, client, db_session, auth_headers, registered_user):
        """PATCH 传回当前本地上传 URL(URL 未变化)→ avatar_file_path 保留"""
        url = await _upload_avatar(client, auth_headers)
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"avatar_url": url})
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.avatar_url == url
        assert user.avatar_file_path is not None

    @pytest.mark.asyncio
    async def test_null_clears_both_fields_after_upload(self, client, db_session, auth_headers, registered_user):
        """上传后 PATCH avatar_url=null:两字段同时清空"""
        await _upload_avatar(client, auth_headers)
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"avatar_url": None})
        assert resp.json()["code"] == 0

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.avatar_url is None
        assert user.avatar_file_path is None

    @pytest.mark.asyncio
    async def test_external_url_with_nickname_clear_together(self, client, db_session, auth_headers, registered_user):
        """组合场景:F1 + F6 同请求(清空昵称 + 设外部 URL → 文件路径清理)"""
        await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "旧昵称"})
        url = await _upload_avatar(client, auth_headers)

        resp = await client.patch(
            "/api/users/me",
            headers=auth_headers,
            json={"nickname": "", "avatar_url": "https://cdn.example.com/a.jpg"},
        )
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["nickname"] is None
        assert data["avatar_url"] == "https://cdn.example.com/a.jpg"

        user = await _get_user(db_session, registered_user["user_id"])
        assert user.nickname is None
        assert user.avatar_file_path is None
