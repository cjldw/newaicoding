"""用户相关 Pydantic Schema"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------

class UpdateProfileRequest(BaseModel):
    """更新个人信息请求"""
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) > 32:
                raise ValueError("昵称不能超过32个字符")
            if not v:
                return None
        return v

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) > 255:
                raise ValueError("头像URL不能超过255个字符")
            if not v:
                return None
        return v


class BindGitlabTokenRequest(BaseModel):
    """绑定 GitLab token 请求"""
    gitlab_token: str

    @field_validator("gitlab_token")
    @classmethod
    def validate_gitlab_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("GitLab token 不能为空")
        return v


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------

class UserProfileResponse(BaseModel):
    """个人信息响应"""
    user_id: str
    phone: str  # 脱敏后
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "user"  # 平台角色:superadmin / user
    gitlab_username: Optional[str] = None
    gitlab_token_bound: bool = False
    gitlab_token_scopes: Optional[List[str]] = None
    gitlab_token_bound_at: Optional[datetime] = None


class BindGitlabTokenResponse(BaseModel):
    """绑定 GitLab token 响应"""
    gitlab_username: str
    gitlab_token_scopes: List[str]
    gitlab_token_bound_at: datetime
