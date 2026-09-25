"""知识库路由 - R14(归档数据/知识条目 CRUD/发布/提升)- R2(详情权限/代码引用)- R1(双类型创建/分支列表)"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.project import Project, ProjectRepo
from app.models.user import User
from app.services import gitlab_service, knowledge_service, project_member_service

router = APIRouter(prefix="/api", tags=["知识库"])

logger = logging.getLogger(__name__)


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
    # R4 契约:detail 同时返回 created_by_user_id 与 permissions(R3 列已有值)
    data["created_by_user_id"] = entry.created_by_user_id
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
# R3 编辑 / 删除
# ---------------------------------------------------------------------------
class UpdateKnowledgeRequest(BaseModel):
    """R3 编辑条目请求体:全字段可选,仅显式提供的字段生效;
    AI 条目仅 tags 允许(其余字段 → 400 + 20013,由服务层白名单拦截)"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=128)
    type: Optional[str] = Field(default=None, min_length=1, max_length=32)
    tags: Optional[list[str]] = None
    content: Optional[str] = None
    source_links: Optional[list[dict]] = None


@router.patch("/knowledge/{entry_id}")
async def update_knowledge(
    entry_id: str,
    req: UpdateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    编辑条目(R3):
    - 人工条目:创建者本人(created_by_user_id 相等)或项目 owner/editor 全字段
    - AI 条目:仅 tags 生效,携带其他可编辑字段 → 400 + 20013「AI 条目仅支持编辑标签」
    - 平台级条目:仅超管
    审计 knowledge.update 记录操作人(沿用现有审计体系)
    """
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    provided = req.model_dump(exclude_unset=True)
    if "source_links" in provided and provided["source_links"] is not None \
            and entry.project_id is not None:
        # A 型代码引用校验与创建口同口径(仓库归属项目/路径 1-10 个;仅项目级)
        await _validate_code_source_links(db, entry.project_id, provided["source_links"])
    changes = {k: v for k, v in provided.items() if v is not None}
    if not changes:
        raise BizError(400, "未提供任何可更新字段", status_code=400)
    entry = await knowledge_service.update_entry(db, entry, current_user, changes)
    return success(data=knowledge_service._entry_brief(entry), message="已保存")


@router.delete("/knowledge/{entry_id}")
async def delete_knowledge(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除条目(R3,物理删除无版本管理):
    - 项目级:创建者本人或 owner/editor;平台级:仅超管
    - 审计 knowledge.delete 记录操作人
    """
    entry = await knowledge_service.get_entry_or_404(db, entry_id)
    await knowledge_service.delete_entry(db, entry, current_user)
    return success(message="已删除")


# ---------------------------------------------------------------------------
# 创建 / 发布 / 提升
# ---------------------------------------------------------------------------
class CreateKnowledgeRequest(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=128)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    source_links: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _content_required_for_direct_create(self):
        """R1 字段定义:A 型(含 code 引用)content 可选=说明文字;
        B 型直接创建仍必填正文(缺省 422,与存量 min_length=1 口径一致)"""
        has_code = any(
            isinstance(link, dict) and link.get("type") == "code"
            for link in (self.source_links or [])
        )
        if not has_code and len(self.content) < 1:
            raise ValueError("直接创建必须填写 Markdown 正文")
        return self


# R1 A 型代码引用上限(DEVPLAN/R1.md:paths 1-10 个、单个 ≤500 字符)
MAX_CODE_LINK_PATHS = 10
MAX_CODE_LINK_PATH_LEN = 500


async def _validate_code_source_links(
    db: AsyncSession, project_id: str, source_links: Optional[list[dict]]
) -> None:
    """
    R1 创建校验:source_links 含 type="code" 对象时——
    repo_id/branch/paths 必填(缺 → 400);repo_id 必属本项目(否 → 20011);
    paths 去空行后须 1-10 个(越界 → 20010)、单个 ≤500 字符(超 → 400)。
    B 型/无 code 对象不校验(存量行为不变);通过后就地剔除空路径项再落库。
    """
    for link in source_links or []:
        if not isinstance(link, dict) or link.get("type") != "code":
            continue
        paths = link.get("paths")
        if not link.get("repo_id") or not link.get("branch") or not isinstance(paths, list):
            logger.info("知识条目创建缺代码引用必填字段 project=%s", project_id)
            raise BizError(400, "代码引用缺少必填字段(repo_id/branch/paths)", status_code=400)
        cleaned = [p.strip() for p in paths if isinstance(p, str) and p.strip()]
        if not cleaned:
            raise BizError(ErrCode.KB_PATHS_LIMIT, "至少填写 1 个路径", status_code=400)
        if len(cleaned) > MAX_CODE_LINK_PATHS:
            logger.info("知识条目创建路径数超限 project=%s count=%s", project_id, len(cleaned))
            raise BizError(ErrCode.KB_PATHS_LIMIT, "路径最多 10 个", status_code=400)
        if any(len(p) > MAX_CODE_LINK_PATH_LEN for p in cleaned):
            logger.info("知识条目创建单路径超长 project=%s", project_id)
            raise BizError(400, "单个路径不能超过 500 字符", status_code=400)
        repo = (await db.execute(
            select(ProjectRepo).where(
                ProjectRepo.repo_id == str(link["repo_id"]),
                ProjectRepo.project_id == project_id,
            )
        )).scalars().first()
        if repo is None:
            logger.info("知识条目创建仓库不属于项目 project=%s repo_id=%s",
                        project_id, link["repo_id"])
            raise BizError(ErrCode.KB_REPO_MISMATCH, "该仓库不属于本项目", status_code=400)
        link["paths"] = cleaned


@router.post("/projects/{project_id}/knowledge")
async def create_project_knowledge(
    project_id: str,
    req: CreateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目内成员创建知识条目(人工创建直接 published;R1 双类型:A 关联代码 / B 直接创建)"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    await _validate_code_source_links(db, project_id, req.source_links)
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


# ---------------------------------------------------------------------------
# R1 分支列表(关联代码 Dialog 分支下拉)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/repos/{repo_id}/branches")
async def list_repo_branches(
    project_id: str,
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目绑定仓库的分支列表(鉴权项目 viewer;default 分支置顶;[{name, default}])"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    repo = (await db.execute(
        select(ProjectRepo).where(
            ProjectRepo.repo_id == repo_id,
            ProjectRepo.project_id == project_id,
        )
    )).scalars().first()
    if repo is None:
        logger.info("分支列表仓库不属于项目 project=%s repo_id=%s", project_id, repo_id)
        raise BizError(404, "仓库不存在", status_code=404)

    from app.services.platform_settings_service import get_gitlab_bot_config
    gitlab_url, bot_token, _group_id = await get_gitlab_bot_config(db)
    branches = await gitlab_service.bot_list_branches(bot_token, gitlab_url, repo.gitlab_repo_id)
    items = [
        {"name": b.get("name") or "", "default": bool(b.get("default"))}
        for b in branches if isinstance(b, dict)
    ]
    items.sort(key=lambda x: not x["default"])   # 稳定排序:default 分支置顶
    return success(data=items)
