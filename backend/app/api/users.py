"""用户路由 - 个人信息、GitLab token 管理"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile
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
from app.services import avatar_service
from app.services.gitlab_service import GitlabService
from app.services.platform_settings_service import get_setting

router = APIRouter(prefix="/api/users", tags=["用户"])


def _profile_response(user: User) -> UserProfileResponse:
    """构造个人信息响应(get_me 与 update_me 共用,R28/F5)"""
    return UserProfileResponse(
        user_id=user.user_id,
        phone=mask_phone(user.phone),
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        role=user.role,
        gitlab_username=user.gitlab_username,
        gitlab_token_bound=user.gitlab_token_encrypted is not None,
        gitlab_token_scopes=user.gitlab_token_scopes,
        gitlab_token_bound_at=user.gitlab_token_bound_at,
    )


# -------------------------------------------------------------------
# GET /api/users/me - 获取个人信息
# -------------------------------------------------------------------
@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户的个人信息"""
    data = _profile_response(current_user)
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
    """更新昵称、头像等个人信息,响应 data 返回更新后的完整用户信息

    - R28/F1:nickname 显式传空串或 null 即清空(前端回显手机号);
      未携带该字段则不修改(以 model_fields_set 区分)
    - R28/F6:avatar_url 换成外部 URL 等非本地上传地址时,同步清空
      avatar_file_path(本地文件不再作为头像来源;文件本身保留,V1 不删)
    - R28/F5:响应 data 为更新后的 UserProfileResponse(前端直接 setUser)
    """
    if "nickname" in req.model_fields_set:
        # 校验器已把空串折叠为 None,None 即清空昵称
        current_user.nickname = req.nickname
    if "avatar_url" in req.model_fields_set:
        if req.avatar_url is None:
            # R28:显式传 null 表示移除头像,同时清空本地文件路径
            # (文件本身保留,V1 不做磁盘清理)
            current_user.avatar_url = None
            current_user.avatar_file_path = None
        else:
            if req.avatar_url != current_user.avatar_url:
                # R28/F6:设为外部 URL(与当前值不同)时,原本地文件路径同步失效
                current_user.avatar_file_path = None
            current_user.avatar_url = req.avatar_url

    await db.flush()

    data = _profile_response(current_user)
    return success(data=data.model_dump(), message="更新成功")


# -------------------------------------------------------------------
# POST /api/users/me/avatar - 上传头像(R28)
# -------------------------------------------------------------------
@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    上传头像(multipart/form-data,字段名 file):
    - 格式仅 JPG/PNG/WebP(4001),大小 ≤ 2MB(4002)
    - 文件名 uuid4 随机生成(防枚举),落盘 ./data/avatars/{user_id}/
    - 更新 avatar_url 与 avatar_file_path,响应仅返回 avatar_url
    """
    content = avatar_service.read_upload_limited(file.file)
    ext = avatar_service.validate_avatar_upload(file.filename or "", file.content_type or "", content)
    avatar_url, file_path = avatar_service.save_avatar_file(current_user.user_id, content, ext)

    current_user.avatar_url = avatar_url
    current_user.avatar_file_path = file_path
    await db.flush()

    return success(data={"avatar_url": avatar_url}, message="头像已更新")


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
    # BUG-015:个人 token 须打到平台设置配置的自建 GitLab 实例校验;
    # 平台未配置 gitlab_url 时传 None,维持旧的默认 gitlab.com 行为
    gitlab_url = await get_setting(db, "gitlab_url")
    api_base = f"{gitlab_url.rstrip('/')}/api/v4" if gitlab_url else None
    gitlab_info = await GitlabService.verify_token(req.gitlab_token, api_base=api_base)
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
