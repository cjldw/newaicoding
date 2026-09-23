"""
R28 用户头像上传测试 — POST /api/users/me/avatar + GET /api/files/avatars/{filename}
====================================================================================
覆盖场景:
- 上传成功(JPG/PNG/WebP):返回 avatar_url,文件落盘,DB 两字段更新
- 格式不支持(GIF/伪造 Content-Type)→ 4001
- 大小超限(>2MB)→ 4002
- 未登录上传 → 401
- 头像文件公开访问(无需登录)/ 不存在 404 / 路径遍历防护
- PATCH /api/users/me avatar_url=null 移除头像(两字段同时清空)
- 重复上传生成新文件名(并发无冲突)
- 存量兼容(avatar_file_path=null 不报错)
"""
import pytest

from app.config import settings
from app.models.user import User
from sqlalchemy import select


# ---------------------------------------------------------------------------
# 测试用最小图片字节(仅魔数正确即可,后端做宽松魔数校验)
# ---------------------------------------------------------------------------
def jpg_bytes(size: int = 64) -> bytes:
    body = b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * max(0, size - 9) + b"\xff\xd9"
    return body


def png_bytes(size: int = 64) -> bytes:
    body = b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)
    return body


def webp_bytes(size: int = 64) -> bytes:
    body = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * max(0, size - 12)
    return body


@pytest.fixture
def avatar_dir(tmp_path, monkeypatch):
    """将头像存储目录指到测试临时目录,避免污染仓库工作区"""
    target = tmp_path / "avatars"
    monkeypatch.setattr(settings, "AVATAR_UPLOAD_DIR", str(target))
    return target


def avatar_file(avatar_dir, filename):
    """在临时目录中定位已上传的头像文件(*/{filename})"""
    matches = list(avatar_dir.glob(f"*/{filename}"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# POST /api/users/me/avatar - 上传
# ---------------------------------------------------------------------------
class TestAvatarUpload:
    @pytest.mark.asyncio
    async def test_upload_jpg_success(self, client, db_session, auth_headers, registered_user, avatar_dir):
        """上传 JPG 成功:返回 avatar_url,落盘,DB avatar_url/avatar_file_path 更新"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.jpg", jpg_bytes(), "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        url = data["data"]["avatar_url"]
        assert url.startswith("/api/files/avatars/")
        filename = url.rsplit("/", 1)[1]
        # 响应最小化:仅 avatar_url,不含内部存储路径
        assert "avatar_file_path" not in data["data"]
        assert "file_path" not in str(data["data"])

        # 文件落盘 ./data/avatars/{user_id}/{uuid}.jpg
        stored = avatar_file(avatar_dir, filename)
        assert stored is not None
        assert registered_user["user_id"] in str(stored)

        # DB 两字段更新(与 API 共享同一 session,flush 可见)
        user = (await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )).scalar_one()
        assert user.avatar_url == url
        assert user.avatar_file_path is not None
        assert user.avatar_file_path.endswith(f"/{filename}")

    @pytest.mark.asyncio
    async def test_upload_png_success(self, client, auth_headers, avatar_dir):
        """上传 PNG 成功,扩展名为 png"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("b.png", png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"].endswith(".png")

    @pytest.mark.asyncio
    async def test_upload_webp_success(self, client, auth_headers, avatar_dir):
        """上传 WebP 成功,扩展名为 webp"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("c.webp", webp_bytes(), "image/webp")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"].endswith(".webp")

    @pytest.mark.asyncio
    async def test_upload_gif_rejected_4001(self, client, auth_headers):
        """GIF 格式不支持 → 4001"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("d.gif", b"GIF89a" + b"\x00" * 32, "image/gif")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 4001

    @pytest.mark.asyncio
    async def test_upload_forged_content_type_rejected_4001(self, client, auth_headers):
        """Content-Type 伪装 image/png 但内容非图片 → 4001(魔数校验)"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")},
        )
        assert resp.json()["code"] == 4001

    @pytest.mark.asyncio
    async def test_upload_oversize_rejected_4002(self, client, auth_headers, avatar_dir):
        """大小超过 2MB → 4002,且不落盘"""
        big = png_bytes(2 * 1024 * 1024 + 1)
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("big.png", big, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 4002
        # 目录未被创建(无脏数据)
        assert not avatar_dir.exists() or not list(avatar_dir.glob("*/*"))

    @pytest.mark.asyncio
    async def test_upload_no_auth_returns_401(self, client, avatar_dir):
        """未登录上传 → 401"""
        resp = await client.post(
            "/api/users/me/avatar",
            files={"file": ("a.png", png_bytes(), "image/png")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_repeat_upload_new_filenames(self, client, auth_headers, avatar_dir):
        """重复上传:各自生成新文件名(并发无冲突),旧文件保留"""
        urls = []
        for i in range(2):
            resp = await client.post(
                "/api/users/me/avatar",
                headers=auth_headers,
                files={"file": (f"r{i}.png", png_bytes(), "image/png")},
            )
            assert resp.json()["code"] == 0
            urls.append(resp.json()["data"]["avatar_url"])
        assert urls[0] != urls[1]
        assert avatar_file(avatar_dir, urls[0].rsplit("/", 1)[1]) is not None
        assert avatar_file(avatar_dir, urls[1].rsplit("/", 1)[1]) is not None

    @pytest.mark.asyncio
    async def test_get_me_after_upload(self, client, auth_headers):
        """上传后 GET /api/users/me 返回新 avatar_url(存量 avatar_file_path=null 兼容读不报错)"""
        # 先验证未上传(存量行)时 avatar_file_path 为 null 且接口正常
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.status_code == 200
        assert me.json()["data"]["avatar_url"] is None

        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.jpg", jpg_bytes(), "image/jpeg")},
        )
        url = resp.json()["data"]["avatar_url"]
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.json()["data"]["avatar_url"] == url


# ---------------------------------------------------------------------------
# GET /api/files/avatars/{filename} - 公开访问
# ---------------------------------------------------------------------------
class TestAvatarFileAccess:
    @pytest.mark.asyncio
    async def test_public_access_no_login(self, client, auth_headers, avatar_dir):
        """无需登录即可访问头像文件,Content-Type 正确,内容一致"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.jpg", jpg_bytes(128), "image/jpeg")},
        )
        url = resp.json()["data"]["avatar_url"]

        # 不带 Authorization 访问
        raw = await client.get(url)
        assert raw.status_code == 200
        assert raw.headers["content-type"].startswith("image/jpeg")
        assert raw.content == jpg_bytes(128)

    @pytest.mark.asyncio
    async def test_missing_file_returns_404(self, client, avatar_dir):
        """不存在的文件 → 404"""
        resp = await client.get("/api/files/avatars/00000000-0000-4000-8000-000000000000.png")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, client, avatar_dir):
        """路径遍历:非 uuid4 白名单文件名一律 404"""
        for bad in ["..", "../../etc/passwd", "a/b.png", "%2e%2e%2f.png", "x.PNG", "not-a-uuid.png"]:
            resp = await client.get(f"/api/files/avatars/{bad}")
            assert resp.status_code == 404, f"filename={bad} 应被拒绝"

    @pytest.mark.asyncio
    async def test_deleted_file_returns_404(self, client, auth_headers, avatar_dir):
        """头像文件被删除后访问 → 404(前端回退默认头像)"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        )
        url = resp.json()["data"]["avatar_url"]
        filename = url.rsplit("/", 1)[1]
        avatar_file(avatar_dir, filename).unlink()
        raw = await client.get(url)
        assert raw.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/users/me - avatar_url 传 null 移除头像
# ---------------------------------------------------------------------------
class TestRemoveAvatar:
    @pytest.mark.asyncio
    async def test_patch_null_clears_both_fields(self, client, db_session, auth_headers, registered_user, avatar_dir):
        """PATCH avatar_url=null:avatar_url 与 avatar_file_path 同时清空,文件保留"""
        resp = await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        )
        url = resp.json()["data"]["avatar_url"]
        filename = url.rsplit("/", 1)[1]

        patch = await client.patch("/api/users/me", headers=auth_headers, json={"avatar_url": None})
        assert patch.status_code == 200
        assert patch.json()["code"] == 0

        user = (await db_session.execute(
            select(User).where(User.user_id == registered_user["user_id"])
        )).scalar_one()
        assert user.avatar_url is None
        assert user.avatar_file_path is None

        # 文件本身保留(V1 不删除),公开 URL 仍可访问
        assert avatar_file(avatar_dir, filename).exists()
        assert (await client.get(url)).status_code == 200

        # GET /me 头像为空
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.json()["data"]["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_patch_empty_body_keeps_avatar(self, client, auth_headers):
        """空请求体(未携带 avatar_url 字段)不移除头像:与显式 null 区分"""
        await client.post(
            "/api/users/me/avatar",
            headers=auth_headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        )
        resp = await client.patch("/api/users/me", headers=auth_headers, json={"nickname": "保持头像"})
        assert resp.json()["code"] == 0
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.json()["data"]["avatar_url"] is not None
        assert me.json()["data"]["nickname"] == "保持头像"

    @pytest.mark.asyncio
    async def test_patch_external_url_keeps_url(self, client, auth_headers):
        """PATCH avatar_url=外部 URL:照常更新(存量外部 URL 场景)"""
        resp = await client.patch(
            "/api/users/me",
            headers=auth_headers,
            json={"avatar_url": "https://example.com/legacy.png"},
        )
        assert resp.json()["code"] == 0
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.json()["data"]["avatar_url"] == "https://example.com/legacy.png"

    @pytest.mark.asyncio
    async def test_patch_remove_no_auth_returns_401(self, client):
        """未登录 PATCH → 401"""
        resp = await client.patch("/api/users/me", json={"avatar_url": None})
        assert resp.status_code == 401
