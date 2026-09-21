"""用户路由 - 个人信息、GitLab token 管理"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.encryption import encrypt_token, decrypt_token
from app.core.response import success, BizError, ErrCode
from app.core.security import mask_phone
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UpdateProfileRequest,
    BindGitlabTokenRequest,
    UserProfileResponse,
    BindGitlabTokenResponse,
)
from app.services.gitlab_service import GitlabService

router = APIRouter(prefix="/api/users", tags=["用户"])


# -------------------------------------------------------------------
# GET /api/users/me - 获取个人信息
# -------------------------------------------------------------------
@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户的个人信息"""
    data = UserProfileResponse(
        user_id=current_user.user_id,
        phone=mask_phone(current_user.phone),
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        gitlab_username=current_user.gitlab_username,
        gitlab_token_bound=current_user.gitlab_token_encrypted is not None,
        gitlab_token_scopes=current_user.gitlab_token_scopes,
        gitlab_token_bound_at=current_user.gitlab_token_bound_at,
    )
    return success(data=data.model_dump())


# -------------------------------------------------------------------
# PATCH /api/users/me - 更新个人信息
# -------------------------------------------------------------------
@router.patch("/me")
async def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新昵称、头像等个人信息"""
    if req.nickname is not None:
        current_user.nickname = req.nickname
    if req.avatar_url is not None:
        current_user.avatar_url = req.avatar_url

    await db.flush()

    return success(message="更新成功")


# -------------------------------------------------------------------
# PUT /api/users/me/gitlab-token - 绑定/重新绑定 GitLab token
# -------------------------------------------------------------------
@router.put("/me/gitlab-token")
async def bind_gitlab_token(
    req: BindGitlabTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    绑定 GitLab personal access token:
    - 调用 GitLab API 验证 token 有效性
    - 获取用户名和 scope
    - AES-256-GCM 加密后存储
    """
    # 调用 GitLab API 验证 token
    gitlab_info = await GitlabService.verify_token(req.gitlab_token)
    username = gitlab_info["username"]
    scopes = gitlab_info["scopes"]

    # 检查 scope 是否满足要求（必须同时具备 read_repository 和 write_repository）
    if not GitlabService.check_required_scopes(scopes):
        raise BizError(ErrCode.GITLAB_SCOPE_INSUFFICIENT, "GitLab token 缺少必要权限")

    # 加密存储
    encrypted = encrypt_token(req.gitlab_token)

    # 更新用户记录
    current_user.gitlab_username = username
    current_user.gitlab_token_encrypted = encrypted
    current_user.gitlab_token_scopes = scopes
    current_user.gitlab_token_bound_at = datetime.now(timezone.utc)

    await db.flush()

    data = BindGitlabTokenResponse(
        gitlab_username=username,
        gitlab_token_scopes=scopes,
        gitlab_token_bound_at=current_user.gitlab_token_bound_at,
    )
    return success(data=data.model_dump())


# -------------------------------------------------------------------
# DELETE /api/users/me/gitlab-token - 解绑 GitLab token
# -------------------------------------------------------------------
@router.delete("/me/gitlab-token")
async def unbind_gitlab_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑 GitLab token，清空相关字段"""
    current_user.gitlab_username = None
    current_user.gitlab_token_encrypted = None
    current_user.gitlab_token_scopes = None
    current_user.gitlab_token_bound_at = None

    await db.flush()

    return success(message="解绑成功")


# -------------------------------------------------------------------
# GET /api/users/search?phone= - 手机号精确搜索(R12 邀请成员用)
# -------------------------------------------------------------------
@router.get("/search")
async def search_user_by_phone(
    phone: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    按手机号精确匹配用户(R1 已去邮箱,手机号即登录名)。
    命中返回 {user_id, phone_masked, nickname, avatar_url};未命中返回 null。
    """
    from sqlalchemy import select

    from app.core.security import mask_phone

    normalized = phone.strip()
    # 未传参或格式不足时直接返回空,避免模糊前缀泄露用户列表
    if len(normalized) < 11:
        return success(data=None)

    result = await db.execute(select(User).where(User.phone == normalized))
    user = result.scalar_one_or_none()
    if user is None:
        return success(data=None)

    return success(data={
        "user_id": user.user_id,
        "phone_masked": mask_phone(user.phone),
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
    })
