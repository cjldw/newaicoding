"""
R28 用户头像本地上传 — pytest(Red 阶段)
==========================================
覆盖需求点:docs/20260920_ai_web开发平台/DEVPLAN/R28.md

接口契约:
- POST /api/users/me/avatar  (multipart, 字段名 file)
  - 格式错误 → code 4001;大小超限(>2MB)→ code 4002;未登录 → 401
  - 成功 → {"code":0,"data":{"avatar_url":"/api/files/avatars/{uuid}.{ext}"}}
  - 文件名 uuid4 随机(防枚举),扩展名小写
  - 存储:settings.AVATAR_UPLOAD_DIR/{user_id}/{filename},DB 更新
    user.avatar_url 与 user.avatar_file_path
  - 响应最小化:仅返回 avatar_url
- PATCH /api/users/me  (扩展:avatar_url 传 null 表示移除头像)
  - null → avatar_url 与 avatar_file_path 均清空
  - 请求体不含 avatar_url 字段时不得误清空(空请求体守卫)
  - 存量兼容:老用户 avatar_file_path=NULL 读取不报错

Red 阶段预期:POST /api/users/me/avatar 尚未实现(404)、
PATCH null 语义尚未实现(被 `is not None` 忽略),故相关用例失败。
test_patch_empty_body_keeps_avatar_url 与
test_legacy_user_without_file_path_get_me_ok 为存量行为守卫(可能 Green)。
"""
import os
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
import pytest_asyncio
from sqlalchemy import select

AVATAR_URL_RE = re.compile(
    r"^/api/files/avatars/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(jpg|jpeg|png|webp)$"
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP"


def _png_bytes(size: int = 16) -> bytes:
    """构造带 PNG 魔数的假图片字节(内容合法性不做断言,仅 Content-Type 校验)"""
    return PNG_MAGIC + b"\x00" * max(0, size - len(PNG_MAGIC))


def _default_avatar_dir() -> Path:
    """spec 约定的默认存储目录(config.AVATAR_UPLOAD_DIR,缺省 ./data/avatars)"""
    from app.config import settings

    return Path(getattr(settings, "AVATAR_UPLOAD_DIR", "./data/avatars"))


_avatar_column_ready = False


@pytest_asyncio.fixture(autouse=True)
async def _ensure_avatar_file_path_column():
    """
    幂等 schema shim:测试库 users 表缺 avatar_file_path 列时补齐。
    等价于迁移 b2e8f4a6c9d1(测试库由 create_all 兜底建表,alembic 重放会
    因表已存在而失败,导致新列无法通过迁移落地)。仅作用于 aicoding_test。
    function 级 async fixture:复用 pytest-asyncio 事件循环,不用 asyncio.run;
    进程内仅首个用例实际检查/补列,降低与 conftest 截断清理的锁竞争。
    """
    global _avatar_column_ready
    if _avatar_column_ready:
        yield
        return

    import sqlalchemy as sa
    from app.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(settings.DATABASE_URL)
    try:
        async with eng.begin() as conn:
            exists = await conn.scalar(sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'users' "
                "AND column_name = 'avatar_file_path'"
            ))
            if not exists:
                await conn.execute(sa.text(
                    "ALTER TABLE users ADD COLUMN avatar_file_path VARCHAR(255) NULL "
                    "DEFAULT NULL COMMENT '本地上传头像存储路径(R28)'"
                ))
    finally:
        await eng.dispose()
    _avatar_column_ready = True
    yield


@pytest.fixture(autouse=True)
def _cleanup_stray_avatar_dir(tmp_path):
    """
    若实现未读取 settings.AVATAR_UPLOAD_DIR 而硬编码 ./data/avatars,
    测试产生的目录在测试后清理(仅清理测试期间新建的目录,不动存量)。
    """
    stray = Path("./data/avatars")
    existed_before = stray.exists()
    yield
    if not existed_before and stray.exists():
        shutil.rmtree(stray, ignore_errors=True)


@pytest_asyncio.fixture
async def redirected_avatar_dir(tmp_path, monkeypatch):
    """
    将 AVATAR_UPLOAD_DIR 重定向到 pytest tmp 目录(raising=False:
    Red 阶段 settings 上还没有该字段,实现后按 spec 生效)。
    返回 avatar 根目录 Path。
    """
    from app.config import settings

    avatar_root = tmp_path / "avatars"
    monkeypatch.setattr(settings, "AVATAR_UPLOAD_DIR", str(avatar_root), raising=False)
    return avatar_root


async def _upload(client, auth_headers, name="a.png", content=None, content_type="image/png"):
    if content is None:
        content = _png_bytes()
    return await client.post(
        "/api/users/me/avatar",
        headers=auth_headers,
        files={"file": (name, content, content_type)},
    )


# ---------------------------------------------------------------------------
# POST /api/users/me/avatar — 上传接口
# ---------------------------------------------------------------------------
class TestAvatarUploadAPI:
    """R28 接口 1:上传头像"""

    @pytest.mark.asyncio
    async def test_upload_jpg_success(self, client, auth_headers, redirected_avatar_dir):
        """上传 JPG 成功:code=0,avatar_url 为 /api/files/avatars/{uuid}.jpg 随机名"""
        resp = await _upload(
            client, auth_headers,
            name="me.jpg", content=JPEG_MAGIC + b"\x00" * 32, content_type="image/jpeg",
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["code"] == 0, data
        assert AVATAR_URL_RE.match(data["data"]["avatar_url"]), data
        assert data["data"]["avatar_url"].endswith(".jpg")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,ctype,magic,ext", [
        ("a.png", "image/png", PNG_MAGIC, "png"),
        ("a.webp", "image/webp", WEBP_MAGIC, "webp"),
    ])
    async def test_upload_png_webp_success(self, client, auth_headers, redirected_avatar_dir,
                                           name, ctype, magic, ext):
        """PNG / WebP 格式均可上传成功"""
        resp = await _upload(client, auth_headers, name=name, content=magic + b"\x00" * 16,
                             content_type=ctype)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["code"] == 0, data
        assert data["data"]["avatar_url"].endswith(f".{ext}")

    @pytest.mark.asyncio
    async def test_upload_boundary_exactly_2mb_success(self, client, auth_headers,
                                                       redirected_avatar_dir):
        """边界:恰好 2MB(≤2MB)应上传成功"""
        content = PNG_MAGIC + b"\x00" * (2 * 1024 * 1024 - len(PNG_MAGIC))
        assert len(content) == 2 * 1024 * 1024
        resp = await _upload(client, auth_headers, name="big.png",
                             content=content, content_type="image/png")
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.json()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,ctype,content", [
        ("a.gif", "image/gif", b"GIF89a" + b"\x00" * 16),
        ("a.txt", "text/plain", b"not an image"),
    ])
    async def test_upload_wrong_format_rejected_4001(self, client, auth_headers,
                                                     redirected_avatar_dir, name, ctype, content):
        """格式不支持(GIF/文本):code 4001,不落盘、不更新用户"""
        resp = await _upload(client, auth_headers, name=name, content=content, content_type=ctype)
        assert resp.json()["code"] == 4001, resp.text

    @pytest.mark.asyncio
    async def test_upload_oversize_rejected_4002(self, client, auth_headers,
                                                 redirected_avatar_dir):
        """大小超限(2MB+1 字节):code 4002"""
        content = PNG_MAGIC + b"\x00" * (2 * 1024 * 1024 + 1 - len(PNG_MAGIC))
        assert len(content) > 2 * 1024 * 1024
        resp = await _upload(client, auth_headers, name="huge.png",
                             content=content, content_type="image/png")
        assert resp.json()["code"] == 4002, resp.text

    @pytest.mark.asyncio
    async def test_upload_unauthenticated_returns_401(self, client, redirected_avatar_dir):
        """未登录上传:401,不产生文件"""
        resp = await client.post(
            "/api/users/me/avatar",
            files={"file": ("a.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_upload_response_minimized_only_avatar_url(self, client, auth_headers,
                                                             redirected_avatar_dir):
        """响应最小化:data 仅含 avatar_url,不泄露内部存储路径/文件名细节"""
        resp = await _upload(client, auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["code"] == 0
        assert set(data["data"].keys()) == {"avatar_url"}, data
        assert "avatar_file_path" not in str(data)
        assert "./data" not in str(data)

    @pytest.mark.asyncio
    async def test_upload_persists_user_fields(self, client, auth_headers, registered_user,
                                               db_session, redirected_avatar_dir):
        """上传成功后:user.avatar_url = 返回值,avatar_file_path 非空(持久化)"""
        resp = await _upload(client, auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        avatar_url = body["data"]["avatar_url"]

        from app.models.user import User
        result = await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )
        user = result.scalar_one()
        assert user.avatar_url == avatar_url
        assert user.avatar_file_path, "avatar_file_path 应在上传后被写入"

    @pytest.mark.asyncio
    async def test_upload_random_filename_anti_enumerable(self, client, auth_headers,
                                                          redirected_avatar_dir):
        """重复上传:文件名 uuid4 随机,两次上传文件名不同(不覆盖)"""
        r1 = await _upload(client, auth_headers)
        r2 = await _upload(client, auth_headers)
        u1 = r1.json()["data"]["avatar_url"]
        u2 = r2.json()["data"]["avatar_url"]
        assert u1 != u2
        assert AVATAR_URL_RE.match(u1) and AVATAR_URL_RE.match(u2)

    @pytest.mark.asyncio
    async def test_upload_extension_lowercased(self, client, auth_headers,
                                               redirected_avatar_dir):
        """扩展名统一转小写(原文件名 .PNG → 返回 .png)"""
        resp = await _upload(client, auth_headers, name="photo.PNG",
                             content=PNG_MAGIC + b"\x00" * 16, content_type="image/png")
        assert resp.status_code == 200, resp.text
        url = resp.json()["data"]["avatar_url"]
        assert url.endswith(".png"), url

    @pytest.mark.asyncio
    async def test_upload_stores_file_under_user_dir(self, client, auth_headers, registered_user,
                                                     redirected_avatar_dir):
        """文件按 spec 存储于 {AVATAR_UPLOAD_DIR}/{user_id}/{filename}"""
        resp = await _upload(client, auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        filename = body["data"]["avatar_url"].rsplit("/", 1)[-1]
        stored = redirected_avatar_dir / registered_user["user_id"] / filename
        assert stored.is_file(), f"文件未写入预期位置: {stored}"


# ---------------------------------------------------------------------------
# PATCH /api/users/me — avatar_url=null 移除头像
# ---------------------------------------------------------------------------
class TestPatchAvatarRemove:
    """R28 接口 3:PATCH /api/users/me 支持 avatar_url 传 null"""

    @pytest.mark.asyncio
    async def test_patch_avatar_url_null_clears_avatar_url(self, client, auth_headers):
        """先设置外部 URL,再传 null:avatar_url 被清空(当前实现 is not None 跳过 → Red)"""
        r1 = await client.patch("/api/users/me", headers=auth_headers,
                                json={"avatar_url": "https://example.com/old.png"})
        assert r1.status_code == 200
        r2 = await client.patch("/api/users/me", headers=auth_headers,
                                json={"avatar_url": None})
        assert r2.status_code == 200, r2.text
        get_resp = await client.get("/api/users/me", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["avatar_url"] is None, get_resp.json()

    @pytest.mark.asyncio
    async def test_patch_null_clears_avatar_file_path_and_keeps_file(
        self, client, auth_headers, registered_user, db_session, redirected_avatar_dir
    ):
        """上传后传 null:avatar_url 与 avatar_file_path 均清空;磁盘文件保留(V1 不删除)"""
        up = await _upload(client, auth_headers)
        assert up.json()["code"] == 0, up.text
        filename = up.json()["data"]["avatar_url"].rsplit("/", 1)[-1]
        stored = redirected_avatar_dir / registered_user["user_id"] / filename
        assert stored.is_file()

        rm = await client.patch("/api/users/me", headers=auth_headers,
                                json={"avatar_url": None})
        assert rm.status_code == 200, rm.text

        from app.models.user import User
        result = await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )
        user = result.scalar_one()
        assert user.avatar_url is None
        assert user.avatar_file_path is None
        # 文件保留
        assert stored.is_file(), "移除头像后磁盘文件应保留(V1 不删除)"

    @pytest.mark.asyncio
    async def test_patch_null_persists_via_get(self, client, auth_headers):
        """null 移除后再 GET /me:avatar_url 保持为 null(持久化,非仅响应层)"""
        await client.patch("/api/users/me", headers=auth_headers,
                           json={"avatar_url": "https://example.com/x.png"})
        await client.patch("/api/users/me", headers=auth_headers, json={"avatar_url": None})
        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.json()["data"]["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_patch_empty_body_keeps_avatar_url(self, client, auth_headers):
        """守卫:请求体不含 avatar_url 字段(空 body)不得误清空已有头像"""
        await client.patch("/api/users/me", headers=auth_headers,
                           json={"avatar_url": "https://example.com/keep.png"})
        resp = await client.patch("/api/users/me", headers=auth_headers, json={})
        assert resp.status_code == 200
        get_resp = await client.get("/api/users/me", headers=auth_headers)
        assert get_resp.json()["data"]["avatar_url"] == "https://example.com/keep.png"

    @pytest.mark.asyncio
    async def test_legacy_user_without_file_path_get_me_ok(self, client, auth_headers,
                                                           registered_user, db_session):
        """存量兼容:老用户 avatar_file_path=NULL + 外部 URL avatar_url,GET /me 正常不报错"""
        from app.models.user import User
        result = await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )
        user = result.scalar_one()
        user.avatar_url = "https://example.com/legacy.png"
        user.avatar_file_path = None  # 存量行默认 NULL
        await db_session.commit()

        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"] == "https://example.com/legacy.png"
