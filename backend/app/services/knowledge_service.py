"""知识库服务 - R14(列表/搜索/详情/创建/发布/提升 + 归档数据)- R2(详情 permissions + 代码引用拉取)"""

import base64
import logging
import time
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.knowledge_entry import KnowledgeEntry
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.user import User
from app.services import gitlab_service
from app.services.project_member_service import get_project_role, require_project_role

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


# ---------------------------------------------------------------------------
# R2 条目详情:读权限 + permissions 块(R3 预埋,后端算好前端零猜测)
# ---------------------------------------------------------------------------
# R3 口径:人工条目可编辑全字段;AI 条目仅 tags(R3 写接口实施时按同一列表校验)
HUMAN_EDITABLE_FIELDS = ["title", "content", "tags", "type", "source_links"]
AI_EDITABLE_FIELDS = ["tags"]


async def entry_permissions(db: AsyncSession, entry: KnowledgeEntry, user: User) -> dict:
    """
    详情页 permissions 块:{can_edit, can_delete, editable_fields}。
    项目级:按有效角色(viewer 只读/editor 可编辑可删/owner 可编辑可删,超管=虚拟 owner);
    平台级:普通用户只读,仅超管可编辑可删(R3 矩阵)。
    注:R3「创建者本人可编辑」依赖 created_by_user_id 列(该列落地后在此追加判断)。
    """
    if entry.project_id is not None:
        project = (await db.execute(
            select(Project).where(Project.project_id == entry.project_id)
        )).scalars().first()
        role = await get_project_role(db, project, user) if project is not None else ""
    else:
        role = "owner" if user.role == "superadmin" else ""

    can_edit = role in ("editor", "owner")
    # R3 口径:创建者本人 + 项目 owner/editor 可删(B1 收口:editor 亦有删除权)
    can_delete = role in ("editor", "owner")
    if not can_edit:
        editable_fields: list = []
    elif entry.created_by == "ai":
        editable_fields = list(AI_EDITABLE_FIELDS)
    else:
        editable_fields = list(HUMAN_EDITABLE_FIELDS)
    return {"can_edit": can_edit, "can_delete": can_delete, "editable_fields": editable_fields}


# ---------------------------------------------------------------------------
# R2 代码引用区:GET /knowledge/{entry_id}/code?path=&refresh=
# ---------------------------------------------------------------------------
MSG_CODE_UNREACHABLE = "代码来源不可达(仓库已解绑或分支已删除)"

_CODE_CACHE_TTL_SECONDS = 300          # R2 契约:进程内缓存 TTL 5 分钟
_CODE_CACHE_MAX_ENTRIES = 512          # 简单防膨胀上限
MAX_DIR_FILES = 200                    # 目录递归文件数上限(超出截断 partial:true)
MAX_DIR_BODY_BYTES = 10 * 1024 * 1024  # 目录响应体上限 10MB

# R2 契约:二进制文件只列节点不拉内容(按扩展名预判 + 内容 utf-8 解码兜底)
_BINARY_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "bmp", "ico", "webp", "tiff", "heic",
    "zip", "tar", "gz", "tgz", "bz2", "xz", "rar", "7z",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "exe", "dll", "so", "dylib", "bin", "o", "a", "obj", "lib", "wasm",
    "woff", "woff2", "ttf", "otf", "eot",
    "mp3", "mp4", "avi", "mov", "mkv", "wav", "flac", "webm",
    "jar", "class", "pyc", "pyo", "db", "sqlite", "pack", "idx",
}

# 进程内缓存:键 {repo_id}:{branch}:{path} → (monotonic 时间戳, 响应体)
_code_cache: dict[str, tuple[float, dict]] = {}


def _is_binary_name(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return False
    return name.rsplit(".", 1)[-1].lower() in _BINARY_EXTENSIONS


def _decode_file_payload(data: dict, path: str) -> dict:
    """GitLab file JSON → 响应节点(base64→utf-8;解码失败=二进制,只回元数据)"""
    raw = base64.b64decode(data.get("content") or "")
    size = data.get("size")
    if size is None:
        size = len(raw)
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": path, "kind": "file", "size": size, "binary": True}
    return {"path": path, "kind": "file", "content": content, "size": size}


def _ensure_dir_chain(nodes: dict, dir_path: str, root: dict, base: str) -> dict:
    """沿 dir_path 逐级补齐目录节点并挂到 root 树上,返回末级目录节点"""
    rel = dir_path[len(base):].strip("/") if base else dir_path.strip("/")
    cur, cur_path = root, base
    for part in filter(None, rel.split("/")):
        cur_path = f"{cur_path}/{part}" if cur_path else part
        node = nodes.get(cur_path)
        if node is None:
            node = {"path": cur_path, "kind": "dir", "children": []}
            nodes[cur_path] = node
            cur["children"].append(node)
        cur = node
    return cur


async def _fetch_dir_tree(bot_token: str, gitlab_url: str, gitlab_repo_id: int,
                          branch: str, base: str, flat: list) -> dict:
    """递归 flat 树 → 组装 children 嵌套;文件数 >200 截断 partial:true,响应体 >10MB 同截断
    (partial 时附 partial_reason:count=按文件数截断 / size=响应体超限,S3)"""
    root: dict = {"path": base, "kind": "dir", "children": []}
    nodes: dict[str, dict] = {base: root}
    file_count = 0
    total_bytes = 0
    partial = False
    partial_reason = ""

    for item in flat:
        p = (item.get("path") or "").rstrip("/")
        if not p or p == base or (base and not p.startswith(base + "/")):
            continue
        parent = nodes.get(p.rsplit("/", 1)[0]) or _ensure_dir_chain(
            nodes, p.rsplit("/", 1)[0], root, base)
        if item.get("type") == "tree":
            node = nodes.get(p)
            if node is None:
                node = {"path": p, "kind": "dir", "children": []}
                nodes[p] = node
                parent["children"].append(node)
            continue

        # blob:超 200 个文件 → 截断(不拉内容、不列节点)
        if file_count >= MAX_DIR_FILES:
            partial = True
            partial_reason = "count"
            continue
        if _is_binary_name(p):
            node = {"path": p, "kind": "file", "size": item.get("size") or 0, "binary": True}
        else:
            try:
                f = await gitlab_service.bot_get_file(bot_token, gitlab_url, gitlab_repo_id, branch, p)
            except BizError as e:
                if e.code == 404:
                    continue   # 遍历期间被删除的文件:跳过不阻断
                raise
            node = _decode_file_payload(f, p)
        size = node.get("size") or 0
        if total_bytes + size > MAX_DIR_BODY_BYTES:
            partial = True
            partial_reason = "size"
            continue
        total_bytes += size
        file_count += 1
        parent["children"].append(node)

    payload = {"path": base, "kind": "dir", "tree": root["children"],
               "size": total_bytes, "partial": partial}
    if partial:
        payload["partial_reason"] = partial_reason
    return payload


async def get_entry_code(db: AsyncSession, entry: KnowledgeEntry, path: str,
                         refresh: bool = False) -> dict:
    """
    R2 代码引用区按路径拉取:
    - 读 source_links 首个 code 对象(repo_id/branch)→ ProjectRepo(解绑→20012)
    - 文件:bot_get_file 全量返回不截断;目录:bot_get_tree recursive + 逐文件 bot_get_file 组树
    - 进程内缓存键 {repo_id}:{branch}:{path} TTL 5 分钟;refresh=1 穿透
    - path 404 → 20012「代码来源不可达」(与解绑同码)
    """
    link = next(
        (l for l in (entry.source_links or [])
         if isinstance(l, dict) and l.get("type") == "code"),
        None,
    )
    base = (path or "").strip("/")
    if not base:
        # S2 收口:空 path 会落到整仓递归拉取,直接拒绝(不进 GitLab 调用)
        logger.info("知识条目代码路径为空 entry=%s", entry.entry_id)
        raise BizError(ErrCode.KB_CODE_UNREACHABLE, "缺少代码引用路径(path)", status_code=400)
    if link is None or not link.get("repo_id"):
        logger.info("知识条目无代码来源 entry=%s path=%s", entry.entry_id, base)
        raise BizError(ErrCode.KB_CODE_UNREACHABLE, MSG_CODE_UNREACHABLE, status_code=404)

    repo_id = str(link["repo_id"])
    branch = link.get("branch") or "main"
    repo_row = (await db.execute(
        select(ProjectRepo).where(ProjectRepo.repo_id == repo_id)
    )).scalars().first()
    if repo_row is None:
        logger.info("知识条目代码来源已解绑 entry=%s repo_id=%s", entry.entry_id, repo_id)
        raise BizError(ErrCode.KB_CODE_UNREACHABLE, MSG_CODE_UNREACHABLE, status_code=404)
    gitlab_repo_id = repo_row.gitlab_repo_id

    cache_key = f"{repo_id}:{branch}:{base}"
    now = time.monotonic()
    if not refresh:
        cached = _code_cache.get(cache_key)
        if cached is not None and now - cached[0] < _CODE_CACHE_TTL_SECONDS:
            logger.info("知识条目代码缓存命中 entry=%s key=%s", entry.entry_id, cache_key)
            return cached[1]

    from app.services.platform_settings_service import get_gitlab_bot_config
    gitlab_url, bot_token, _group_id = await get_gitlab_bot_config(db)

    # 先按文件取(常规主路径);404 再按目录递归取;两者皆空 → 不可达
    try:
        data = await gitlab_service.bot_get_file(bot_token, gitlab_url, gitlab_repo_id, branch, base)
        payload = _decode_file_payload(data, base)
    except BizError as e:
        if e.code != 404:
            raise
        flat = await gitlab_service.bot_get_tree(
            bot_token, gitlab_url, gitlab_repo_id, branch, base, recursive=True)
        if not flat:
            logger.info("知识条目代码路径不可达 entry=%s repo=%s branch=%s path=%s",
                        entry.entry_id, repo_id, branch, base)
            raise BizError(ErrCode.KB_CODE_UNREACHABLE, MSG_CODE_UNREACHABLE, status_code=404)
        payload = await _fetch_dir_tree(bot_token, gitlab_url, gitlab_repo_id, branch, base, flat)

    if len(_code_cache) >= _CODE_CACHE_MAX_ENTRIES:
        _code_cache.clear()   # 简单 expiry:超限整体清空(容量远大于单页消费量)
    _code_cache[cache_key] = (time.monotonic(), payload)
    return payload
