"""
R28 头像文件公开访问 — pytest(Red 阶段)
==========================================
覆盖需求点:docs/20260920_ai_web开发平台/DEVPLAN/R28.md 接口 2

- GET /api/files/avatars/{filename}:无需登录(公开可访问)
  - 存在:返回二进制内容,Content-Type 按扩展名(png/jpeg/webp)
  - 不存在:404
  - 路径遍历(../、%2e%2e 编码):拒绝,不得泄露 avatars 目录外文件

Red 阶段预期:GET /api/files/avatars/{filename} 路由尚未实现 → 404,用例失败。

存储目录:优先读 settings.AVATAR_UPLOAD_DIR(R28 新增配置),
未实现时回退 spec 默认值 ./data/avatars,保证 Red/Green 两阶段都能定位。
"""
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
import pytest_asyncio

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP"


_avatar_column_ready = False


@pytest_asyncio.fixture(autouse=True)
async def _ensure_avatar_file_path_column():
    """
    幂等 schema shim:测试库 users 表缺 avatar_file_path 列时补齐
    (与迁移 b2e8f4a6c9d1 等价;同 test_r28_avatar_upload.py,进程内只执行一次)。
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


def _avatar_root() -> Path:
    from app.config import settings

    return Path(getattr(settings, "AVATAR_UPLOAD_DIR", "./data/avatars"))


@pytest.fixture
def avatar_root(tmp_path, monkeypatch):
    """重定向 AVATAR_UPLOAD_DIR 到 tmp(实现读取该配置时生效);返回根目录"""
    from app.config import settings

    root = tmp_path / "avatars"
    monkeypatch.setattr(settings, "AVATAR_UPLOAD_DIR", str(root), raising=False)
    yield root
    # 若实现硬编码未走配置,清理测试期间新建的 ./data/avatars
    stray = Path("./data/avatars")
    if stray.exists() and str(root) != "./data/avatars":
        shutil.rmtree(stray, ignore_errors=True)


def _seed_file(root: Path, user_id: str, filename: str, content: bytes) -> Path:
    """直接在存储目录落一个文件(GET 测试不依赖上传接口,保持用例独立)"""
    user_dir = root / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    f = user_dir / filename
    f.write_bytes(content)
    return f


@pytest.fixture
def seeded_user_id() -> str:
    return "11111111-2222-3333-4444-555555555555"


# ---------------------------------------------------------------------------
# GET /api/files/avatars/{filename} — 公开访问
# ---------------------------------------------------------------------------
class TestAvatarFileAccess:
    """R28 接口 2:头像文件公开访问(无需登录)"""

    @pytest.mark.asyncio
    async def test_get_existing_file_public_no_auth(self, client, avatar_root,
                                                    seeded_user_id):
        """存在的文件:无需登录即可 GET,返回原始字节"""
        content = PNG_MAGIC + b"\x00" * 32
        _seed_file(avatar_root, seeded_user_id, "aaaabbbb-cccc-dddd-eeee-ffff00001111.png",
                   content)
        resp = await client.get(
            f"/api/files/avatars/aaaabbbb-cccc-dddd-eeee-ffff00001111.png"
        )
        assert resp.status_code == 200, resp.text
        assert resp.content == content

    @pytest.mark.asyncio
    @pytest.mark.parametrize("filename,content,expected_ctype", [
        ("aaaabbbb-cccc-dddd-eeee-ffff00002222.png", PNG_MAGIC + b"\x00" * 8, "image/png"),
        ("aaaabbbb-cccc-dddd-eeee-ffff00003333.jpg", JPEG_MAGIC + b"\x00" * 8, "image/jpeg"),
        ("aaaabbbb-cccc-dddd-eeee-ffff00004444.webp", WEBP_MAGIC + b"\x00" * 8, "image/webp"),
    ])
    async def test_get_content_type_by_extension(self, client, avatar_root, seeded_user_id,
                                                 filename, content, expected_ctype):
        """Content-Type 按扩展名自动判断(png/jpeg/webp)"""
        _seed_file(avatar_root, seeded_user_id, filename, content)
        resp = await client.get(f"/api/files/avatars/{filename}")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == expected_ctype

    @pytest.mark.asyncio
    async def test_get_nonexistent_file_returns_404(self, client, avatar_root):
        """不存在的文件:404(即使目录本身也不存在)"""
        resp = await client.get(
            "/api/files/avatars/00000000-0000-0000-0000-000000000000.png"
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw_name", [
        "../secret-marker.txt",                    # 明文 ..
        "%2e%2e%2fsecret-marker.txt",              # 编码 ./%2e%2e%2f
    ])
    async def test_get_path_traversal_blocked(self, client, avatar_root, raw_name):
        """路径遍历防护:拒绝访问 avatars 目录外文件,不泄露内容"""
        # 在 avatars 目录的上一级放置标记文件(遍历一层即可触达)
        marker = avatar_root.parent / "secret-marker.txt"
        avatar_root.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"TOPSECRET-AVATAR-TRAVERSAL-MARKER")
        try:
            resp = await client.get(f"/api/files/avatars/{quote(raw_name)}")
            assert resp.status_code in (400, 404), \
                f"遍历请求未被拒绝: {resp.status_code} {resp.text[:200]}"
            assert b"TOPSECRET" not in resp.content, "泄露了 avatars 目录外文件内容"
        finally:
            marker.unlink(missing_ok=True)
