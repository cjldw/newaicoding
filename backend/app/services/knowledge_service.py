"""知识库服务 - R14(列表/搜索/详情/创建/发布/提升 + 归档数据)"""

import logging
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.knowledge_entry import KnowledgeEntry
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.user import User
from app.services.project_member_service import require_project_role

logger = logging.getLogger(__name__)


def _entry_brief(e: KnowledgeEntry) -> dict:
    return {
        "entry_id": e.entry_id,
        "type": e.type,
        "title": e.title,
        "tags": e.tags or [],
        "status": e.status,
        "created_by": e.created_by,
        "created_at": e.created_at,
        "project_id": e.project_id,
        "req_id": e.req_id,
    }


async def get_entry_or_404(db: AsyncSession, entry_id: str) -> KnowledgeEntry:
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.entry_id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise BizError(404, "知识条目不存在", status_code=404)
    return entry


# ---------------------------------------------------------------------------
# 列表(项目级 / 平台级;FULLTEXT 检索 + tag/type 过滤)
# ---------------------------------------------------------------------------
async def list_entries(
    db: AsyncSession,
    *,
    scope: str,
    project_id: Optional[str],
    q: Optional[str] = None,
    tag: Optional[str] = None,
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    include_drafts: bool = True,
) -> dict:
    """
    scope="project":project_id 匹配;scope="platform":project_id IS NULL。
    q 走 FULLTEXT(MATCH...AGAINST,ngram);tag 走 JSON_CONTAINS。
    include_drafts=False 时仅 published(平台级 Tab 口径)。
    """
    conditions = []
    if scope == "platform":
        conditions.append(KnowledgeEntry.project_id.is_(None))
        if not include_drafts:
            conditions.append(KnowledgeEntry.status == "published")
    else:
        conditions.append(KnowledgeEntry.project_id == project_id)

    use_fulltext = bool(q) and len(q.strip()) >= 2
    if use_fulltext:
        # ngram 全文;布尔模式便于短词(两个独立 text 对象,避免 bindparams 复用冲突)
        conditions.append(text(
            "MATCH(title, content) AGAINST(:kw IN BOOLEAN MODE)"
        ).bindparams(kw=q.strip()))
    elif q:
        # 单字符退化为 LIKE 前缀
        conditions.append(KnowledgeEntry.title.like(f"%{q.strip()}%"))
    if tag:
        conditions.append(text("JSON_CONTAINS(tags, :tag_json)").bindparams(
            tag_json=__import__("json").dumps(tag, ensure_ascii=False)
        ))
    if type:
        conditions.append(KnowledgeEntry.type == type)

    total = (await db.execute(
        select(func.count(KnowledgeEntry.id)).where(*conditions)
    )).scalar() or 0

    order = []
    if use_fulltext:
        order.append(text("MATCH(title, content) AGAINST(:kw IN BOOLEAN MODE) DESC").bindparams(kw=q.strip()))
    order.append(KnowledgeEntry.created_at.desc())
    order.append(KnowledgeEntry.id.desc())

    rows = (await db.execute(
        select(KnowledgeEntry).where(*conditions).order_by(*order)
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return {
        "items": [_entry_brief(e) for e in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 创建 / 发布 / 提升
# ---------------------------------------------------------------------------
async def create_entry(
    db: AsyncSession, project_id: Optional[str], operator: Optional[User],
    type: str, title: str, content: str,
    tags: Optional[list] = None, source_links: Optional[list] = None,
    status: str = "published", created_by_kind: str = "human",
    req_id: str = "manual",
) -> dict:
    """创建条目(项目内成员建项目级;AI 提取默认 draft;req_id 缺省 manual)"""
    entry = KnowledgeEntry(
        project_id=project_id,
        req_id=req_id,
        type=type,
        title=title,
        content=content,
        tags=tags or [],
        source_links=source_links or [],
        created_by=created_by_kind,
        status=status,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    operator_id = operator.user_id if operator is not None else "system"
    logger.info("知识条目创建 entry=%s scope=%s by=%s kind=%s",
                entry.entry_id, "platform" if project_id is None else project_id,
                operator_id, created_by_kind)
    return _entry_brief(entry)


async def publish_entry(db: AsyncSession, entry_id: str, operator: User) -> None:
    """发布条目(draft → published;owner/editor)"""
    entry = await get_entry_or_404(db, entry_id)
    if entry.status == "published":
        return
    if entry.project_id is not None:
        project = (await db.execute(
            select(Project).where(Project.project_id == entry.project_id)
        )).scalars().first()
        await require_project_role(db, project, operator, "editor")
    entry.status = "published"
    await db.flush()
    logger.info("知识条目发布 entry=%s by=%s", entry_id, operator.user_id)


async def promote_entry(db: AsyncSession, entry_id: str, operator: User) -> None:
    """提升到平台级(仅 owner;project_id 置 null)"""
    entry = await get_entry_or_404(db, entry_id)
    if entry.project_id is None:
        return
    project = (await db.execute(
        select(Project).where(Project.project_id == entry.project_id)
    )).scalars().first()
    await require_project_role(db, project, operator, "owner")
    entry.project_id = None
    await db.flush()
    logger.info("知识条目提升平台级 entry=%s by=%s", entry_id, operator.user_id)
