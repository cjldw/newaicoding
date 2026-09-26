"""Skills 路由 - R17 平台级 Skills 市场(JWT)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.services import platform_settings_service, skill_service

router = APIRouter(prefix="/api/skills", tags=["Skills"])


@router.get("/market/sources")
async def list_market_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """R1(skills 市场):市场源列表(JWT 登录即可;未配置时返回默认两源种子)。
    data 直接为源数组 [{name,type,base}]"""
    sources = await platform_settings_service.get_setting(db, "skill_market_sources")
    return success(data=sources)


@router.get("")
async def list_market_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """平台级 Skills 市场列表(所有登录用户可见)"""
    items = await skill_service.list_market_skills(db)
    return success(data={"items": items})


@router.get("/{skill_id}")
async def get_skill_detail(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Skill 详情(含 Markdown content)"""
    data = await skill_service.get_skill_detail(db, skill_id)
    return success(data=data)
