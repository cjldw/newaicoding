"""知识库路由 - R14(归档数据/知识条目 CRUD/发布/提升)"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services import knowledge_service, project_member_service

router = APIRouter(prefix="/api", tags=["知识库"])


# ---------------------------------------------------------------------------
# 归档页数据
# ---------------------------------------------------------------------------
@router.get("/requirements/{req_id}/archive")
async def get_archive(
    req_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档页数据(时间线 + 归档总结路径 + 关联知识条目)"""
    from app.services.archive_service import get_archive_data
    from app.services.project_service import get_requirement_or_404 as _get_req
    # R3 的 get_requirement_or_404 在 requirement_service
    from app.services.requirement_service import get_requirement_or_404

    req = await get_requirement_or_404(db, req_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == req.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    data = await get_archive_data(db, req)
    return success(data=data)


# ---------------------------------------------------------------------------
# 知识库列表(项目级 / 平台级)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/knowledge")
async def list_project_knowledge(
    project_id: str,
    q: str = Query(default=None),
    tag: str = Query(default=None),
    type: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目知识库(项目成员;含 draft)"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    data = await knowledge_service.list_entries(
        db, scope="project", project_id=project_id,
        q=q, tag=tag, type=type, page=page, page_size=page_size,
        include_drafts=True,
    )
    return success(data=data)


@router.get("/knowledge")
async def list_platform_knowledge(
    q: str = Query(default=None),
    tag: str = Query(default=None),
    type: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """平台知识库(全员可见;仅 published)"""
    data = await knowledge_service.list_entries(
        db, scope="platform", project_id=None,
        q=q, tag=tag, type=type, page=page, page_size=page_size,
        include_drafts=False,
    )
    return success(data=data)


async def _ensure_entry_readable(db: AsyncSession, entry, user: User) -> None:
    """R2 权限口径:项目级条目要求项目 viewer+(非成员 403);平台级登录即可"""
    if entry.project_id is None:
        return
    project = (await db.execute(
        select(Project).where(Project.project_id == entry.project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "知识条目不存在", status_code=404)
    await project_member_service.require_project_role(db, project, user, "viewer")


@router.get("/knowledge/{entry_id}")
async def get_knowledge_detail(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """知识条目详情(Markdown 内容;R2 收紧权限 + permissions 块 R3 预埋)"""
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    await _ensure_entry_readable(db, entry, current_user)
    # R14 存量 bug 顺带修复:_entry_brief 为同步函数,误 await 导致 detail 必 500
    data = knowledge_service._entry_brief(entry)
    data["content"] = entry.content
    data["source_links"] = entry.source_links or []
    data["permissions"] = await knowledge_service.entry_permissions(db, entry, current_user)
    return success(data=data)


@router.get("/knowledge/{entry_id}/code")
async def get_knowledge_entry_code(
    entry_id: str,
    path: str = Query(default=""),
    refresh: str = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    条目代码引用按路径拉取(R2 A 型详情逐块消费,失败互不影响):
    - 文件全量返回不截断;目录递归拉全组树(>200 文件截断 partial:true)
    - 服务端缓存 TTL 5 分钟,refresh=1 穿透;404/仓库解绑 → code 20012
    - 鉴权同 detail(项目级 viewer / 平台级登录)
    """
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    await _ensure_entry_readable(db, entry, current_user)
    data = await knowledge_service.get_entry_code(
        db, entry, path=path, refresh=refresh in ("1", "true"),
    )
    return success(data=data)


# ---------------------------------------------------------------------------
# 创建 / 发布 / 提升
# ---------------------------------------------------------------------------
class CreateKnowledgeRequest(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    source_links: list[dict] = Field(default_factory=list)


@router.post("/projects/{project_id}/knowledge")
async def create_project_knowledge(
    project_id: str,
    req: CreateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目内成员创建知识条目(人工创建直接 published)"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    data = await knowledge_service.create_entry(
        db, project_id, current_user,
        type=req.type, title=req.title, content=req.content,
        tags=req.tags, source_links=req.source_links,
        status="published", created_by_kind="human",
    )
    return success(data=data, message="创建成功")


@router.post("/knowledge/{entry_id}/publish")
async def publish_knowledge(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发布条目(draft → published;owner/editor)"""
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    if entry.project_id is not None:
        project = (await db.execute(
            select(Project).where(Project.project_id == entry.project_id)
        )).scalars().first()
        await project_member_service.require_project_role(db, project, current_user, "editor")
    else:
        from app.core.auth import require_superadmin
        # 平台级条目发布:超管(与创建口一致)
        if current_user.role != "superadmin":
            raise BizError(ErrCode.NOT_SUPERADMIN, "需要平台超级管理员权限", status_code=403)
    await knowledge_service.publish_entry(db, entry_id, current_user)
    return success(message="已发布")


@router.post("/knowledge/{entry_id}/promote")
async def promote_knowledge(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提升到平台级(仅项目 owner)"""
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    if entry.project_id is None:
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "该条目已是平台级")
    project = (await db.execute(
        select(Project).where(Project.project_id == entry.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "owner")
    await knowledge_service.promote_entry(db, entry_id, current_user)
    return success(message="已提升到平台级")
