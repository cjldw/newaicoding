"""平台级 Skills 管理路由 - R17(超管)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.schemas.skill import AdminCreateSkillRequest, AdminUpdateSkillRequest
from app.services import skill_service

router = APIRouter(prefix="/api/admin/skills", tags=["平台管理"])


@router.get("")
async def admin_list_skills(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:平台级 Skills 列表(含 content 供编辑)"""
    items = await skill_service.list_market_skills(db)
    out = []
    for item in items:
        detail = await skill_service.get_skill_detail(db, item["skill_id"])
        out.append(detail)
    return success(data={"items": out})


@router.post("")
async def admin_create_skill(
    req: AdminCreateSkillRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:创建平台级 Skill"""
    data = await skill_service.admin_create_skill(db, current_user, req.name, req.description, req.content)
    return success(data=data, message="创建成功")


@router.patch("/{skill_id}")
async def admin_update_skill(
    skill_id: str,
    req: AdminUpdateSkillRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:更新平台级 Skill"""
    data = await skill_service.admin_update_skill(db, current_user, skill_id, req)
    return success(data=data, message="更新成功")


@router.delete("/{skill_id}")
async def admin_delete_skill(
    skill_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:删除平台级 Skill(级联删安装关联)"""
    await skill_service.admin_delete_skill(db, current_user, skill_id)
    return success(message="删除成功")
