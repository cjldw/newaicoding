"""需求路由 - R3(CRUD + 打磨/评审/取消状态机)"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.requirement import (
    CancelRequest,
    CreateRequirementRequest,
    ReviewRequest,
    UpdateRequirementRequest,
)
from app.services import project_member_service, requirement_service

router = APIRouter(prefix="/api", tags=["需求"])


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/requirements - 需求列表
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/requirements")
async def list_requirements(
    project_id: str,
    status: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """需求列表(项目成员;status 可选过滤)"""
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")

    conditions = [Requirement.project_id == project_id]
    if status:
        conditions.append(Requirement.status == status)

    total = (await db.execute(
        select(func.count(Requirement.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(Requirement).where(*conditions)
        .order_by(Requirement.created_at.desc(), Requirement.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for r in rows:
        items.append({
            "req_id": r.req_id,
            "title": r.title,
            "status": r.status,
            "priority": r.priority,
            "created_by": await requirement_service._creator_brief(db, r.created_by),
            "created_at": r.created_at,
        })
    return success(data={"items": items, "total": total, "page": page, "page_size": page_size})


# ---------------------------------------------------------------------------
# POST /api/projects/{project_id}/requirements - 创建需求
# ---------------------------------------------------------------------------
@router.post("/projects/{project_id}/requirements")
async def create_requirement(
    project_id: str,
    req: CreateRequirementRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建需求(owner/editor;所有绑定 repo 切需求分支)"""
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    data = await requirement_service.create_requirement(
        db, project, current_user, req.model_dump(exclude_none=True),
    )
    return success(data=data, message="需求创建成功")


# ---------------------------------------------------------------------------
# GET /api/requirements/{req_id} - 需求详情
# ---------------------------------------------------------------------------
@router.get("/requirements/{req_id}")
async def get_requirement(
    req_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """需求详情(含关联任务)"""
    req = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, req.project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    return success(data=await requirement_service.build_detail(db, req))


# ---------------------------------------------------------------------------
# PATCH /api/requirements/{req_id} - 更新需求
# ---------------------------------------------------------------------------
@router.patch("/requirements/{req_id}")
async def update_requirement(
    req_id: str,
    req: UpdateRequirementRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新需求(owner/editor;评审中不可编辑 title/description)"""
    requirement = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, requirement.project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")

    if requirement.status == "reviewing" and (req.title is not None or req.description is not None):
        raise BizError(ErrCode.NOT_IN_POLISHING, "评审中需求不可编辑")

    if req.title is not None:
        requirement.title = req.title
    if req.background is not None:
        requirement.background = req.background
    if req.description is not None:
        requirement.description = req.description
    if req.acceptance_criteria is not None:
        requirement.acceptance_criteria = req.acceptance_criteria
    if req.priority is not None:
        requirement.priority = req.priority
    if req.prototype_links is not None:  # R4:不传 = 不动;[] = 清空;非法整组 400
        requirement.prototype_links = requirement_service._normalize_prototype_links(req.prototype_links)
    await db.flush()
    # updated_at 带 onupdate=func.now(),flush 实改字段后该属性被置为过期;
    # build_detail 同步访问会触发 MissingGreenlet(R4 QA 用例暴露)→ 照 create 口径显式 refresh
    await db.refresh(requirement)
    return success(data=await requirement_service.build_detail(db, requirement), message="更新成功")


# ---------------------------------------------------------------------------
# POST /api/requirements/{req_id}/polish - 开始打磨
# ---------------------------------------------------------------------------
@router.post("/requirements/{req_id}/polish")
async def start_polish(
    req_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """开始打磨(draft → polishing;拉起打磨容器 + Claude 会话)"""
    requirement = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, requirement.project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    task_id = await requirement_service.start_polish(db, project, current_user, requirement)
    return success(data={"task_id": task_id}, message="打磨任务已启动")


# ---------------------------------------------------------------------------
# POST /api/requirements/{req_id}/submit-review - 提交评审
# ---------------------------------------------------------------------------
@router.post("/requirements/{req_id}/submit-review")
async def submit_review(
    req_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交评审(polishing → reviewing)"""
    requirement = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, requirement.project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await requirement_service.submit_review(db, requirement)
    # R25 审计:requirement.submit_review(service 签名无 operator → 模式 C API 层)
    from app.services.audit_service import audit_write

    await audit_write(
        db, current_user, "requirement.submit_review",
        project_id=project.project_id, target_type="requirement", target_id=req_id,
    )
    return success(message="已提交评审")


# ---------------------------------------------------------------------------
# POST /api/requirements/{req_id}/review - 评审(通过/驳回)
# ---------------------------------------------------------------------------
@router.post("/requirements/{req_id}/review")
async def review_requirement(
    req_id: str,
    req: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """评审(owner/editor;通过用评审人 token commit PRD;驳回填理由回打磨)"""
    requirement = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, requirement.project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await requirement_service.review_requirement(
        db, project, current_user, requirement, req.approved, req.reject_reason
    )
    return success(message="评审通过" if req.approved else "已驳回,可继续打磨")


# ---------------------------------------------------------------------------
# POST /api/requirements/{req_id}/cancel - 取消需求
# ---------------------------------------------------------------------------
@router.post("/requirements/{req_id}/cancel")
async def cancel_requirement(
    req_id: str,
    req: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消需求(owner;分支保留只读,30 天后自动删除)"""
    requirement = await requirement_service.get_requirement_or_404(db, req_id)
    from app.services.project_service import get_project_or_404

    project = await get_project_or_404(db, requirement.project_id)
    from app.services.project_member_service import require_project_role, get_project_role

    role = await get_project_role(db, project, current_user)
    require_project_role(db, project, current_user, "viewer")
    if role != "owner":
        raise BizError(ErrCode.NO_PROJECT_PERMISSION, "仅项目所有者可取消需求", status_code=403)
    await requirement_service.cancel_requirement(db, current_user, requirement, req.reason)
    return success(message="需求已取消")
