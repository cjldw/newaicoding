"""平台设置路由 - GET/PUT /api/admin/platform-settings(超管;R2;权限收口 R19)"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.services import gitlab_service, platform_settings_service

router = APIRouter(prefix="/api/admin/platform-settings", tags=["平台管理"])


# -------------------------------------------------------------------
# GET /api/admin/platform-settings - 获取全部配置(敏感项打码)
# -------------------------------------------------------------------
@router.get("")
async def get_platform_settings(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管读取平台配置;gitlab_bot_token / gitlab_webhook_secret 打码回显,不回明文"""
    data = await platform_settings_service.get_all_masked(db)
    return success(data=data)


# -------------------------------------------------------------------
# PUT /api/admin/platform-settings - 部分更新(白名单 key;敏感项加密落盘)
# -------------------------------------------------------------------
@router.put("")
async def update_platform_settings(
    payload: Dict[str, Any],
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    超管更新配置(部分更新 {key: value});仅白名单 key 可写,非法值 2007。
    变更即时生效(读取处实时查表);审计留 TODO(R19)。
    """
    updated = await platform_settings_service.update_settings(db, current_user.user_id, payload)
    return success(data={"updated": updated})


# -------------------------------------------------------------------
# POST /api/admin/platform-settings/test-connection - 测试 GitLab 连接
# -------------------------------------------------------------------
@router.post("/test-connection")
async def test_connection(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """用已保存的 gitlab_url + bot token 调 GitLab GET /api/v4/version 验证连通性"""
    gitlab_url, bot_token, _ = await platform_settings_service.get_gitlab_bot_config(db)
    result = await gitlab_service.bot_test_connection(bot_token, gitlab_url)
    return success(data=result)
