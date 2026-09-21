"""预览路由 - R10(任务工作台预览列表;网关本体归 R15)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.services import preview_service

router = APIRouter(prefix="/api/tasks", tags=["预览"])


@router.get("/{task_id}/previews")
async def list_task_previews(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务预览列表(端口/预览 URL/状态;前端 3s 轮询)"""
    items = await preview_service.get_task_previews(db, task_id)
    return success(data={"items": items})
