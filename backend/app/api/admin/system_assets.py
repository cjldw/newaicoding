"""系统级 Claude 资产采集路由 - R5(超管:POST /api/admin/system-assets/collect)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.services import system_asset_service
from app.services.audit_service import audit_write

router = APIRouter(prefix="/api/admin/system-assets", tags=["平台管理"])


@router.post("/collect")
async def collect_system_assets(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    超管触发系统级采集:Runner 临时容器起→探→毁(用后即毁),
    镜像内置 skills/MCP 覆盖入库;并发采集复用首次结果。
    探测失败 502 可重试(旧数据保留)。审计照 R1 先例:API 层 audit_write。
    """
    data = await system_asset_service.collect(db, current_user.user_id)
    # 审计(模式 C:operator 在 API 层;detail 只记计数与镜像标识,不落探测原文)
    await audit_write(
        db, current_user, "system_assets.collect",
        target_type="claude_system_asset",
        detail={
            "skills": data["skills"],
            "mcps": data["mcps"],
            "image_tag": data["image_tag"],
        },
    )
    return success(data=data)
