"""认证依赖 - JWT 校验 + 当前用户注入"""

from typing import Optional

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 Authorization header 解析 access token，
    校验 token_version 与数据库一致，返回当前用户。
    """
    if not authorization:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "未提供认证信息", status_code=401)

    # 解析 Bearer <token>
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise BizError(ErrCode.WRONG_CREDENTIALS, "认证格式错误", status_code=401)

    token = parts[1]

    # 解码 JWT
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "令牌已过期", status_code=401)
    except jwt.PyJWTError:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "无效令牌", status_code=401)

    # 校验 token 类型
    if payload.get("type") != "access":
        raise BizError(ErrCode.WRONG_CREDENTIALS, "令牌类型错误", status_code=401)

    user_id = payload.get("sub")
    token_version = payload.get("token_version")

    if not user_id or token_version is None:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "令牌内容无效", status_code=401)

    # 查询用户
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "用户不存在", status_code=401)

    # 校验 token_version（立即失效机制）
    if user.token_version != token_version:
        raise BizError(ErrCode.WRONG_CREDENTIALS, "令牌已失效，请重新登录", status_code=401)

    # 校验账号状态
    if user.status == "disabled":
        raise BizError(ErrCode.ACCOUNT_DISABLED, "账号已被禁用")

    return user
