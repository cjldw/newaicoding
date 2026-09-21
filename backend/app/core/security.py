"""安全模块 - JWT 双令牌 + 密码哈希 + 手机号脱敏"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from passlib.context import CryptContext

from app.config import settings


# ---------------------------------------------------------------------------
# 密码哈希 (bcrypt, cost=12)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT 双令牌 (access + refresh)，payload 携带 token_version
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"


def create_access_token(user_id: str, token_version: int, extra: Optional[dict[str, Any]] = None) -> str:
    """创建 access token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "token_version": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, token_version: int) -> str:
    """创建 refresh token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "token_version": token_version,
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT，失败时抛出 jwt.PyJWTError"""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# 手机号脱敏: 138****1234
# ---------------------------------------------------------------------------

def mask_phone(phone: str) -> str:
    """手机号中间四位脱敏"""
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


# ---------------------------------------------------------------------------
# 密码强度校验 (R1 要求: 8-32 位, 至少含大小写字母和数字)
# ---------------------------------------------------------------------------

def check_password_strength(password: str) -> tuple[bool, str]:
    """
    校验密码强度:
    - 长度 8-32
    - 至少包含大写字母、小写字母、数字
    返回 (通过, 失败原因)
    """
    if len(password) < 8:
        return False, "密码长度不能少于8位"
    if len(password) > 32:
        return False, "密码长度不能超过32位"
    if not any(c.isupper() for c in password):
        return False, "密码必须包含至少一个大写字母"
    if not any(c.islower() for c in password):
        return False, "密码必须包含至少一个小写字母"
    if not any(c.isdigit() for c in password):
        return False, "密码必须包含至少一个数字"
    return True, ""
