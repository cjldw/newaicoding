"""知识库空间服务 - R20(CRUD/导入同步/页面操作/搜索)

- blank:平台内编辑,存 knowledge_docs
- repo_import:bot token 经 GitLab API 拉取 .md 生成只读快照;后台任务 + 事务内整体替换
- 限制:单库 ≤500 页;单文件 >1MB 跳过;导入超时 5 分钟 failed(可重试)
- 并发互斥:同库 importing 中重复触发 → 20007
- repo_import 写操作(含超管)→ 403 20002(source_type 决定,非角色)
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc
from app.models.project import Project, ProjectRepo
from app.models.user import User
from app.services.project_member_service import require_project_role

logger = logging.getLogger(__name__)

MAX_DOCS_PER_KB = 500
MAX_IMPORT_FILE_BYTES = 1024 * 1024  # 单文件 >1MB 跳过
IMPORT_TIMEOUT_SECONDS = 300         # 导入超时 5 分钟
_PATH_INVALID_RE = re.compile(r"[^0-9A-Za-z一-鿿/_-]+")


# ---------------------------------------------------------------------------
# 查询与定位
# ---------------------------------------------------------------------------
async def get_kb_or_404(db: AsyncSession, project_id: Optional[str], kb_id: str) -> KnowledgeBase:
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
    kb = result.scalar_one_or_none()
    if kb is None or (project_id is not None and kb.project_id != project_id):
        raise BizError(20006, "知识库不存在", status_code=404)
    return kb


async def get_doc_or_404(db: AsyncSession, kb_id: str, doc_id: str) -> KnowledgeDoc:
    result = await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.kb_id == kb_id, KnowledgeDoc.doc_id == doc_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise BizError(20006, "页面不存在", status_code=404)
    return doc


def ensure_writable(kb: KnowledgeBase) -> None:
    """repo_import 只读:任何写操作(含超管)一律 403 20002(source_type 决定,非角色)"""
    if kb.source_type == "repo_import":
        raise BizError(ErrCode.KB_IMPORT_READONLY, "无权限执行此操作", status_code=403)


async def require_kb_editor(db: AsyncSession, project: Project, operator: User) -> None:
    await require_project_role(db, project, operator, "editor")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_kb(
    db: AsyncSession, project: Project, operator: User,
    name: str, description: str, source_type: str,
    source_config: Optional[dict],
) -> tuple[KnowledgeBase, Optional[str]]:
    """
    建库:blank(空)或 repo_import(校验 repo 归属与路径;置 importing,后台拉取)。
    返回 (kb, hint);hint=无 test 语义的提示信息(如目录为空)。
    """
    dup = await db.execute(
        select(KnowledgeBase.id).where(
            KnowledgeBase.project_id == project.project_id,
            KnowledgeBase.name == name,
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        raise BizError(20001, "名称已存在")

    config = None
    if source_type == "repo_import":
        if not source_config or "repo_id" not in source_config:
            raise BizError(20005, "配置无效:缺少 repo_id")
        repo_id = source_config["repo_id"]
        repo = (await db.execute(
            select(ProjectRepo).where(
                ProjectRepo.project_id == project.project_id,
                ProjectRepo.repo_id == repo_id,
            )
        )).scalars().first()
        if repo is None:
            raise BizError(20005, "配置无效:仓库不属于本项目")
        branch = source_config.get("branch") or project.default_branch
        paths = source_config.get("paths") or []
        paths = [p.strip().strip("/") for p in paths if p and p.strip()]
        if not paths:
            raise BizError(20005, "配置无效:至少选择一个导入目录")
        config = {"repo_id": repo_id, "branch": branch, "paths": paths}

    kb = KnowledgeBase(
        project_id=project.project_id,
        name=name,
        description=description or "",
        source_type=source_type,
        source_config=config,
        import_status="idle",
        created_by=operator.user_id,
    )
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    logger.info("知识库创建 kb=%s type=%s by=%s", kb.kb_id, source_type, operator.user_id)
    return kb, None


def _kb_brief(kb: KnowledgeBase, docs_count: Optional[int] = None) -> dict:
    data = {
        "kb_id": kb.kb_id,
        "name": kb.name,
        "description": kb.description or "",
        "source_type": kb.source_type,
        "source_config": kb.source_config,
        "import_status": kb.import_status,
        "import_error": kb.import_error,
        "last_synced_at": kb.last_synced_at,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
    }
    if docs_count is not None:
        data["docs_count"] = docs_count
    return data


async def list_kbs(db: AsyncSession, project_id: str) -> list[dict]:
    rows = (await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.project_id == project_id)
        .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id.desc())
    )).scalars().all()
    out = []
    for kb in rows:
        cnt = (await db.execute(
            select(func.count(KnowledgeDoc.id)).where(KnowledgeDoc.kb_id == kb.kb_id)
        )).scalar() or 0
        out.append(_kb_brief(kb, docs_count=cnt))
    return out


async def rename_kb(db: AsyncSession, kb: KnowledgeBase, name: Optional[str], description: Optional[str]) -> dict:
    if name is not None and name != kb.name:
        dup = await db.execute(
            select(KnowledgeBase.id).where(
                KnowledgeBase.project_id == kb.project_id,
                KnowledgeBase.name == name,
                KnowledgeBase.kb_id != kb.kb_id,
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise BizError(20001, "名称已存在")
        kb.name = name
    if description is not None:
        kb.description = description
    await db.flush()
    # R2.F4:同 update_doc —— flush 后 _kb_brief 读过期的 updated_at 触发 MissingGreenlet
    await db.refresh(kb)
    return _kb_brief(kb)


async def delete_kb(db: AsyncSession, kb: KnowledgeBase) -> int:
    """删库:级联删 docs;不影响 GitLab repo。返回删除页面数。"""
    cnt = (await db.execute(
        select(func.count(KnowledgeDoc.id)).where(KnowledgeDoc.kb_id == kb.kb_id)
    )).scalar() or 0
    await db.execute(delete(KnowledgeDoc).where(KnowledgeDoc.kb_id == kb.kb_id))
    await db.delete(kb)
    await db.flush()
    logger.info("知识库删除 kb=%s docs=%d", kb.kb_id, cnt)
    return cnt


# ---------------------------------------------------------------------------
# 页面操作(blank;repo_import 一律 403)
# ---------------------------------------------------------------------------
def _slugify_title(title: str) -> str:
    slug = _PATH_INVALID_RE.sub("-", title.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return (slug or "page")[:120]


async def _unique_path(db: AsyncSession, kb_id: str, path: str) -> str:
    """path 冲突自动 -1(不报错)"""
    candidate = path
    i = 1
    while True:
        dup = await db.execute(
            select(KnowledgeDoc.id).where(
                KnowledgeDoc.kb_id == kb_id, KnowledgeDoc.path == candidate
            ).limit(1)
        )
        if dup.scalar_one_or_none() is None:
            return candidate
        candidate = f"{path}-{i}"
        i += 1


async def create_doc(db: AsyncSession, kb: KnowledgeBase, operator: User,
                     title: str, parent_path: str = "") -> dict:
    ensure_writable(kb)
    cnt = (await db.execute(
        select(func.count(KnowledgeDoc.id)).where(KnowledgeDoc.kb_id == kb.kb_id)
    )).scalar() or 0
    if cnt >= MAX_DOCS_PER_KB:
        raise BizError(20003, "页面数已达上限")

    slug = _slugify_title(title)
    parent = parent_path.strip("/") if parent_path else ""
    base_path = f"{parent}/{slug}" if parent else slug
    path = await _unique_path(db, kb.kb_id, base_path)

    doc = KnowledgeDoc(
        kb_id=kb.kb_id,
        title=title,
        path=path,
        content="",
        created_by=operator.user_id,
        updated_by=operator.user_id,
    )
    db.add(doc)
    await db.flush()
    logger.info("页面创建 kb=%s path=%s", kb.kb_id, path)
    return {"doc_id": doc.doc_id, "title": doc.title, "path": doc.path, "sort_order": doc.sort_order}


async def update_doc(db: AsyncSession, kb: KnowledgeBase, operator: User,
                     doc: KnowledgeDoc, title: Optional[str], content: Optional[str]) -> dict:
    ensure_writable(kb)
    if title is not None:
        doc.title = title
    if content is not None:
        doc.content = content
    doc.updated_by = operator.user_id
    await db.flush()
    # R2.F4:onupdate=func.now() 使 updated_at 过期,flush 后直接读会触发
    # 隐式同步 SELECT → MissingGreenlet(编辑保存恒 500);refresh 后再取值
    await db.refresh(doc)
    return {"doc_id": doc.doc_id, "updated_at": doc.updated_at}


async def delete_doc(db: AsyncSession, kb: KnowledgeBase, doc: KnowledgeDoc) -> None:
    ensure_writable(kb)
    await db.delete(doc)
    await db.flush()


# ---------------------------------------------------------------------------
# 搜索(FULLTEXT ngram;标题+正文)
# ---------------------------------------------------------------------------
async def search_docs(db: AsyncSession, kb_id: str, q: str, page: int = 1, page_size: int = 20) -> dict:
    q = q.strip()
    if not q:
        return {"items": [], "total": 0}

    ft = text("MATCH(title, content) AGAINST(:kw IN BOOLEAN MODE)").bindparams(kw=q)
    conditions = [KnowledgeDoc.kb_id == kb_id, ft]
    total = (await db.execute(
        select(func.count(KnowledgeDoc.id)).where(*conditions)
    )).scalar() or 0

    rows = (await db.execute(
        select(KnowledgeDoc).where(*conditions)
        .order_by(text("MATCH(title, content) AGAINST(:kw IN BOOLEAN MODE) DESC").bindparams(kw=q))
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    def _snippet(content: str) -> str:
        idx = content.lower().find(q.lower())
        if idx == -1:
            return content[:120]
        start = max(0, idx - 60)
        end = min(len(content), idx + len(q) + 60)
        frag = content[start:end]
        return frag.replace(q, f"<em>{q}</em>")

    items = [
        {"doc_id": d.doc_id, "title": d.title, "path": d.path,
         "snippet": _snippet(d.content)}
        for d in rows
    ]
    return {"items": items, "total": total}
