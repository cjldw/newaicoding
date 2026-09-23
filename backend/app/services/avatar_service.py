"""头像上传服务 - R28(本地磁盘存储/格式与大小校验/随机文件名防枚举)

与 R4 任务上传(file_upload_service,落容器)不同,头像走平台本地磁盘:
./data/avatars/{user_id}/{uuid4}.{ext}
"""

import re
import uuid
from pathlib import Path

from app.config import settings
from app.core.response import BizError, ErrCode

# R28:头像文件 ≤ 2MB
MAX_AVATAR_SIZE = 2 * 1024 * 1024

# 允许的 Content-Type → 规范扩展名(小写)
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# 扩展名 → 响应 Content-Type(公开访问接口用)
MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

# 头像文件名严格白名单:uuid4 + 白名单扩展名。
# 公开访问接口只接受此形态,天然免疫路径遍历(.. %2F 反斜杠等均不匹配)
FILENAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|jpeg|png|webp)$"
)


def _magic_ok(ext: str, head: bytes) -> bool:
    """宽松魔数校验(防 Content-Type 伪造上传脚本/HTML 等非图片内容)"""
    if ext == "jpg":
        return head[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def read_upload_limited(file, chunk_size: int = 1024 * 1024) -> bytes:
    """限流读取上传流:超过 MAX_AVATAR_SIZE 立即 4002,避免超限文件整块进内存"""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_AVATAR_SIZE:
            raise BizError(ErrCode.AVATAR_TOO_LARGE, "图片大小不能超过 2MB")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_avatar_upload(filename: str, content_type: str, content: bytes) -> str:
    """
    校验上传头像(R28 契约):
    - Content-Type 必须为 image/jpeg / image/png / image/webp,否则 4001
    - 大小 ≤ 2MB(超限在读流阶段已 4002,此处兜底)
    - 魔数与声明格式不符 → 4001
    通过返回规范扩展名(小写)。
    """
    ext = ALLOWED_CONTENT_TYPES.get((content_type or "").split(";")[0].strip().lower())
    if ext is None:
        raise BizError(ErrCode.AVATAR_FORMAT_UNSUPPORTED, "仅支持 JPG/PNG/WebP 格式的图片")
    if len(content) > MAX_AVATAR_SIZE:
        raise BizError(ErrCode.AVATAR_TOO_LARGE, "图片大小不能超过 2MB")
    if not content or not _magic_ok(ext, content[:12]):
        raise BizError(ErrCode.AVATAR_FORMAT_UNSUPPORTED, "仅支持 JPG/PNG/WebP 格式的图片")
    return ext


def save_avatar_file(user_id: str, content: bytes, ext: str) -> tuple[str, str]:
    """
    落盘到 ./data/avatars/{user_id}/{uuid4}.{ext}(目录自动创建)。
    文件名 uuid4 随机生成防枚举;重复上传生成新文件名,旧文件保留(V1 不清理)。
    返回 (avatar_url, avatar_file_path);avatar_file_path 存配置相对路径。
    """
    filename = f"{uuid.uuid4()}.{ext}"
    base = Path(settings.AVATAR_UPLOAD_DIR)
    user_dir = base / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / filename).write_bytes(content)

    avatar_url = f"/api/files/avatars/{filename}"
    file_path = f"{str(settings.AVATAR_UPLOAD_DIR).rstrip('/')}/{user_id}/{filename}"
    return avatar_url, file_path


def resolve_avatar_file(filename: str) -> Path | None:
    """
    按文件名定位 ./data/avatars/{user_id}/{filename}(扫描一层用户子目录)。
    文件名先过严格白名单正则,再参与 glob(无通配元字符),路径遍历不可达。
    找不到返回 None(含:目录不存在/文件已被删 → 前端回退默认头像)。
    """
    if not FILENAME_RE.match(filename or ""):
        return None
    base = Path(settings.AVATAR_UPLOAD_DIR)
    if not base.is_dir():
        return None
    matches = sorted(base.glob(f"*/{filename}"))
    return matches[0] if matches else None
