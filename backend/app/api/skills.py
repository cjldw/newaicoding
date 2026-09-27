"""Skills 路由 - R17 平台级 Skills 市场(JWT)"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.user import User
from app.services import platform_settings_service, skill_market_service, skill_service

router = APIRouter(prefix="/api/skills", tags=["Skills"])

# R2(skills 市场):limit 范围(契约 1-50,默认 20;非整数/越界均走 BizError 400 而非 422)
SKILL_MARKET_LIMIT_DEFAULT = 20
SKILL_MARKET_LIMIT_MIN = 1
SKILL_MARKET_LIMIT_MAX = 50


@router.get("/market/sources")
async def list_market_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """R1(skills 市场):市场源列表(JWT 登录即可;未配置时返回默认两源种子)。
    data 直接为源数组 [{name,type,base}]"""
    sources = await platform_settings_service.get_setting(db, "skill_market_sources")
    return success(data=sources)


@router.get("/market/search")
async def search_market_skills(
    market: str = Query(""),
    q: str = Query(""),
    limit: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """R2(skills 市场):市场搜索(后端代理双市场,归一化 + 5min 内存缓存)。
    limit 收原始串自行 int() 解析(类型声明 int 时非整数会被 FastAPI 折成 422);
    data = {market, items:[{name,description,installs,ref,market}]}"""
    q_trimmed = (q or "").strip()
    if not q_trimmed:
        raise BizError(ErrCode.SKILL_MARKET_PARAM_INVALID, "搜索词 q 不能为空", status_code=400)
    if limit is None:
        limit_val = SKILL_MARKET_LIMIT_DEFAULT
    else:
        try:
            limit_val = int(limit.strip())
        except ValueError:
            raise BizError(
                ErrCode.SKILL_MARKET_PARAM_INVALID, "limit 需为整数", status_code=400
            )
    if not (SKILL_MARKET_LIMIT_MIN <= limit_val <= SKILL_MARKET_LIMIT_MAX):
        raise BizError(
            ErrCode.SKILL_MARKET_PARAM_INVALID,
            f"limit 需在 {SKILL_MARKET_LIMIT_MIN}-{SKILL_MARKET_LIMIT_MAX} 范围内",
            status_code=400,
        )
    data = await skill_market_service.search(db, market, q_trimmed, limit_val)
    return success(data=data)


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
