"""项目路由 - R2 项目管理(列表/创建/详情/更新/删除/归档/仓库绑定解绑)"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import success
from app.database import get_db
from app.models.user import User
from app.schemas.project import (
    AddRepoRequest,
    CreateProjectRequest,
    UpdateProjectRequest,
)
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["项目"])


# -------------------------------------------------------------------
# GET /api/projects - 项目列表(分页)
# -------------------------------------------------------------------
@router.get("")
async def list_projects(
    status: str = Query(default="active"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目列表(口径:我创建的项目;status=active 默认)"""
    data = await project_service.list_projects(db, current_user, status, page, page_size)
    return success(data=data)


# -------------------------------------------------------------------
# POST /api/projects - 创建项目(auto/manual 绑定主仓库)
# -------------------------------------------------------------------
@router.post("")
async def create_project(
    req: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建项目并绑定主仓库;成功返回 project_id/slug/main_repo"""
    data = await project_service.create_project(db, current_user, req)
    return success(data=data, message="项目创建成功")


# -------------------------------------------------------------------
# GET /api/projects/{project_id} - 项目详情
# -------------------------------------------------------------------
@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目详情(owner/超管/internal 可见;private 非成员 404)"""
    project = await project_service.get_project_or_404(db, project_id)
    project_service._ensure_can_view(project, current_user)
    data = await project_service.build_detail(db, project)
    return success(data=data)


# -------------------------------------------------------------------
# PATCH /api/projects/{project_id} - 更新项目
# -------------------------------------------------------------------
@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新项目(name/description/default_branch/visibility;仅 owner)"""
    data = await project_service.update_project(db, current_user, project_id, req)
    return success(data=data, message="更新成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id} - 删除项目(软删 7 天)
# -------------------------------------------------------------------
@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """软删项目(status=deleted,列表隐藏;7 天后物理删除,不动 GitLab repo)"""
    await project_service.delete_project(db, current_user, project_id)
    return success(message="项目已删除(软删,7天后物理删除)")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/archive - 归档项目
# -------------------------------------------------------------------
@router.post("/{project_id}/archive")
async def archive_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档项目(只读;容器停止/部署下线在 R8/R7 联动)"""
    await project_service.archive_project(db, current_user, project_id)
    return success(message="项目已归档")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/repos - 追加绑定仓库
# -------------------------------------------------------------------
@router.post("/{project_id}/repos")
async def add_repo(
    project_id: str,
    req: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """追加绑定仓库(test/docs/other;bot 校验权限;同 repo 不可重复绑定)"""
    data = await project_service.add_repo(db, current_user, project_id, req)
    return success(data=data, message="仓库绑定成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id}/repos/{repo_id} - 解绑仓库
# -------------------------------------------------------------------
@router.delete("/{project_id}/repos/{repo_id}")
async def unbind_repo(
    project_id: str,
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑仓库(main 不可解绑;解绑后不动 GitLab repo)"""
    await project_service.unbind_repo(db, current_user, project_id, repo_id)
    return success(message="仓库已解绑")
