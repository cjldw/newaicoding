"""认证路由 - 注册、登录、刷新 token、SMS 占位"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success, BizError
from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SendSmsCodeRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["认证"])


# -------------------------------------------------------------------
# POST /api/auth/register - 注册
# -------------------------------------------------------------------
@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """手机号 + 密码注册，首个用户自动成为 superadmin"""
    data = await AuthService.register(db, req)
    return success(data=data.model_dump())


# -------------------------------------------------------------------
# POST /api/auth/login - 登录
# -------------------------------------------------------------------
@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db), request: Request = None):
    """手机号 + 密码登录，返回 access_token + refresh_token;R25 审计透传客户端 IP"""
    ip = request.client.host if (request is not None and request.client) else None
    data = await AuthService.login(db, req, ip=ip)
    return success(data=data.model_dump())


# -------------------------------------------------------------------
# POST /api/auth/refresh - 刷新 access token
# -------------------------------------------------------------------
@router.post("/refresh")
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """用 refresh_token 换取新的 access_token"""
    data = await AuthService.refresh_token(db, req.refresh_token)
    return success(data=data.model_dump())


# -------------------------------------------------------------------
# POST /api/auth/forgot-password - 忘记密码（V1 返回 501）
# -------------------------------------------------------------------
@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """V1 暂不支持，返回 501 Not Implemented"""
    raise BizError(501, "该功能将在后续版本提供")


# -------------------------------------------------------------------
# POST /api/auth/reset-password - 重置密码（V1 返回 501）
# -------------------------------------------------------------------
@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """V1 暂不支持，返回 501 Not Implemented"""
    raise BizError(501, "该功能将在后续版本提供")


# -------------------------------------------------------------------
# POST /api/auth/send-sms-code - 发送短信验证码（V1 返回 501）
# -------------------------------------------------------------------
@router.post("/send-sms-code")
async def send_sms_code(req: SendSmsCodeRequest):
    """V1 暂不支持，返回 501 Not Implemented"""
    raise BizError(501, "该功能将在后续版本提供")
