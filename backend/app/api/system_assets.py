"""系统级资产只读展示路由 - R6(登录用户:GET /api/system-assets)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.services import system_asset_service

router = APIRouter(prefix="/api/system-assets", tags=["平台管理"])


@router.get("")
async def list_system_assets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    系统级已安装 skills/MCP 只读列表(PRD-B R2 两处展示的数据源):
    任意登录用户可读(JWT 即可,非超管专属);写口(采集)仍超管专属见 R5。
    """
    data = await system_asset_service.list_system_assets(db)
    return success(data=data)
