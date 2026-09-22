"""知识库空间路由 - R20(列表/建库/详情/导入同步/页面 CRUD/搜索)"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, success
from app.database import get_db
from app.models.knowledge_base import KnowledgeDoc
from app.models.project import Project
from app.models.user import User
from app.services import kb_import_service, kb_service, project_member_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["知识库空间"])


async def _project_or_404(db: AsyncSession, project_id: str) -> Project:
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    return project


# ---------------------------------------------------------------------------
# 列表 / 创建
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/knowledge-bases")
async def list_kbs(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目知识库列表(成员;不含 content)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    items = await kb_service.list_kbs(db, project_id)
    return success(data={"items": items, "total": len(items)})


class CreateKBRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    source_type: str = Field(default="blank")
    source_config: dict | None = Field(default=None)


@router.post("/projects/{project_id}/knowledge-bases")
async def create_kb(
    project_id: str,
    req: CreateKBRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """建库(editor;blank 或 repo_import;repo_import 置 importing 后台拉取)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")

    if req.source_type not in ("blank", "repo_import"):
        raise BizError(20005, "配置无效:source_type 必须为 blank 或 repo_import")

    kb, _hint = await kb_service.create_kb(
        db, project, current_user,
        name=req.name, description=req.description,
        source_type=req.source_type, source_config=req.source_config,
    )

    # repo_import:入队后台导入(bot token 实时读平台设置;R18 通知钩子在服务内)
    dns_note = None
    if kb.source_type == "repo_import":
        from app.services.platform_settings_service import get_setting

        kb.import_status = "importing"
        await db.flush()
        gitlab_url = await get_setting(db, "gitlab_url") or ""
        bot_token = (await get_setting(db, "gitlab_bot_token")) or ""
        if bot_token and gitlab_url:
            try:
                kb_import_service.spawn_import(kb.kb_id, bot_token, gitlab_url)
            except BizError as e:
                if e.code == 20007:
                    dns_note = "导入进行中,请稍候"
        else:
            kb.import_status = "failed"
            kb.import_error = "平台 GitLab 未配置,无法导入"
            await db.flush()

    data = kb_service._kb_brief(kb)
    if dns_note:
        data["hint"] = dns_note
    return success(data=data, message="创建成功")


# ---------------------------------------------------------------------------
# 详情 / 改名 / 删除
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/knowledge-bases/{kb_id}")
async def get_kb(
    project_id: str,
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """知识库详情(树;不含 content)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    kb = await kb_service.get_kb_or_404(db, project_id, kb_id)
    docs = (await db.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.kb_id == kb_id)
        .order_by(KnowledgeDoc.path.asc())
    )).scalars().all()
    data = kb_service._kb_brief(kb)
    data["docs"] = [
        {"doc_id": d.doc_id, "title": d.title, "path": d.path, "sort_order": d.sort_order}
        for d in docs
    ]
    return success(data=data)


class UpdateKBRequest(BaseModel):
    name: str = Field(default=None, max_length=64)
    description: str = Field(default=None, max_length=255)


@router.patch("/projects/{project_id}/knowledge-bases/{kb_id}")
async def update_kb(
    project_id: str,
    kb_id: str,
    req: UpdateKBRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """改名/描述(editor)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    kb = await kb_service.get_kb_or_404(db, project_id, kb_id)
    data = await kb_service.rename_kb(db, kb, req.name, req.description)
    return success(data=data, message="更新成功")


@router.delete("/projects/{project_id}/knowledge-bases/{kb_id}")
async def delete_kb(
    project_id: str,
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删库(editor;级联删 docs;不影响 GitLab repo)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    kb = await kb_service.get_kb_or_404(db, project_id, kb_id)
    await kb_service.delete_kb(db, kb)
    return success(message="知识库已删除")


# ---------------------------------------------------------------------------
# 导入 / 同步
# ---------------------------------------------------------------------------
async def _trigger_import(db: AsyncSession, project: Project, kb, current_user: User):
    await kb_service.require_kb_editor(db, project, current_user)
    from app.services.platform_settings_service import get_setting

    gitlab_url = await get_setting(db, "gitlab_url") or ""
    bot_token = (await get_setting(db, "gitlab_bot_token")) or ""
    if not (bot_token and gitlab_url):
        raise BizError(20005, "平台 GitLab 未配置,无法导入")
    try:
        kb_import_service.spawn_import(kb.kb_id, bot_token, gitlab_url)
    except BizError as e:
        if e.code == 20007:
            raise
        raise
    kb.import_status = "importing"
    kb.import_error = None
    await db.flush()


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/import")
async def import_kb(
    project_id: str,
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """首次导入重试(editor;repo_import 专用;并发互斥 20007)"""
    project = await _project_or_404(db, project_id)
    kb = await kb_service.get_kb_or_404(db, project_id, kb_id)
    if kb.source_type != "repo_import":
        raise BizError(20005, "空白知识库无导入配置")
    if kb.import_status == "importing" or kb_import_service.is_importing(kb_id):
        raise BizError(20007, "导入进行中,请稍候")
    await _trigger_import(db, project, kb, current_user)
    return success(data={"kb_id": kb.kb_id, "import_status": "importing"})


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/sync")
async def sync_kb(
    project_id: str,
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重新导入(同步):按 source_config 覆盖;并发互斥 20007"""
    project = await _project_or_404(db, project_id)
    kb = await kb_service.get_kb_or_404(db, project_id, kb_id)
    if kb.source_type != "repo_import":
        raise BizError(20005, "空白知识库无同步配置")
    if kb.import_status == "importing" or kb_import_service.is_importing(kb_id):
        raise BizError(20007, "导入进行中,请稍候")
    await _trigger_import(db, project, kb, current_user)
    return success(data={"kb_id": kb.kb_id, "import_status": "importing"})


# ---------------------------------------------------------------------------
# 页面(blank)
# ---------------------------------------------------------------------------
class CreateDocRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    parent_path: str = Field(default="", max_length=240)


@router.get("/knowledge-bases/{kb_id}/docs")
async def list_docs(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """页面树(不含 content)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == kb.project_id)
        )).scalars().first(), current_user, "viewer")
    from app.models.knowledge_base import KnowledgeDoc

    docs = (await db.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.kb_id == kb_id)
        .order_by(KnowledgeDoc.path.asc())
    )).scalars().all()
    return success(data={"items": [
        {"doc_id": d.doc_id, "title": d.title, "path": d.path, "sort_order": d.sort_order}
        for d in docs
    ]})


@router.post("/knowledge-bases/{kb_id}/docs")
async def create_doc(
    kb_id: str,
    req: CreateDocRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新建页面(blank + editor;repo_import → 403 20002)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == kb.project_id)
    )).scalars().first()
    await kb_service.require_kb_editor(db, project, current_user)
    kb_service.ensure_writable(kb)
    data = await kb_service.create_doc(db, kb, current_user, req.title, req.parent_path)
    return success(data=data)


@router.get("/knowledge-bases/{kb_id}/docs/{doc_id}")
async def get_doc(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """页面详情(含 content)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == kb.project_id)
        )).scalars().first(), current_user, "viewer")
    doc = await kb_service.get_doc_or_404(db, kb_id, doc_id)
    return success(data={
        "doc_id": doc.doc_id, "kb_id": doc.kb_id, "title": doc.title,
        "path": doc.path, "content": doc.content, "sort_order": doc.sort_order,
        "source_file_path": doc.source_file_path,
        "updated_by": doc.updated_by, "updated_at": doc.updated_at,
    })


class UpdateDocRequest(BaseModel):
    title: str = Field(default=None, max_length=128)
    content: str = Field(default=None)


@router.put("/knowledge-bases/{kb_id}/docs/{doc_id}")
async def update_doc(
    kb_id: str,
    doc_id: str,
    req: UpdateDocRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新页面(blank + editor;repo_import 403 20002)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == kb.project_id)
        )).scalars().first(), current_user, "editor")
    kb_service.ensure_writable(kb)
    doc = await kb_service.get_doc_or_404(db, kb_id, doc_id)
    data = await kb_service.update_doc(db, kb, current_user, doc, req.title, req.content)
    return success(data=data)


@router.delete("/knowledge-bases/{kb_id}/docs/{doc_id}")
async def delete_doc(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除页面(blank + editor)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == kb.project_id)
        )).scalars().first(), current_user, "editor")
    kb_service.ensure_writable(kb)
    doc = await kb_service.get_doc_or_404(db, kb_id, doc_id)
    await kb_service.delete_doc(db, kb, doc)
    return success(message="已删除")


# ---------------------------------------------------------------------------
# 库内搜索
# ---------------------------------------------------------------------------
@router.get("/knowledge-bases/{kb_id}/search")
async def search_kb(
    kb_id: str,
    q: str = Query(min_length=1, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """库内标题+全文搜索(FULLTEXT ngram;相关度排序;snippet 高亮)"""
    kb = await kb_service.get_kb_or_404(db, None, kb_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == kb.project_id)
        )).scalars().first(), current_user, "viewer")
    data = await kb_service.search_docs(db, kb_id, q, page, page_size)
    return success(data=data)
