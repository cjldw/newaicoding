"""需求服务 - R3(需求 CRUD + 状态机 + 打磨/评审/取消)"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.user import User
from app.services import container_service, notification_service, runner_service
from app.services.audit_service import audit_write  # R25 审计接入(事务内,失败不阻塞)
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)

# R2 PRD 回传:最大副本字节数(16MB,MEDIUMTEXT 物理上限)
_PRD_CONTENT_MAX_BYTES = 16 * 1024 * 1024


# ---------------------------------------------------------------------------
# R2:PRD 回传(容器 → 平台副本;路径后置:实际路径发现 + 回写自愈)
# ---------------------------------------------------------------------------
def _truncate_prd(content: str, req_id: str = "") -> str:
    """超 _PRD_CONTENT_MAX_BYTES(16MB,MEDIUMTEXT 物理上限)按字节截断;
    回退到有效 UTF-8 字符边界(去掉尾部不完整的 multibyte 序列)。容器/GitLab 两路回传共用。"""
    content_bytes = content.encode("utf-8")
    if len(content_bytes) <= _PRD_CONTENT_MAX_BYTES:
        return content
    logger.warning(
        "[prd-sync] truncated oversized content req_id=%s truncated_to=%d bytes",
        req_id, _PRD_CONTENT_MAX_BYTES,
    )
    return content_bytes[:_PRD_CONTENT_MAX_BYTES].decode("utf-8", errors="ignore")


async def _discover_prd_path_in_container(db: AsyncSession, task_id: str) -> tuple:
    """
    容器内实际 PRD 路径发现(路径后置自愈:prd_file_path 为空或固定路径读空时调用)。
    返回 (repo 相对路径 or None, 已验证非空的 content)。
    候选优先级:
      ① docs/ 一层子目录中目录名含任务短 id(task_id[:8])的 <dir>/PRD.md
        —— Q26 建议路径尾段即 taskShortId,恰好覆盖技能服从 PRD_FILE_PATH env 的情况
      ② 根候选:PRD.md、docs/PRD.md
      ③ docs/ 其余子目录的 <dir>/PRD.md(多命中取首个 + warning)
    逐候选 task_read_file 验证非空即命中;全程异常吞掉返回 (None, "")——发现器是兜底,不阻塞主链。
    """
    from app.services import file_service

    try:
        short_id = (task_id or "")[:8]
        try:
            docs_items = await file_service.task_file_list(db, task_id, "/workspace/main/docs")
        except Exception:
            docs_items = []  # docs 目录不存在/列取失败 → 只剩根候选

        subdir_names = [it.get("path", "").strip("/") for it in docs_items
                        if it.get("type") == "dir" and it.get("path")]
        subdir_names = [n for n in subdir_names if n]
        preferred = [n for n in subdir_names if short_id and short_id in n]
        others = [n for n in subdir_names if n not in preferred]

        candidates = [f"docs/{n}/PRD.md" for n in preferred]
        candidates += ["PRD.md", "docs/PRD.md"]
        candidates += [f"docs/{n}/PRD.md" for n in others]

        for rel in candidates:
            try:
                data = await file_service.task_read_file(db, task_id, "/workspace/main/" + rel)
            except Exception:
                continue  # 单候选不存在/读失败 → 试下一个
            content = data.get("content") or ""
            if content.strip():
                if len(others) > 1 and not (short_id and short_id in rel) and rel.startswith("docs/"):
                    logger.warning(
                        "[prd-discover] multiple PRD candidates under docs/, picked first "
                        "task=%s picked=%s all_subdirs=%s", task_id, rel, others,
                    )
                return rel, content
        return None, ""
    except Exception as e:
        logger.warning("[prd-discover] failed task_id=%s: %s", task_id, e)
        return None, ""


async def sync_prd_from_container(db: AsyncSession, task_id: str) -> None:
    """
    R2 同步逻辑:从容器回读 prd_file_path 并更新 requirement.prd_content。
    全程 try/except,任何异常不外抛(静默跳过 + [prd-sync] 日志)。
    由 _sync_prd_background 包装(独立 session)或测试直接传入 db 调用。
    """
    try:
        from app.models.task import Task
        from app.services import file_service

        # ① 校验 task 存在且 type=='requirement' 且 req_id 非空
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            logger.warning("[prd-sync] task not found task_id=%s", task_id)
            return
        if task.type != "requirement":
            logger.info("[prd-sync] skip non-requirement task task_id=%s type=%s", task_id, task.type)
            return
        if not task.req_id:
            logger.info("[prd-sync] skip task without req_id task_id=%s", task_id)
            return

        # ② 查 requirement;查不到 → 静默跳过(悬空引用)
        req_result = await db.execute(
            select(Requirement).where(Requirement.req_id == task.req_id)
        )
        req = req_result.scalar_one_or_none()
        if req is None:
            logger.warning("[prd-sync] requirement not found req_id=%s", task.req_id)
            return

        # ③ 库内固定路径(存量预生成 / 已回写实际路径);为空不再跳过——
        #   路径后置改造:prd_file_path 由打磨完成后实际路径回写产生,启动时为空属常态
        prd_path = (req.prd_file_path or "").strip()

        # ④ 固定路径的容器绝对路径 = /workspace/main/{prd_file_path}(去前导斜杠拼接)
        container_path = ("/workspace/main/" + prd_path.lstrip("/")) if prd_path else ""

        # ⑤ 查 running 容器 + runner 在线(静默 return,不抛 9001)——发现器同样依赖容器在线
        ctr_result = await db.execute(
            select(Container)
            .where(Container.task_id == task_id, Container.status == "running")
            .order_by(Container.id.desc())
            .limit(1)
        )
        container = ctr_result.scalar_one_or_none()
        if container is None:
            logger.info("[prd-sync] skip no running container task_id=%s", task_id)
            return
        if runner_registry.get(container.runner_id) is None:
            logger.info("[prd-sync] skip runner offline runner_id=%s", container.runner_id)
            return

        # ⑥ 固定路径回读(有路径才读);R37.F11(BUG-086)读取失败(路径失效/
        #    文件不存在)不再中止——降级为空内容走 ⑦ 发现器自愈。原:异常直接
        #    中止整个同步,失效的 prd_file_path 把发现器弄瞎(实证:任务 89e587e8
        #    的每轮回传全程空转,PRD 实际写在 AI 自选目录里却永远回不来)
        content = ""
        if container_path:
            try:
                file_data = await file_service.task_read_file(db, task_id, container_path)
                content = file_data.get("content") or ""
            except Exception as e:
                logger.info(
                    "[prd-sync] stored path read failed, fallback to discovery req_id=%s path=%s err=%s",
                    req.req_id, prd_path, e,
                )

        # ⑦ 固定路径读空/启动时无路径 → 容器内发现实际 PRD 路径(路径后置自愈):
        #   命中即回写 prd_file_path——实际路径自此成为关联键,后续直取命中不再进发现器
        if not content.strip():
            discovered_path, discovered_content = await _discover_prd_path_in_container(db, task_id)
            if discovered_path:
                req.prd_file_path = discovered_path
                logger.info(
                    "[prd-sync] prd path healed req_id=%s stored=%r discovered=%s",
                    req.req_id, prd_path, discovered_path,
                )
                content = discovered_content

        # 空 → 跳过
        if not content:
            logger.info("[prd-sync] skip empty content req_id=%s", req.req_id)
            return

        # 超 16MB → 截断 + warning(按字节截断后回退到字符边界,避免 UTF-8 半字符)
        content = _truncate_prd(content, req.req_id)

        # ⑧ UPDATE requirement.prd_content(ORM 属性赋值,flush 由调用方负责)
        req.prd_content = content
        await db.flush()

        byte_len = len(content.encode("utf-8"))
        logger.info("[prd-sync] success req_id=%s bytes=%d", req.req_id, byte_len)

    except Exception as e:
        logger.warning("[prd-sync] failed task_id=%s: %s", task_id, e, exc_info=True)


async def get_prd_content_with_fallback(db: AsyncSession, req: Requirement) -> tuple:
    """
    R3 PRD 副本读取降级链(路径后置:③ 层含 GitLab 侧路径发现+回写自愈):
    ① req.prd_content truthy → (content, 'db')
    ② 定位打磨任务 → 容器在线 → sync_prd_from_container 回读回填 → (content, 'container')
    ③ 容器不可用或回读落空 → _sync_prd_from_gitlab(直取 404 → tree 发现)→ (content, 'gitlab')
    ④ 都没有 → (None, 'none')

    打磨任务定位:requirement.polish_task_id 优先;空则按 req_id 找 type=requirement 最新任务。
    """
    # ① DB 副本优先
    if req.prd_content:
        logger.info("[prd-view] hit db req_id=%s", req.req_id)
        return (req.prd_content, "db")

    # ② 定位打磨任务
    from app.models.task import Task

    task_id = None
    if req.polish_task_id:
        task_id = req.polish_task_id
    else:
        # 按 req_id 找 type=requirement 最新任务
        result = await db.execute(
            select(Task.task_id)
            .where(Task.req_id == req.req_id, Task.type == "requirement")
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(1)
        )
        task_id = result.scalar_one_or_none()

    if not task_id:
        logger.info("[prd-view] no polish task found req_id=%s", req.req_id)
        return (None, "none")

    # ② 查 running 容器 + runner 在线;不可用不早退,继续走 GitLab 兜底
    ctr_result = await db.execute(
        select(Container)
        .where(Container.task_id == task_id, Container.status == "running")
        .order_by(Container.id.desc())
        .limit(1)
    )
    container = ctr_result.scalar_one_or_none()
    if container is None or runner_registry.get(container.runner_id) is None:
        logger.info("[prd-view] container unavailable task_id=%s → gitlab fallback", task_id)
    else:
        # 调 R2 同步函数回读回填(内部自捕获异常,含路径发现+回写)
        try:
            await sync_prd_from_container(db, task_id)
        except Exception as e:
            logger.warning("[prd-view] sync_prd_from_container failed task_id=%s: %s", task_id, e)

        # 重查 req.prd_content 判断回填是否成功
        await db.refresh(req)
        if req.prd_content:
            logger.info("[prd-view] hit container req_id=%s task_id=%s", req.req_id, task_id)
            return (req.prd_content, "container")

    # ③ GitLab 兜底(finish_task 销毁容器前已把 PRD push 到 req_branch,容器销毁后仍可取回;
    #   含 GitLab 侧实际路径发现 + prd_file_path 回写)
    gitlab_content = await _sync_prd_from_gitlab(db, req)
    if gitlab_content:
        logger.info("[prd-view] hit gitlab req_id=%s task_id=%s", req.req_id, task_id)
        return (gitlab_content, "gitlab")

    logger.info("[prd-view] all sources empty req_id=%s", req.req_id)
    return (None, "none")


async def _sync_prd_background(task_id: str) -> None:
    """
    R2 后台包装:自开 session(请求级 db 在 SSE 响应结束后关闭,后台任务禁用之)
    全程捕获异常不外抛(fire-and-forget 语义)。
    """
    from app.database import async_session_factory

    try:
        async with async_session_factory() as session:
            await sync_prd_from_container(session, task_id)
            # 自开 session 无请求级 commit(请求级由 get_db 收尾 commit),flush 不提交
            # 即随 close 回滚——补 commit 落库(prd_content 与自愈回写的 prd_file_path 都依赖)
            await session.commit()
    except Exception:
        logger.warning("[prd-sync] background task unexpected error task_id=%s", task_id, exc_info=True)


async def _sync_prd_from_gitlab(db: AsyncSession, req: Requirement) -> str:
    """
    读侧第③层 GitLab 兜底(路径后置自愈的容器外入口):
    finish_task 销毁容器前已把全部变更 push 到 work_branch(打磨任务即 req_branch),
    容器销毁后按 (主仓库, req_branch, prd_file_path) 仍可取回 PRD。
    直取 404 或路径为空 → GitLab tree 发现(docs/ 一层子目录,任务短 id 优先,同容器内发现器口径),
    命中即回写 req.prd_file_path + 截断 + 回填 prd_content 并返回内容;任何失败返回 ""(兜底不外抛)。
    """
    from app.services import file_service, gitlab_service

    try:
        if not (req.req_branch or "").strip():
            return ""

        project = (await db.execute(
            select(Project).where(Project.project_id == req.project_id)
        )).scalar_one_or_none()
        if project is None:
            return ""
        gitlab_url, bot_token, main_repo = await file_service._gitlab_ctx(db, project)

        async def _fetch(rel: str) -> str:
            """单路径取文件内容(base64 → utf-8);404(未提交过)→ 空串,其余异常上抛"""
            try:
                data = await gitlab_service.bot_get_file(
                    bot_token, gitlab_url, main_repo.gitlab_repo_id, req.req_branch, rel
                )
            except BizError as e:
                if getattr(e, "code", None) == 404:
                    return ""
                raise
            import base64

            return base64.b64decode(data.get("content", "")).decode("utf-8")

        stored_path = (req.prd_file_path or "").strip()
        content = await _fetch(stored_path) if stored_path else ""

        # 直取落空 → GitLab 侧路径发现(与容器内发现器同优先级口径)
        if not content.strip():
            short_id = (req.polish_task_id or "")[:8]
            try:
                tree_items = await gitlab_service.bot_get_tree(
                    bot_token, gitlab_url, main_repo.gitlab_repo_id, req.req_branch, "docs"
                )
            except Exception:
                tree_items = []  # docs 不存在/列取失败 → 只剩根候选
            subdir_names = [it.get("path", "")[len("docs/"):] for it in tree_items
                            if it.get("type") == "tree" and it.get("path", "").startswith("docs/")]
            preferred = [n for n in subdir_names if short_id and short_id in n]
            others = [n for n in subdir_names if n not in preferred]

            candidates = [f"docs/{n}/PRD.md" for n in preferred]
            candidates += ["PRD.md", "docs/PRD.md"]
            candidates += [f"docs/{n}/PRD.md" for n in others]

            for rel in candidates:
                hit = await _fetch(rel)
                if hit.strip():
                    if len(others) > 1 and not (short_id and short_id in rel) and rel.startswith("docs/"):
                        logger.warning(
                            "[prd-gitlab] multiple PRD candidates under docs/, picked first "
                            "req=%s picked=%s all_subdirs=%s", req.req_id, rel, others,
                        )
                    stored_path, content = rel, hit
                    break

        if not content.strip():
            return ""

        # 自愈回写:实际路径成为关联键(下次直取命中)+ 回填平台副本
        if stored_path and stored_path != (req.prd_file_path or "").strip():
            req.prd_file_path = stored_path
            logger.info(
                "[prd-gitlab] prd path healed req_id=%s discovered=%s", req.req_id, stored_path,
            )
        req.prd_content = _truncate_prd(content, req.req_id)
        await db.flush()
        return req.prd_content

    except Exception as e:
        logger.warning("[prd-gitlab] failed req_id=%s: %s", req.req_id, e, exc_info=True)
        return ""


async def _creator_brief(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == user_id))
    u = result.scalar_one_or_none()
    return {
        "user_id": user_id,
        "username": (u.gitlab_username or "") if u else "",
        "nickname": u.nickname if u else None,
    }


async def get_requirement_or_404(db: AsyncSession, req_id: str) -> Requirement:
    result = await db.execute(select(Requirement).where(Requirement.req_id == req_id))
    req = result.scalar_one_or_none()
    if req is None:
        raise BizError(404, "需求不存在", status_code=404)
    return req


async def build_detail(db: AsyncSession, req: Requirement) -> dict:
    """需求详情(含关联任务列表,tasks 表)"""
    from app.models.task import Task

    result = await db.execute(
        select(Task).where(Task.req_id == req.req_id)
        .order_by(Task.created_at.asc(), Task.id.asc())
    )
    from app.services import task_service

    tasks = [
        {
            "task_id": t.task_id,
            "type": t.type,
            "title": t.title,
            "status": t.status,
            # BUG-077:补齐 created_at/display_status,前端「创建时间」列与状态徽章渲染依赖
            "created_at": t.created_at,
            "display_status": task_service.derive_display_status(t.status, None),
        }
        for t in result.scalars().all()
    ]

    reviewer = None
    if req.reviewed_by:
        reviewer = await _creator_brief(db, req.reviewed_by)
    return {
        "req_id": req.req_id,
        "project_id": req.project_id,  # R2:详情页据此拉项目成员(关联用户 chips/编辑权限/编辑候选)
        "title": req.title,
        "background": req.background,
        "description": req.description,
        "acceptance_criteria": req.acceptance_criteria,
        "status": req.status,
        "priority": req.priority,
        "related_user_ids": req.related_user_ids or [],  # R1:存量 NULL 归一为 []
        "prototype_links": req.prototype_links or [],  # R4:存量 NULL 归一为 []
        "delivery_date": req.delivery_date,  # R5:交付时间(date;NULL → None,前端无值不渲染行)
        "req_branch": req.req_branch,
        "prd_file_path": req.prd_file_path,
        "created_by": await _creator_brief(db, req.created_by),
        "reviewed_by": reviewer,
        "reviewed_at": req.reviewed_at,
        "reject_reason": req.reject_reason,
        "polish_task_id": req.polish_task_id,
        # R35.F1:打磨任务状态透传(前端「重新打磨」按钮可见性,免二次请求)
        "polish_task_status": next((t["status"] for t in tasks if t["task_id"] == req.polish_task_id), None),
        "tasks": tasks,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }


# ---------------------------------------------------------------------------
# 关联用户过滤(R1 创建 / R2 编辑共用)
# ---------------------------------------------------------------------------
async def _filter_related_members(db: AsyncSession, project_id: str, ids: Optional[list]) -> list:
    """
    关联用户口径(PRD-A R1):非项目成员 id **静默剔除**(不报错)+ 去重(保持输入顺序)。
    空/None → [](创建/编辑侧直接落库,详情侧再归一为 [])。
    """
    if not ids:
        return []
    unique_ids = list(dict.fromkeys(ids))  # 去重且保序
    result = await db.execute(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id.in_(unique_ids),
        )
    )
    member_ids = set(result.scalars().all())
    return [uid for uid in unique_ids if uid in member_ids]


# ---------------------------------------------------------------------------
# 原型链接校验(R4 创建 / 编辑共用;与关联用户静默剔除不同:非法整组显式 400)
# ---------------------------------------------------------------------------
def _normalize_prototype_links(links: Optional[list]) -> list:
    """
    原型链接口径(PRD-B R4):≤10 条;url 必须 http(s):// 开头;label 截断 20(空串保留不丢)。
    超限 / URL 非 http(s) → BizError 400 **整组拒绝**;None/缺省/[] → []。
    """
    if not links:
        return []
    if len(links) > 10:
        raise BizError(400, "原型链接最多 10 条", status_code=400)
    normalized: list = []
    for link in links:
        raw = link if isinstance(link, dict) else {}
        url = str(raw.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise BizError(400, "原型链接 URL 需以 http(s):// 开头", status_code=400)
        normalized.append({"label": str(raw.get("label") or "")[:20], "url": url})
    logger.info("原型链接已规范化 raw=%s normalized=%s", len(links), len(normalized))
    return normalized


# ---------------------------------------------------------------------------
# 创建(所有绑定 repo 建需求分支)
# ---------------------------------------------------------------------------
def gen_req_branch_slug(title: str, max_len: int = 10) -> str:
    """
    R34.F1:需求名 → 简称首拼(最多 max_len 字符):
    逐字取拼音首字母(pypinyin FIRST_LETTER);ASCII 字母/数字取其自身小写,
    其余(空白/标点/未识别)忽略;空结果回退 "req"。
    例:「用户登录功能优化」→ yhdlgnyh(截 10);「AI 助手」→ azs;「登录」→ dl。
    """
    import re as _re

    from pypinyin import Style, lazy_pinyin

    text = (title or '').strip()
    if not text:
        return 'req'
    # 先按 [ASCII 字母数字串 | 其它单字] 切分,ASCII 段取首字母,单字走拼音首字母
    out: list[str] = []
    for token in _re.findall(r'[A-Za-z0-9]+|.', text, flags=_re.S):
        if token[0].isascii() and token[0].isalnum():
            out.append(token[0].lower())
        else:
            ini = lazy_pinyin(token, style=Style.FIRST_LETTER, errors='ignore')
            if ini and ini[0] and ini[0][0].isascii() and ini[0][0].isalnum():
                out.append(ini[0][0])
        if len(out) >= max_len:
            break
    return ''.join(out) or 'req'


def default_req_branch(title: str) -> str:
    """
    R34.F1:需求分支默认生成策略(用户口径):feat/{简称首拼≤10}{日期YYYYMMDD}
    日期取 Asia/Shanghai 墙钟(与平台 func.now() +08:00 固化口径一致,BUG-039)。
    """
    from zoneinfo import ZoneInfo

    day = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    return f"feat/{gen_req_branch_slug(title)}{day}"


async def create_requirement(db: AsyncSession, project: Project, operator: User, req_data: dict) -> dict:
    """
    创建需求:生成 req_id/req_branch → 在所有绑定 repo 上从默认分支切需求分支
    → 写 requirements 表(draft)。分支创建失败即整体失败(GitLab 不可用)。
    """
    from app.services import gitlab_service
    from app.services.platform_settings_service import get_gitlab_bot_config

    logger.info("创建需求 project=%s title=%s by=%s", project.project_id, req_data.get("title"), operator.user_id)

    # R4 原型链接:格式校验前置(非法整组 400,避免 GitLab 分支已建的半成品)
    prototype_links = _normalize_prototype_links(req_data.get("prototype_links"))

    # 平台 GitLab 配置(建分支用 bot token;未配置 2001)
    gitlab_url, bot_token, _ = await get_gitlab_bot_config(db)

    req_id = str(uuid.uuid4())
    # R34.F1:默认分支策略 req-{id8} → feat/{需求名首拼≤10}{日期YYYYMMDD}(用户口径)
    branch = req_data.get("req_branch") or default_req_branch(req_data.get("title") or "")

    # 同项目分支名查重(requirements 表口径;GitLab 侧 400 也兜底)
    dup = await db.execute(
        select(Requirement.id).where(
            Requirement.project_id == project.project_id,
            Requirement.req_branch == branch,
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        # R34.F1:自动生成的分支撞名(同项目同日同首拼)→ 追加 req_id 短码脱撞;
        # 显式填写的分支撞名维持报错(用户语义,400 口径不变)
        if req_data.get("req_branch"):
            raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, f"需求分支 {branch} 已存在")
        branch = f"{branch}-{req_id[:4]}"

    # 在所有绑定 repo 建分支(从项目默认分支切出)
    repos_result = await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == project.project_id)
    )
    repos = repos_result.scalars().all()
    for repo in repos:
        await gitlab_service.bot_create_branch(
            bot_token, gitlab_url, repo.gitlab_repo_id, branch, project.default_branch
        )
        logger.info("需求分支已创建 repo=%s branch=%s", repo.gitlab_repo_id, branch)

    # R1 关联用户:剔除非项目成员 + 去重(静默口径)
    related_user_ids = await _filter_related_members(db, project.project_id, req_data.get("related_user_ids"))

    requirement = Requirement(
        req_id=req_id,
        project_id=project.project_id,
        title=req_data["title"],
        background=req_data.get("background"),
        description=req_data["description"],
        acceptance_criteria=req_data.get("acceptance_criteria"),
        req_branch=branch,
        priority=req_data.get("priority", "medium"),
        related_user_ids=related_user_ids,
        prototype_links=prototype_links,  # R4 原型链接(已规范化)
        delivery_date=req_data.get("delivery_date"),  # R5 交付时间(None/缺省 → NULL)
        created_by=operator.user_id,
        status="draft",
    )
    db.add(requirement)
    await db.flush()
    await db.refresh(requirement)

    logger.info("需求创建完成 req=%s branch=%s", requirement.req_id, branch)
    # R25 审计:requirement.create
    await audit_write(
        db, operator, "requirement.create",
        project_id=project.project_id, target_type="requirement", target_id=requirement.req_id,
        detail={"title": req_data.get("title")},
    )
    return {"req_id": requirement.req_id, "req_branch": branch}


# ---------------------------------------------------------------------------
# 状态机:开始打磨
# ---------------------------------------------------------------------------
async def start_polish(db: AsyncSession, project: Project, operator: User, req: Requirement) -> str:
    """
    开始打磨(draft → polishing):
    1. 重复校验(3001)
    2. 经 task_service 创建并启动打磨任务(type=requirement;R13 配置校验 + R8 容器)
    3. status=polishing + polish_task_id;
       prd_file_path 不再预生成——rd-prd 实际写出路径不受平台控制,
       字段改由打磨完成后以实际路径回写(sync_prd_from_container / _sync_prd_from_gitlab 自愈),
       语义:「最近一次打磨的实际 repo 路径,空=尚无打磨成果」

    R35.F1 打磨可重启:status=="polishing" 且 polish_task_id 指向的 task 已终态
    (cancelled/failed/timeout/done)→ 清空 polish_task_id 后走原创建链路(重新打磨);
    关联 task 仍 active(running/pending/cases_review)→ 维持 3001。
    R37.F7(BUG-080):状态门放宽到 reviewing/approved——打磨完成后提交评审/评审通过
    仍可再次打磨(任务须终态),放行后状态回 polishing、polish_task_id 换新任务。
    """
    if req.status == "draft":
        if req.polish_task_id:
            raise BizError(ErrCode.POLISH_ALREADY_RUNNING, "已有打磨任务进行中")
    elif req.status in ("polishing", "reviewing", "approved"):
        # R37.F7(BUG-080):打磨完成后不再锁死在 polishing,reviewing/approved 也可返工重磨;
        # in_progress/done/archived/rejected 落 else 仍 3001(开发态/完结态/归档/已取消不重磨)
        if req.polish_task_id:
            from app.models.task import Task

            old = (await db.execute(
                select(Task.status).where(Task.task_id == req.polish_task_id).limit(1)
            )).scalar_one_or_none()
            if old in ("cancelled", "failed", "timeout", "done") or old is None:
                logger.info("打磨任务已终态(%s),允许再次打磨 req=%s", old, req.req_id)
                req.polish_task_id = None
            else:
                raise BizError(ErrCode.POLISH_ALREADY_RUNNING, "已有打磨任务进行中")
        # polish_task_id 为空(从未打磨或孤儿态)→ 直接走创建链路
    else:
        raise BizError(ErrCode.POLISH_ALREADY_RUNNING, "已有打磨任务进行中")

    from app.services import task_service

    task_id = await task_service.create_polish_task(db, project, req, operator)

    req.status = "polishing"
    req.polish_task_id = task_id
    # prd_file_path 不预生成(容器内建议路径仅经 create_polish_task 的 PRD_FILE_PATH env 传递,
    # 不落库);完成后由实际路径回写——见 sync_prd_from_container 自愈链
    await db.flush()
    logger.info("打磨任务已启动 req=%s task=%s", req.req_id, task_id)
    # R25 审计:requirement.start_polish
    await audit_write(
        db, operator, "requirement.start_polish",
        project_id=req.project_id, target_type="requirement", target_id=req.req_id,
    )
    return task_id


# ---------------------------------------------------------------------------
# 状态机:提交评审 / 评审 / 取消
# ---------------------------------------------------------------------------
async def submit_review(db: AsyncSession, req: Requirement) -> None:
    """提交评审(polishing → reviewing;非 polishing → 3002)"""
    if req.status != "polishing":
        raise BizError(ErrCode.NOT_IN_POLISHING, "需求状态不是打磨中")
    req.status = "reviewing"
    await db.flush()
    logger.info("需求提交评审 req=%s", req.req_id)


async def _notify_related_users_on_approve(db: AsyncSession, req: Requirement, operator: User) -> None:
    """
    R3 评审通过站内通知(PRD-A R3):状态变 approved 时向当次关联用户发站内信。
    收件人口径:related_user_ids 去重(保序)→ 排除操作人 → 过滤仍为项目成员者;
    NULL/空名单 → 零发送。单个发送失败仅记日志继续(调用方再整体兜底,不阻塞评审)。
    """
    ids = [uid for uid in dict.fromkeys(req.related_user_ids or []) if uid != operator.user_id]  # 去重保序 + 排除操作人
    if not ids:
        return

    # 过滤仍为该项目成员(评审时点可能已被移出)
    result = await db.execute(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == req.project_id,
            ProjectMember.user_id.in_(ids),
        )
    )
    member_ids = set(result.scalars().all())
    recipients = [uid for uid in ids if uid in member_ids]
    if len(recipients) < len(ids):
        logger.info(
            "评审通过通知跳过非项目成员 req=%s project=%s skip=%s",
            req.req_id, req.project_id, [uid for uid in ids if uid not in member_ids],
        )
    if not recipients:
        return

    for uid in recipients:
        try:
            await notification_service.send_notification(
                db,
                recipient_id=uid,
                type="review_approved",
                level="normal",
                title=f"需求《{req.title}》已评审通过",
                content="可以开始开发了",
                link=f"/requirements/{req.req_id}",
                project_id=req.project_id,
            )
        except Exception as e:
            logger.warning("评审通过通知单发失败(跳过继续) req=%s recipient=%s: %s", req.req_id, uid, e)
    logger.info("评审通过通知完成 req=%s sent=%d", req.req_id, len(recipients))


async def review_requirement(
    db: AsyncSession, project: Project, operator: User, req: Requirement,
    approved: bool, reject_reason: Optional[str],
) -> None:
    """
    评审(owner/editor):
    - 通过:reviewing → approved;用评审人个人 token 把 PRD commit + push 到 req_branch;销毁打磨容器
    - 驳回:reviewing → polishing;填理由;容器保留继续打磨
    """
    if req.status != "reviewing":
        raise BizError(ErrCode.NOT_IN_POLISHING, "需求状态不是打磨中")

    if approved:
        # 评审人须绑定 GitLab token(个人 token commit/push)
        if not operator.gitlab_token_encrypted:
            raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "请先在个人设置绑定 GitLab token")

        # 打磨容器仍在跑 → 容器内 commit + push(用评审人 token 注入 remote)
        container = await _get_polish_container(db, req)
        conn = runner_registry.get(container.runner_id) if container else None
        if container is not None and conn is not None:
            from app.core.encryption import decrypt_token

            reviewer_token = decrypt_token(operator.gitlab_token_encrypted)
            message = f"[ai:req] {req.title}"
            await runner_service.send_to_runner(conn, {
                "type": "git_commit",
                "container_id": container.container_id,
                "repo_path": "/workspace/main",
                "add_path": req.prd_file_path,
                "message": message,
                "branch": req.req_branch,
                "token": reviewer_token,
            })
        else:
            # 容器已销毁(异常路径):PRD 无法 commit,仅状态流转并告警(R4 联调补持久化 PRD)
            logger.warning("打磨容器不在跑,跳过 PRD commit req=%s", req.req_id)

        req.status = "approved"
        req.reviewed_by = operator.user_id
        req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info("需求评审通过 req=%s by=%s", req.req_id, operator.user_id)
        # R25 审计:requirement.review_approve
        await audit_write(
            db, operator, "requirement.review_approve",
            project_id=req.project_id, target_type="requirement", target_id=req.req_id,
        )
        # R3 评审通过站内通知(整体兜底:失败不阻塞评审主流程)
        try:
            await _notify_related_users_on_approve(db, req, operator)
        except Exception as e:
            logger.warning("评审通过通知失败(不阻塞评审) req=%s: %s", req.req_id, e)
    else:
        if not reject_reason:
            raise BizError(ErrCode.NOT_IN_POLISHING, "驳回时必须填写理由")
        req.status = "polishing"
        req.reviewed_by = operator.user_id
        req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        req.reject_reason = reject_reason
        logger.info("需求驳回 req=%s by=%s", req.req_id, operator.user_id)
        # R25 审计:requirement.review_reject
        await audit_write(
            db, operator, "requirement.review_reject",
            project_id=req.project_id, target_type="requirement", target_id=req.req_id,
        )
    await db.flush()


async def cancel_requirement(db: AsyncSession, operator: User, req: Requirement, reason: str) -> None:
    """
    取消需求(owner;非 done/archived;分支保留只读,30 天清理归 R14)
    R35.F2:同步收尾——polish_task_id 指向的打磨任务未终态时,先走 finish_task(cancelled)
    停止并销毁容器,消除孤儿容器;收尾失败不阻塞需求取消(warning 留痕)。
    """
    if req.status in ("done", "archived"):
        raise BizError(ErrCode.NOT_IN_POLISHING, "已完成/已归档需求不可取消")

    # R35.F2:打磨任务/容器收尾(孤儿泄漏修复)
    if req.polish_task_id:
        from app.models.task import Task
        from app.services import task_service

        polish_task = (await db.execute(
            select(Task).where(Task.task_id == req.polish_task_id).limit(1)
        )).scalar_one_or_none()
        if polish_task is not None and polish_task.status not in ("done", "cancelled", "failed", "timeout"):
            try:
                await task_service.finish_task(db, polish_task, operator, status="cancelled")
            except Exception as e:  # 收尾失败不阻塞取消(容器泄漏风险降级为告警)
                logger.warning("取消需求:打磨任务收尾失败 task=%s: %s", polish_task.task_id, e)

    req.status = "rejected"
    req.reject_reason = reason
    await db.flush()
    logger.info("需求取消 req=%s by=%s reason=%s", req.req_id, operator.user_id, reason[:50])
    # R25 审计:requirement.cancel(reason 截断,防 detail 膨胀)
    await audit_write(
        db, operator, "requirement.cancel",
        project_id=req.project_id, target_type="requirement", target_id=req.req_id,
        detail={"reason": reason[:100]},
    )


# ---------------------------------------------------------------------------
# 容器辅助(R4 任务表落地前的台账口径)
# ---------------------------------------------------------------------------
async def _get_polish_container(db: AsyncSession, req: Requirement) -> Optional[Container]:
    if not req.polish_task_id:
        return None
    result = await db.execute(
        select(Container).where(Container.task_id == req.polish_task_id).order_by(Container.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()
