"""认证服务 - 注册、登录、刷新 token、密码锁"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import BizError, ErrCode
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    mask_phone,
    check_password_strength,
)
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RegisterData,
    LoginData,
    LoginUserInfo,
    RefreshData,
)

logger = logging.getLogger(__name__)


class AuthService:
    """认证业务逻辑"""

    # -------------------------------------------------------------------
    # 注册
    # -------------------------------------------------------------------
    @staticmethod
    async def register(db: AsyncSession, req: RegisterRequest) -> RegisterData:
        """
        注册新用户:
        - 手机号唯一性校验
        - 密码强度校验
        - 首个注册用户自动成为 superadmin
        """
        # 检查手机号是否已注册
        existing = await db.execute(select(User).where(User.phone == req.phone))
        if existing.scalar_one_or_none():
            raise BizError(ErrCode.PHONE_EXISTS, "该手机号已注册")

        # 密码强度校验（service 层二次校验，schema 层已做基础校验）
        ok, reason = check_password_strength(req.password)
        if not ok:
            raise BizError(ErrCode.WEAK_PASSWORD, reason)

        # 判断是否为第一个用户 → superadmin
        count_result = await db.execute(select(func.count(User.id)))
        user_count = count_result.scalar()
        role = "superadmin" if user_count == 0 else "user"

        # 创建用户
        user = User(
            phone=req.phone,
            password_hash=hash_password(req.password),
            role=role,
            token_version=0,
            status="active",
        )
        db.add(user)
        await db.flush()  # 触发 default 值填充

        logger.info("新用户注册: phone=%s, role=%s, user_id=%s", req.phone, role, user.user_id)

        return RegisterData(
            user_id=user.user_id,
            phone=mask_phone(user.phone),
        )

    # -------------------------------------------------------------------
    # 登录
    # -------------------------------------------------------------------
    # 锁定配置
    MAX_LOGIN_FAIL_COUNT = 5
    LOCK_DURATION_MINUTES = 10

    @staticmethod
    async def login(db: AsyncSession, req: LoginRequest) -> LoginData:
        """
        手机号 + 密码登录:
        - 密码错误 5 次 → 锁定 10 分钟（DB 字段记录）
        - 登录成功 → 清除错误计数，递增 token_version
        """
        # 查找用户
        result = await db.execute(select(User).where(User.phone == req.phone))
        user = result.scalar_one_or_none()

        if not user:
            raise BizError(ErrCode.WRONG_CREDENTIALS, "手机号或密码错误")

        # 检查账号状态
        if user.status == "disabled":
            raise BizError(ErrCode.ACCOUNT_DISABLED, "账号已被禁用")

        # 检查是否处于锁定状态
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until
        if locked_until is not None:
            # 确保 locked_until 带时区信息以便比较
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if now < locked_until:
                remaining_seconds = int((locked_until - now).total_seconds())
                raise BizError(
                    ErrCode.ACCOUNT_LOCKED,
                    "账号已锁定，请10分钟后重试",
                    data={"remaining_seconds": remaining_seconds},
                )
            else:
                # 锁定已过期，清除锁定状态
                user.locked_until = None
                user.login_fail_count = 0

        # 校验密码
        if not verify_password(req.password, user.password_hash):
            # 密码错误，累加失败计数
            user.login_fail_count = (user.login_fail_count or 0) + 1
            if user.login_fail_count >= AuthService.MAX_LOGIN_FAIL_COUNT:
                # 达到阈值，锁定账号
                user.locked_until = now + timedelta(minutes=AuthService.LOCK_DURATION_MINUTES)
                await db.flush()
                remaining_seconds = AuthService.LOCK_DURATION_MINUTES * 60
                raise BizError(
                    ErrCode.ACCOUNT_LOCKED,
                    "账号已锁定，请10分钟后重试",
                    data={"remaining_seconds": remaining_seconds},
                )
            await db.flush()
            raise BizError(ErrCode.WRONG_CREDENTIALS, "手机号或密码错误")

        # 登录成功 → 清除锁定计数，递增 token_version（使旧 token 失效）
        user.login_fail_count = 0
        user.locked_until = None
        user.token_version = (user.token_version or 0) + 1
        await db.flush()

        # 生成双 token
        access_token = create_access_token(user.user_id, user.token_version)
        refresh_token = create_refresh_token(user.user_id, user.token_version)

        logger.info("用户登录: phone=%s, user_id=%s", req.phone, user.user_id)

        return LoginData(
            access_token=access_token,
            refresh_token=refresh_token,
            user=LoginUserInfo(
                user_id=user.user_id,
                phone=mask_phone(user.phone),
                nickname=user.nickname,
                avatar_url=user.avatar_url,
            ),
        )

    # -------------------------------------------------------------------
    # 刷新 access token
    # -------------------------------------------------------------------
    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token_str: str) -> RefreshData:
        """
        用 refresh token 换取新的 access token:
        - 校验 refresh token 签名 & 类型
        - 校验 token_version 与数据库一致
        - 返回新 access token（不刷新 refresh token）
        """
        import jwt as pyjwt

        # 解码
        try:
            payload = decode_token(refresh_token_str)
        except pyjwt.ExpiredSignatureError:
            raise BizError(ErrCode.INVALID_REFRESH, "刷新令牌已过期，请重新登录")
        except pyjwt.PyJWTError:
            raise BizError(ErrCode.INVALID_REFRESH, "无效的刷新令牌")

        # 校验类型
        if payload.get("type") != "refresh":
            raise BizError(ErrCode.INVALID_REFRESH, "令牌类型错误")

        user_id = payload.get("sub")
        token_version = payload.get("token_version")

        if not user_id or token_version is None:
            raise BizError(ErrCode.INVALID_REFRESH, "令牌内容无效")

        # 查询用户
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise BizError(ErrCode.INVALID_REFRESH, "用户不存在")

        if user.status == "disabled":
            raise BizError(ErrCode.ACCOUNT_DISABLED, "账号已被禁用")

        # 校验 token_version
        if user.token_version != token_version:
            raise BizError(ErrCode.INVALID_REFRESH, "令牌已失效，请重新登录")

        # 签发新 access token
        new_access_token = create_access_token(user.user_id, user.token_version)

        return RefreshData(access_token=new_access_token)
