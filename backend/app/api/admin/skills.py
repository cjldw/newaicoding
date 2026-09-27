"""平台级 Skills 管理路由 - R17(超管)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.schemas.skill import (
    AdminCreateSkillRequest,
    AdminUpdateSkillRequest,
    InstallRemoteSkillRequest,
)
from app.services import skill_market_service, skill_service

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


@router.post("/install-remote")
async def admin_install_remote_skill(
    req: InstallRemoteSkillRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:市场搜索安装进平台官方库(R4.F1)。
    fetch_skill_md(market,ref) → parse 校验(400 17003)→ 入库 scope=platform
    (source=market + source_url,无 project_skills 关联;同名覆盖沿用 R3 原地覆盖语义)
    → 审计(platform 级,无 project_id);
    失败口径同 R3:参数 400(17004)→ 拉取失败 502(17005)「市场暂不可用」→ 256KB 上限 400。
    响应 data:{skill_id,name,source,source_url,extra_files}"""
    fetched = await skill_market_service.fetch_skill_md(db, req.market, req.ref)
    data = await skill_service.admin_install_skill_from_market(
        db, current_user, fetched["content"], fetched["source_url"]
    )
    data["extra_files"] = fetched["extra_files"]

    from app.services.audit_service import audit_write

    await audit_write(
        db, current_user, "skill.install_remote_platform",
        project_id=None, target_type="skill", target_id=data["skill_id"],
        detail={"market": req.market, "ref": req.ref, "source_url": fetched["source_url"],
                "extra_files": fetched["extra_files"]},
    )
    return success(data=data, message="安装成功")


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
