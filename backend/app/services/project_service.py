"""项目服务 - R2 项目管理业务逻辑(创建/列表/详情/更新/软删/归档/仓库绑定解绑)"""

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.project import Project, ProjectRepo
from app.models.user import User
from app.services import gitlab_service
from app.services.gitlab_service import (
    ACCESS_LEVEL_DEVELOPER,
    ACCESS_LEVEL_MAINTAINER,
)
from app.services.platform_settings_service import get_gitlab_bot_config

logger = logging.getLogger(__name__)

# 业务上限(分片约束)
MAX_PROJECTS_PER_USER = 50   # 单用户项目数 ≤ 50
MAX_REPOS_PER_PROJECT = 10   # 单项目绑定 repo 数 ≤ 10


# ---------------------------------------------------------------------------
# 工具:slug 生成与 URL 解析
# ---------------------------------------------------------------------------
def _kebab_case(name: str) -> str:
    """名称转 kebab-case:小写、非字母数字转 -、压缩连续 -、去首尾 -"""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"


async def generate_slug(db: AsyncSession, name: str) -> str:
    """
    生成全局唯一 slug:kebab-case 优先;冲突则追加 -xxxx(4 位 hex)重试。
    (slug 全局唯一含软删记录——UNIQUE 约束作用于全表,复用历史 slug 会撞约束)
    """
    base = _kebab_case(name)

    # 无后缀优先
    result = await db.execute(select(Project.id).where(Project.slug == base).limit(1))
    if result.scalar_one_or_none() is None:
        return base

    # 冲突:追加 4 位随机后缀,最多重试 5 次
    for _ in range(5):
        candidate = f"{base}-{uuid.uuid4().hex[:4]}"
        result = await db.execute(select(Project.id).where(Project.slug == candidate).limit(1))
        if result.scalar_one_or_none() is None:
            return candidate

    # 理论上不可达(16^4 空间);兜底长后缀
    return f"{base}-{uuid.uuid4().hex[:8]}"


def parse_repo_path(url: str) -> Optional[str]:
    """
    从仓库 URL 解析 GitLab path_with_namespace:
    https://gitlab.example.com/group/proj.git → group/proj
    非法(无路径/无 namespace)返回 None。
    """
    if not url or "://" not in url:
        # 容错:允许省略 scheme 的 host/path 形式
        if not url or "/" not in url or "." not in url.split("/", 1)[0]:
            return None
        rest = url.strip().strip("/")
    else:
        rest = url.split("://", 1)[1].strip().strip("/")

    # 去掉 host 部分
    if "/" not in rest:
        return None
    path = rest.split("/", 1)[1]
    # 去 .git 后缀
    if path.endswith(".git"):
        path = path[: -len(".git")]
    # 需要 namespace/repo 至少两段
    if not path or "/" not in path:
        return None
    return path


# ---------------------------------------------------------------------------
# 权限辅助
# ---------------------------------------------------------------------------
def ensure_project_owner(project: Project, user: User) -> None:
    """owner 或平台超管(虚拟 owner,D16)才可操作;否则 403"""
    if project.owner_id == user.user_id:
        return
    if user.role == "superadmin":
        return
    raise BizError(ErrCode.NO_PROJECT_PERMISSION, "无项目操作权限", status_code=403)


async def get_project_or_404(db: AsyncSession, project_id: str) -> Project:
    """按对外 project_id 取项目;不存在(或已软删)返回 404"""
    result = await db.execute(
        select(Project).where(
            Project.project_id == project_id,
            Project.status != "deleted",
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    return project


def _ensure_can_view(project: Project, user: User, role: str) -> None:
    """
    查看权限(R12 接入成员体系后):owner/成员(任意角色)/超管/internal(平台登录用户可见)。
    private 非成员返回 404(隐藏存在性)。
    """
    if role:
        return
    if project.visibility == "internal":
        return
    raise BizError(404, "项目不存在", status_code=404)


# ---------------------------------------------------------------------------
# owner 摘要(owner 对象 users 表无 username 字段,以 gitlab_username 代替,可空)
# ---------------------------------------------------------------------------
async def _owner_brief(db: AsyncSession, owner_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        return {"user_id": owner_id, "username": "", "nickname": None}
    return {
        "user_id": owner.user_id,
        "username": owner.gitlab_username or "",
        "nickname": owner.nickname,
    }


async def _repos_of(db: AsyncSession, project_id: str) -> list[ProjectRepo]:
    result = await db.execute(
        select(ProjectRepo)
        .where(ProjectRepo.project_id == project_id)
        .order_by(ProjectRepo.created_at.asc(), ProjectRepo.id.asc())
    )
    return list(result.scalars().all())


async def build_detail(db: AsyncSession, project: Project) -> dict:
    """项目详情数据(owner + repos)"""
    repos = await _repos_of(db, project.project_id)
    owner = await _owner_brief(db, project.owner_id)
    return {
        "project_id": project.project_id,
        "name": project.name,
        "slug": project.slug,
        "description": project.description or "",
        "status": project.status,
        "visibility": project.visibility,
        "default_branch": project.default_branch,
        "owner": owner,
        "repos": [
            {
                "repo_id": r.repo_id,
                "role": r.role,
                "gitlab_repo_url": r.gitlab_repo_url,
                "gitlab_repo_id": r.gitlab_repo_id,
                "gitlab_bind_type": r.gitlab_bind_type,
            }
            for r in repos
        ],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


# ---------------------------------------------------------------------------
# 把平台用户加为 repo 成员(非关键步骤:失败仅告警,不阻断项目创建)
# ---------------------------------------------------------------------------
async def _grant_repo_member(
    bot_token: str,
    gitlab_url: str,
    gitlab_repo_id: int,
    user: User,
    access_level: int,
) -> None:
    """
    平台 bot 把用户加为 GitLab repo 成员。
    前置:平台用户已绑定 GitLab(gitlab_username);未绑定/查不到 id 则跳过(记 info)。
    已是成员时 GitLab 返回 409,bot_add_member 内部按跳过处理。
    """
    if not user.gitlab_username:
        logger.info("用户 %s 未绑定 GitLab,跳过 repo 成员授权", user.user_id)
        return
    gitlab_uid = await gitlab_service.bot_lookup_user_id_by_username(
        bot_token, gitlab_url, user.gitlab_username
    )
    if gitlab_uid is None:
        logger.info("GitLab 上未找到用户 %s(%s),跳过 repo 成员授权", user.gitlab_username, user.user_id)
        return
    await gitlab_service.bot_add_member(bot_token, gitlab_url, gitlab_repo_id, gitlab_uid, access_level)


# ---------------------------------------------------------------------------
# 创建项目(auto / manual)
# ---------------------------------------------------------------------------
async def create_project(db: AsyncSession, user: User, req) -> dict:
    """
    创建项目并绑定主仓库(role=main,每项目唯一)。
    - auto:平台 bot 在 bot group 下建 {slug} 仓库 + 初始化 README + 创建者加 Maintainer
    - manual:bot 验证 repo 存在且有 read/write/merge 权限 + 创建者加 Maintainer(已是成员跳过)
    """
    logger.info(
        "创建项目入口 user=%s name=%s bind_type=%s", user.user_id, req.name, req.main_repo.bind_type
    )

    # 1. 平台 GitLab 配置检查(未配置 → 2001)
    gitlab_url, bot_token, group_id = await get_gitlab_bot_config(db)

    # 2. 单用户项目数上限(软删不计)
    count_result = await db.execute(
        select(func.count(Project.id)).where(
            Project.owner_id == user.user_id,
            Project.status != "deleted",
        )
    )
    project_count = count_result.scalar() or 0
    if project_count >= MAX_PROJECTS_PER_USER:
        raise BizError(ErrCode.PROJECT_LIMIT_EXCEEDED, "项目数量超限(每人最多 50 个)")

    # 3. 生成全局唯一 slug(冲突自动 -xxxx)
    slug = await generate_slug(db, req.name)

    # 4. 绑定主仓库
    if req.main_repo.bind_type == "auto":
        # auto 建仓必须在平台配置中指定 bot group
        if group_id is None:
            raise BizError(
                ErrCode.BOT_TOKEN_NOT_CONFIGURED,
                "平台 GitLab 未配置(auto 建仓需配置 bot group)",
            )
        logger.info("auto 建仓 slug=%s group=%s branch=%s", slug, group_id, req.default_branch)
        project_json = await gitlab_service.bot_create_repo(
            bot_token, gitlab_url, slug, group_id, req.default_branch, req.visibility
        )
        repo_url = project_json.get("http_url_to_repo") or f"{gitlab_url}/{slug}.git"
        gitlab_repo_id = int(project_json["id"])
        # 初始化 README(非关键步骤,失败仅告警)
        await gitlab_service.bot_init_readme(bot_token, gitlab_url, gitlab_repo_id, req.default_branch)
        bind_type = "auto"
    else:
        # manual:校验 URL 并解析 path → bot 查仓库 → 校验权限
        repo_path = parse_repo_path(req.main_repo.gitlab_repo_url or "")
        if repo_path is None:
            raise BizError(ErrCode.REPO_URL_INVALID, "仓库 URL 无效或无权限")
        logger.info("manual 绑定 path=%s", repo_path)
        project_json = await gitlab_service.bot_get_repo_by_path(bot_token, gitlab_url, repo_path)
        if not gitlab_service.bot_check_repo_permission(project_json):
            raise BizError(ErrCode.REPO_URL_INVALID, "仓库 URL 无效或无权限")
        repo_url = project_json.get("http_url_to_repo") or req.main_repo.gitlab_repo_url
        gitlab_repo_id = int(project_json["id"])
        bind_type = "manual"

    # 5. 创建者加为 main repo Maintainer(非关键步骤:失败仅告警)
    await _grant_repo_member(bot_token, gitlab_url, gitlab_repo_id, user, ACCESS_LEVEL_MAINTAINER)

    # 6. 落库:projects + project_repos(main)
    project = Project(
        name=req.name,
        slug=slug,
        description=req.description or "",
        default_branch=req.default_branch,
        visibility=req.visibility,
        owner_id=user.user_id,
        status="active",
    )
    db.add(project)
    await db.flush()  # 取 project.project_id

    repo = ProjectRepo(
        project_id=project.project_id,
        role="main",
        gitlab_repo_url=repo_url,
        gitlab_repo_id=gitlab_repo_id,
        gitlab_bind_type=bind_type,
        created_by=user.user_id,
    )
    db.add(repo)
    await db.flush()

    logger.info(
        "项目创建完成 project=%s slug=%s main_repo=%s(%s)",
        project.project_id, slug, gitlab_repo_id, bind_type,
    )
    return {
        "project_id": project.project_id,
        "slug": slug,
        "main_repo": {
            "repo_id": repo.repo_id,
            "gitlab_repo_url": repo_url,
            "gitlab_repo_id": gitlab_repo_id,
        },
    }


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------
async def list_projects(db: AsyncSession, user: User, status: str, page: int, page_size: int) -> dict:
    """
    项目列表(分页)。口径:我创建的项目(成员体系 R12 接入后扩展为成员项目)。
    status: active(默认)/archived/all(all 排除软删)。
    """
    conditions = [Project.owner_id == user.user_id]
    if status == "all":
        conditions.append(Project.status != "deleted")
    elif status in ("active", "archived", "deleted"):
        conditions.append(Project.status == status)
    else:
        conditions.append(Project.status == "active")

    total_result = await db.execute(select(func.count(Project.id)).where(*conditions))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Project)
        .where(*conditions)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    projects = result.scalars().all()

    # 批量取 repo 数(避免 N+1)
    pid_list = [p.project_id for p in projects]
    repo_counts: dict[str, int] = {}
    if pid_list:
        cnt_result = await db.execute(
            select(ProjectRepo.project_id, func.count(ProjectRepo.id))
            .where(ProjectRepo.project_id.in_(pid_list))
            .group_by(ProjectRepo.project_id)
        )
        repo_counts = {pid: cnt for pid, cnt in cnt_result.all()}

    items = []
    for p in projects:
        owner = await _owner_brief(db, p.owner_id)
        items.append(
            {
                "project_id": p.project_id,
                "name": p.name,
                "slug": p.slug,
                "description": p.description or "",
                "status": p.status,
                "owner": owner,
                "repo_count": repo_counts.get(p.project_id, 0),
                "created_at": p.created_at,
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# 更新 / 软删 / 归档
# ---------------------------------------------------------------------------
async def update_project(db: AsyncSession, user: User, project_id: str, req) -> dict:
    """更新项目(仅 owner/超管):name/description/default_branch/visibility"""
    project = await get_project_or_404(db, project_id)
    ensure_project_owner(project, user)

    if req.name is not None:
        project.name = req.name
    if req.description is not None:
        project.description = req.description
    if req.default_branch is not None:
        project.default_branch = req.default_branch
    if req.visibility is not None:
        project.visibility = req.visibility

    await db.flush()
    # onupdate=func.now() 的 updated_at 由数据库生成,flush 后属性过期,
    # 必须显式异步 refresh,否则后续属性访问触发同步 IO(MissingGreenlet)
    await db.refresh(project)
    logger.info("项目更新 project=%s by=%s", project_id, user.user_id)
    return await build_detail(db, project)


async def delete_project(db: AsyncSession, user: User, project_id: str) -> None:
    """删除项目:软删(status=deleted + deleted_at),列表隐藏;7 天后物理删除由定时任务处理"""
    from datetime import datetime, timezone

    project = await get_project_or_404(db, project_id)
    ensure_project_owner(project, user)

    project.status = "deleted"
    project.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    logger.info("项目软删 project=%s by=%s", project_id, user.user_id)


async def archive_project(db: AsyncSession, user: User, project_id: str) -> None:
    """归档项目:容器停止/部署下线/只读(容器与部署动作在 R8/R7 接入后联动)"""
    project = await get_project_or_404(db, project_id)
    ensure_project_owner(project, user)

    project.status = "archived"
    await db.flush()
    logger.info("项目归档 project=%s by=%s", project_id, user.user_id)


# ---------------------------------------------------------------------------
# 追加绑定 / 解绑仓库
# ---------------------------------------------------------------------------
async def add_repo(db: AsyncSession, user: User, project_id: str, req) -> dict:
    """
    追加绑定仓库(role=test/docs/other;main 不允许经此接口)。R12 后 owner/editor 均可。
    - 同一 repo 不可重复绑定到同一项目(2004)
    - 单项目绑定 repo 数 ≤ 10(2005)
    - bot 需对该 repo 有权限(2002)
    """
    logger.info("追加绑定仓库入口 project=%s role=%s by=%s", project_id, req.role, user.user_id)

    project = await get_project_or_404(db, project_id)
    # 权限矩阵:owner/editor 可追加绑定(R12 Guard;viewer/非成员拒绝)
    from app.services.project_member_service import require_project_role

    await require_project_role(db, project, user, "editor")

    # 平台 GitLab 配置(未配置 → 2001)
    gitlab_url, bot_token, _group_id = await get_gitlab_bot_config(db)

    # 解析 + bot 权限校验(2002)
    repo_path = parse_repo_path(req.gitlab_repo_url)
    if repo_path is None:
        raise BizError(ErrCode.REPO_URL_INVALID, "仓库 URL 无效或无权限")
    project_json = await gitlab_service.bot_get_repo_by_path(bot_token, gitlab_url, repo_path)
    if not gitlab_service.bot_check_repo_permission(project_json):
        raise BizError(ErrCode.REPO_URL_INVALID, "仓库 URL 无效或无权限")
    gitlab_repo_id = int(project_json["id"])
    repo_url = project_json.get("http_url_to_repo") or req.gitlab_repo_url

    # 同一 repo 不可重复绑定(2004;组合唯一约束兜底)
    dup_result = await db.execute(
        select(ProjectRepo.id).where(
            ProjectRepo.project_id == project_id,
            ProjectRepo.gitlab_repo_id == gitlab_repo_id,
        ).limit(1)
    )
    if dup_result.scalar_one_or_none() is not None:
        raise BizError(ErrCode.REPO_ALREADY_BOUND, "该仓库已绑定到本项目")

    # 单项目绑定数上限(2005)
    cnt_result = await db.execute(
        select(func.count(ProjectRepo.id)).where(ProjectRepo.project_id == project_id)
    )
    repo_count = cnt_result.scalar() or 0
    if repo_count >= MAX_REPOS_PER_PROJECT:
        raise BizError(ErrCode.REPO_LIMIT_EXCEEDED, "绑定仓库数量超限(每项目最多 10 个)")

    # 项目现有成员加为该 repo Developer(R12 前:仅 owner;owner 建仓时已是 Maintainer,跳过)
    owner = await db.execute(select(User).where(User.user_id == project.owner_id))
    owner_user = owner.scalar_one_or_none()
    if owner_user is not None:
        await _grant_repo_member(bot_token, gitlab_url, gitlab_repo_id, owner_user, ACCESS_LEVEL_DEVELOPER)

    row = ProjectRepo(
        project_id=project_id,
        role=req.role,
        gitlab_repo_url=repo_url,
        gitlab_repo_id=gitlab_repo_id,
        gitlab_bind_type="manual",
        created_by=user.user_id,
    )
    db.add(row)
    await db.flush()

    logger.info("仓库绑定完成 repo=%s role=%s project=%s", row.repo_id, req.role, project_id)
    return {
        "repo_id": row.repo_id,
        "role": row.role,
        "gitlab_repo_url": repo_url,
        "gitlab_repo_id": gitlab_repo_id,
    }


async def unbind_repo(db: AsyncSession, user: User, project_id: str, repo_id: str) -> None:
    """
    解绑仓库:仅 role != main 可解绑(2006);解绑后不动 GitLab repo(仅断关联)。
    权限:owner/超管(权限矩阵:editor 不可解绑)。
    """
    project = await get_project_or_404(db, project_id)
    ensure_project_owner(project, user)

    result = await db.execute(
        select(ProjectRepo).where(
            ProjectRepo.repo_id == repo_id,
            ProjectRepo.project_id == project_id,
        )
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise BizError(404, "仓库不存在", status_code=404)

    # main 不可解绑(V1 换绑需删项目重建)
    if repo.role == "main":
        raise BizError(ErrCode.MAIN_REPO_UNBINDABLE, "主仓库不可解绑")

    await db.execute(delete(ProjectRepo).where(ProjectRepo.id == repo.id))
    # 仅断平台关联,不动 GitLab repo
    logger.info("仓库解绑 repo=%s project=%s by=%s(GitLab repo 不受影响)", repo_id, project_id, user.user_id)
