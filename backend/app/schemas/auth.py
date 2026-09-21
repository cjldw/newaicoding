"""认证相关 Pydantic Schema"""

import re
from typing import Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """注册请求"""
    phone: str
    password: str
    invitation_token: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式错误")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少8位")
        if len(v) > 32:
            raise ValueError("密码不能超过32位")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码需包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        return v


class LoginRequest(BaseModel):
    """登录请求"""
    phone: str
    password: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式错误")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError("请输入密码")
        return v


class RefreshRequest(BaseModel):
    """刷新 token 请求"""
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """找回密码请求 (V2)"""
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式错误")
        return v


class ResetPasswordRequest(BaseModel):
    """重置密码请求 (V2)"""
    phone: str
    sms_code: str
    new_password: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式错误")
        return v

    @field_validator("sms_code")
    @classmethod
    def validate_sms_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("验证码为6位数字")
        return v

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少8位")
        if len(v) > 32:
            raise ValueError("密码不能超过32位")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码需包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        return v


class SendSmsCodeRequest(BaseModel):
    """发送短信验证码请求 (V2)"""
    phone: str
    scene: str  # register | login | reset_password

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式错误")
        return v

    @field_validator("scene")
    @classmethod
    def validate_scene(cls, v: str) -> str:
        allowed = {"register", "login", "reset_password"}
        if v not in allowed:
            raise ValueError(f"scene 必须为 {', '.join(allowed)} 之一")
        return v


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------

class RegisterData(BaseModel):
    """注册响应 data"""
    user_id: str
    phone: str  # 脱敏后


class LoginUserInfo(BaseModel):
    """登录响应中的 user 对象"""
    user_id: str
    phone: str  # 脱敏后
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


class LoginData(BaseModel):
    """登录响应 data"""
    access_token: str
    refresh_token: str
    user: LoginUserInfo


class RefreshData(BaseModel):
    """刷新 token 响应 data"""
    access_token: str
