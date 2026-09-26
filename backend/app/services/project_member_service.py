"""项目成员服务 - R12 邀请/移除/改角色/转让 + 项目级角色 Guard(D16)

Guard 约定:
- 角色层级 viewer(1) < editor(2) < owner(3)
- 超管 = 虚拟 owner(D16):get_project_role 对 superadmin 直接返回 owner,
  不写 project_members 冗余记录
- GitLab 权限映射:owner→Maintainer(40) / editor→Developer(30) / viewer→Reporter(20)
- owner 记录懒回填:R2 建项目时无本表,首次读取/变更时为 project.owner_id 补建
  role='owner' 的成员行(invited_by=自身)
"""

import logging
import time
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.core.security import mask_phone  # R1 打码复用 admin 同函数(users_admin 亦从此导入)
from app.models.project import Project, ProjectRepo
from app.models.project_member import ProjectMember
from app.models.user import User
from app.services import gitlab_service
from app.services.platform_settings_service import get_gitlab_bot_config
from app.services.audit_service import audit_write  # R25 审计接入(事务内,失败不阻塞)

logger = logging.getLogger(__name__)

# 角色层级(数字越大权限越高)
PROJECT_ROLE_LEVELS = {"viewer": 1, "editor": 2, "owner": 3}
# GitLab access_level 映射(40=Maintainer 30=Developer 20=Reporter)
GITLAB_ACCESS_BY_ROLE = {"owner": 40, "editor": 30, "viewer": 20}

MAX_MEMBERS_PER_PROJECT = 50  # 单项目成员数 ≤ 50(含 owner)


# ---------------------------------------------------------------------------
# Guard 核心
# ---------------------------------------------------------------------------
async def _ensure_owner_member_row(db: AsyncSession, project: Project) -> None:
    """为 project.owner_id 懒回填 owner 成员行(幂等)"""
    result = await db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.project_id,
            ProjectMember.user_id == project.owner_id,
        ).limit(1)
    )
    if result.scalar_one_or_none() is None:
        db.add(ProjectMember(
            project_id=project.project_id,
            user_id=project.owner_id,
            role="owner",
            invited_by=project.owner_id,
        ))
        await db.flush()


async def get_project_role(db: AsyncSession, project: Project, user: User) -> str:
    """
    返回用户在项目中的有效角色:''(非成员)/ viewer / editor / owner。
    超管 = 虚拟 owner(D16);projects.owner_id 直接判 owner(不依赖成员行)。
    """
    if user.role == "superadmin":
        return "owner"
    if project.owner_id == user.user_id:
        return "owner"
    result = await db.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.project_id,
            ProjectMember.user_id == user.user_id,
        )
    )
    role = result.scalar_one_or_none()
    return role or ""


async def require_project_role(
    db: AsyncSession,
    project: Project,
    user: User,
    min_level: str,
) -> str:
    """
    项目级 Guard(D16):有效角色层级 >= min_level 才放行,返回有效角色。
    不满足 → 403 code=1901。
    """
    role = await get_project_role(db, project, user)
    if PROJECT_ROLE_LEVELS.get(role, 0) < PROJECT_ROLE_LEVELS[min_level]:
        raise BizError(ErrCode.NO_PROJECT_PERMISSION, "无项目操作权限", status_code=403)
    return role


def require_owner(operator_role: str) -> None:
    """成员管理类操作只认 owner(调用前已通过 require_project_role 拿到有效角色)"""
    if operator_role != "owner":
        raise BizError(ErrCode.NO_PROJECT_PERMISSION, "仅项目所有者可执行此操作", status_code=403)


# ---------------------------------------------------------------------------
# GitLab 同步(非关键步骤:失败仅告警,不阻断平台操作)
# ---------------------------------------------------------------------------
async def _sync_all_repos(
    db: AsyncSession,
    project: Project,
    target: User,
    action: str,
    new_role: str = "viewer",
) -> None:
    """
    把成员变更同步到项目所有绑定 repo(action: add / remove / update)。
    平台 GitLab 未配置或用户未绑 GitLab 时跳过(记 info);单 repo 失败不阻断。
    """
    try:
        gitlab_url, bot_token, _group = await get_gitlab_bot_config(db)
    except Exception:
        logger.info("平台 GitLab 未配置,跳过成员 GitLab 同步 project=%s", project.project_id)
        return

    if not target.gitlab_username:
        logger.info("用户 %s 未绑定 GitLab,跳过成员同步", target.user_id)
        return
    gitlab_uid = await gitlab_service.bot_lookup_user_id_by_username(
        bot_token, gitlab_url, target.gitlab_username
    )
    if gitlab_uid is None:
        logger.info("GitLab 未找到用户 %s,跳过成员同步", target.gitlab_username)
        return

    result = await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == project.project_id)
    )
    repos = result.scalars().all()
    access_level = GITLAB_ACCESS_BY_ROLE[new_role]

    for repo in repos:
        if action == "add":
            await gitlab_service.bot_add_member(bot_token, gitlab_url, repo.gitlab_repo_id, gitlab_uid, access_level)
        elif action == "remove":
            await gitlab_service.bot_remove_member(bot_token, gitlab_url, repo.gitlab_repo_id, gitlab_uid)
        elif action == "update":
            await gitlab_service.bot_update_member_level(bot_token, gitlab_url, repo.gitlab_repo_id, gitlab_uid, access_level)


# ---------------------------------------------------------------------------
# 成员数据组装
# ---------------------------------------------------------------------------
async def _user_brief(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == user_id))
    u = result.scalar_one_or_none()
    if u is None:
        return {"user_id": user_id, "username": "", "nickname": None, "avatar_url": None}
    return {
        "user_id": u.user_id,
        "username": u.gitlab_username or "",
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
    }


async def _member_item(db: AsyncSession, member: ProjectMember) -> dict:
    brief = await _user_brief(db, member.user_id)
    inviter = await _user_brief(db, member.invited_by)
    return {
        "user_id": member.user_id,
        "username": brief["username"],
        "nickname": brief["nickname"],
        "avatar_url": brief["avatar_url"],
        "role": member.role,
        "invited_by": {"user_id": inviter["user_id"], "username": inviter["username"]},
        "joined_at": member.joined_at,
    }


async def _get_member_row(db: AsyncSession, project_id: str, user_id: str) -> Optional[ProjectMember]:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _count_owners(db: AsyncSession, project_id: str) -> int:
    result = await db.execute(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "owner",
        )
    )
    return result.scalar() or 0


# ---------------------------------------------------------------------------
# 成员列表
# ---------------------------------------------------------------------------
async def list_members(db: AsyncSession, project: Project, operator: User) -> list[dict]:
    """成员列表(项目成员/owner/超管可看;先懒回填 owner 行)"""
    await _ensure_owner_member_row(db, project)
    await require_project_role(db, project, operator, "viewer")

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project.project_id)
        .order_by(ProjectMember.joined_at.asc(), ProjectMember.id.asc())
    )
    members = result.scalars().all()
    return [await _member_item(db, m) for m in members]


# ---------------------------------------------------------------------------
# 邀请成员
# ---------------------------------------------------------------------------
async def invite_member(db: AsyncSession, project: Project, operator: User, phone: str, role: str) -> dict:
    """
    owner 按手机号精确搜索邀请已注册用户(editor/viewer)。
    同步:该用户加到所有绑定 repo 为 Developer(editor)/ Reporter(viewer)。
    """
    op_role = await require_project_role(db, project, operator, "viewer")
    require_owner(op_role)

    # 手机号精确查找(R1 已去邮箱,以手机号为唯一登录名)
    normalized = phone.strip()
    result = await db.execute(select(User).where(User.phone == normalized))
    target = result.scalar_one_or_none()
    if target is None:
        # 平台注册邀请是超管职能(R19),V1 不做邀请链接
        raise BizError(ErrCode.INVITE_USER_NOT_FOUND, "该手机号未注册,请联系管理员邀请注册")

    # 已是成员 → 12002(含 owner 行懒回填后再判)
    if await _get_member_row(db, project.project_id, target.user_id) is not None:
        raise BizError(ErrCode.ALREADY_MEMBER, "该用户已是项目成员")

    # 单项目成员数 ≤ 50(owner 行计入)
    cnt = await db.execute(
        select(func.count(ProjectMember.id)).where(ProjectMember.project_id == project.project_id)
    )
    if (cnt.scalar() or 0) >= MAX_MEMBERS_PER_PROJECT:
        raise BizError(ErrCode.MEMBER_LIMIT_EXCEEDED, "项目成员数已达上限(50人)")

    member = ProjectMember(
        project_id=project.project_id,
        user_id=target.user_id,
        role=role,
        invited_by=operator.user_id,
    )
    db.add(member)
    await db.flush()

    logger.info("邀请成员 project=%s user=%s role=%s by=%s", project.project_id, target.user_id, role, operator.user_id)
    # R25 审计:project_member.add(手机号不入 detail,只记目标 user_id 与角色)
    await audit_write(
        db, operator, "project_member.add",
        project_id=project.project_id, target_type="user", target_id=target.user_id,
        detail={"role": role},
    )
    await _sync_all_repos(db, project, target, "add", role)

    brief = await _user_brief(db, target.user_id)
    return {"user_id": target.user_id, "username": brief["username"], "role": role}


# ---------------------------------------------------------------------------
# R2 批量邀请(owner 专属,整体事务:任一校验失败整批拒绝,不留半批)
# ---------------------------------------------------------------------------
async def _precheck_batch_invite(
    db: AsyncSession,
    project: Project,
    user_ids: list[str],
) -> list[dict]:
    """
    批量邀请预检(全量只读,与插入分离;调用方任一 error 即整批 400):
    含重复/不存在/status!=active/已是成员逐条列 reason;
    现成员数+len(user_ids) ≤ 50。
    返回 errors:[{user_id, reason}](空列表 = 全部通过);
    容量超限不逐条列,直接 12003 整批拒绝(与 invite 同码同文案口径)。
    """
    # 按 user_id IN 一次批量查 users(避免逐条查询)
    rows = (await db.execute(
        select(User.user_id, User.status).where(User.user_id.in_(user_ids))
    )).all()
    status_by_id = {uid: status for uid, status in rows}

    # 项目现有成员集合(owner 行懒回填前 owner_id 也算成员,与候选列表 is_member 同口径);
    # 同一份集合兼做容量核算(现成员数 ≤50 行,一次查询两用)
    member_ids = set((await db.execute(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project.project_id)
    )).scalars().all())
    member_ids.add(project.owner_id)

    if len(member_ids) + len(user_ids) > MAX_MEMBERS_PER_PROJECT:
        raise BizError(
            ErrCode.MEMBER_LIMIT_EXCEEDED,
            f"项目成员数已达上限({MAX_MEMBERS_PER_PROJECT}人)",
            status_code=400,
        )

    # 重复计数(契约裁决:含重复整批 400,不再静默去重)
    counts: dict[str, int] = {}
    for uid in user_ids:
        counts[uid] = counts.get(uid, 0) + 1

    errors: list[dict] = []
    reported: set[str] = set()  # 同一 id 只列一条(重复 id 不再叠加其他原因)
    for uid in user_ids:
        if uid in reported:
            continue
        reported.add(uid)
        if counts[uid] > 1:
            errors.append({"user_id": uid, "reason": "重复提交"})
        elif uid not in status_by_id:
            errors.append({"user_id": uid, "reason": "用户不存在"})
        elif status_by_id[uid] != "active":
            errors.append({"user_id": uid, "reason": "用户已停用"})
        elif uid in member_ids:
            errors.append({"user_id": uid, "reason": "该用户已是项目成员"})
    return errors


async def batch_invite_members(
    db: AsyncSession,
    project: Project,
    operator: User,
    user_ids: list[str],
    role: str,
) -> dict:
    """
    owner 批量邀请已注册用户为 editor/viewer(整体事务):
    空/超 50 拒绝 → 全量预检(含重复=整批 400)任一失败整批 400(errors 列 {user_id, reason})
    → 单事务批量 INSERT(invited_by=operator)+ 逐条审计 project_member.add
    → 沿用 invite 的 _sync_all_repos 链路同步 GitLab(失败不回滚成员)。
    并发撞车由 uq_project_member_user 兜底:IntegrityError → 整体回滚 400。
    """
    op_role = await require_project_role(db, project, operator, "viewer")
    require_owner(op_role)

    started = time.monotonic()
    logger.info(
        "批量邀请入口 project=%s n=%s role=%s by=%s",
        project.project_id, len(user_ids), role, operator.user_id,
    )

    # 非空 / 单次 ≤50(原始列表;含重复不做静默去重,由预检整批拒绝,契约裁决 20260927)
    if not user_ids:
        raise BizError(ErrCode.BATCH_INVITE_EMPTY, "user_ids 不能为空", status_code=400)
    if len(user_ids) > MAX_MEMBERS_PER_PROJECT:
        raise BizError(
            ErrCode.BATCH_INVITE_TOO_MANY,
            f"单次最多邀请 {MAX_MEMBERS_PER_PROJECT} 人",
            status_code=400,
        )

    # 全量预检(含重复检查):任一失败整批 400,零插入(异常路径不触碰成员表)
    errors = await _precheck_batch_invite(db, project, user_ids)
    if errors:
        raise BizError(
            ErrCode.BATCH_INVITE_PRECHECK_FAILED,
            "部分用户不可加入,整批未加入",
            status_code=400,
            data={"errors": errors},
        )

    # 单事务批量 INSERT + 逐条审计;并发撞车唯一约束兜底 → 整体回滚 400
    db.add_all([
        ProjectMember(
            project_id=project.project_id,
            user_id=uid,
            role=role,
            invited_by=operator.user_id,
        )
        for uid in user_ids
    ])
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise BizError(
            ErrCode.BATCH_INVITE_CONFLICT, "部分用户刚被加入,请刷新重试", status_code=400,
        )

    # 逐条审计 project_member.add,与单邀请同格式(invited_by=operator)
    for uid in user_ids:
        logger.info("批量邀请成员 project=%s user=%s role=%s by=%s", project.project_id, uid, role, operator.user_id)
        await audit_write(
            db, operator, "project_member.add",
            project_id=project.project_id, target_type="user", target_id=uid,
            detail={"role": role},
        )

    # GitLab 同步沿用 invite 链路(逐用户加所有绑定 repo;失败仅告警不回滚成员)
    target_rows = (await db.execute(
        select(User).where(User.user_id.in_(user_ids))
    )).scalars().all()
    users_by_id = {u.user_id: u for u in target_rows}
    for uid in user_ids:
        target = users_by_id.get(uid)
        if target is not None:
            await _sync_all_repos(db, project, target, "add", role)

    users = [{
        "user_id": uid,
        "nickname": users_by_id[uid].nickname if uid in users_by_id else None,
    } for uid in user_ids]
    logger.info(
        "批量邀请完成 project=%s added=%s 耗时=%.0fms by=%s",
        project.project_id, len(user_ids), (time.monotonic() - started) * 1000, operator.user_id,
    )
    return {"added": len(user_ids), "role": role, "users": users}


# ---------------------------------------------------------------------------
# 移除成员
# ---------------------------------------------------------------------------
async def remove_member(db: AsyncSession, project: Project, operator: User, target_user_id: str) -> None:
    """owner 移除成员;不可移除最后一个 owner;同步从所有绑定 repo 移除"""
    op_role = await require_project_role(db, project, operator, "viewer")
    require_owner(op_role)

    member = await _get_member_row(db, project.project_id, target_user_id)
    if member is None:
        raise BizError(404, "成员不存在", status_code=404)

    # 最后一个 owner 保护(owner 行与 project.owner_id 用户都算)
    if member.role == "owner" and await _count_owners(db, project.project_id) <= 1:
        raise BizError(ErrCode.LAST_OWNER_UNREMOVABLE, "项目必须至少保留一个所有者")

    target = await db.execute(select(User).where(User.user_id == target_user_id))
    target_user = target.scalar_one_or_none()

    await db.execute(delete(ProjectMember).where(ProjectMember.id == member.id))
    logger.info("移除成员 project=%s user=%s by=%s", project.project_id, target_user_id, operator.user_id)
    # R25 审计:project_member.remove
    await audit_write(
        db, operator, "project_member.remove",
        project_id=project.project_id, target_type="user", target_id=target_user_id,
        detail={"role": member.role},
    )

    if target_user is not None:
        await _sync_all_repos(db, project, target_user, "remove")


# ---------------------------------------------------------------------------
# 改角色
# ---------------------------------------------------------------------------
async def change_member_role(
    db: AsyncSession,
    project: Project,
    operator: User,
    target_user_id: str,
    new_role: str,
) -> dict:
    """owner 改成员角色;降级最后一个 owner → 12004;同步 GitLab access_level"""
    op_role = await require_project_role(db, project, operator, "viewer")
    require_owner(op_role)

    member = await _get_member_row(db, project.project_id, target_user_id)
    if member is None:
        raise BizError(404, "成员不存在", status_code=404)

    # 不可把最后一个 owner 降级(owner 转让走 transfer-ownership)
    if member.role == "owner" and new_role != "owner" and await _count_owners(db, project.project_id) <= 1:
        raise BizError(ErrCode.LAST_OWNER_UNREMOVABLE, "项目必须至少保留一个所有者")

    member.role = new_role
    await db.flush()
    logger.info("改角色 project=%s user=%s → %s by=%s", project.project_id, target_user_id, new_role, operator.user_id)
    # R25 审计:project_member.role_change
    await audit_write(
        db, operator, "project_member.role_change",
        project_id=project.project_id, target_type="user", target_id=target_user_id,
        detail={"new_role": new_role},
    )

    target_user = await db.execute(select(User).where(User.user_id == target_user_id))
    target_user_obj = target_user.scalar_one_or_none()
    if target_user_obj is not None:
        await _sync_all_repos(db, project, target_user_obj, "update", new_role)

    return await _member_item(db, member)


# ---------------------------------------------------------------------------
# 转让 owner
# ---------------------------------------------------------------------------
async def transfer_ownership(
    db: AsyncSession,
    project: Project,
    operator: User,
    new_owner_user_id: str,
) -> None:
    """
    owner 转让:project.owner_id → 新 owner;双方成员行角色对调
    (原 owner 降为 editor;新 owner 行角色 → owner)。同步 GitLab 权限对调。
    """
    op_role = await require_project_role(db, project, operator, "viewer")
    require_owner(op_role)

    target_member = await _get_member_row(db, project.project_id, new_owner_user_id)
    if target_member is None:
        raise BizError(ErrCode.TRANSFER_NON_MEMBER, "目标用户不是项目成员")

    if new_owner_user_id != operator.user_id:
        # 平台层 owner 归属切换
        project.owner_id = new_owner_user_id
        target_member.role = "owner"

        # 原 owner 降为 editor(虚拟 owner 超管无成员行则跳过)
        if operator.role != "superadmin":
            op_member = await _get_member_row(db, project.project_id, operator.user_id)
            if op_member is None:
                op_member = ProjectMember(
                    project_id=project.project_id,
                    user_id=operator.user_id,
                    role="editor",
                    invited_by=operator.user_id,
                )
                db.add(op_member)
            else:
                op_member.role = "editor"

    await db.flush()
    logger.info(
        "转让 owner project=%s %s → %s by=%s", project.project_id, operator.user_id, new_owner_user_id, operator.user_id
    )
    # R25 审计:project_member.transfer_ownership
    await audit_write(
        db, operator, "project_member.transfer_ownership",
        project_id=project.project_id, target_type="user", target_id=new_owner_user_id,
    )

    # GitLab 权限对调(非关键步骤)
    new_user = await db.execute(select(User).where(User.user_id == new_owner_user_id))
    new_user_obj = new_user.scalar_one_or_none()
    if new_user_obj is not None:
        await _sync_all_repos(db, project, new_user_obj, "update", "owner")
    if operator.role != "superadmin":
        await _sync_all_repos(db, project, operator, "update", "editor")


# ---------------------------------------------------------------------------
# R1 候选用户列表(owner 专属,成员批量邀请前置)
# ---------------------------------------------------------------------------
async def list_candidate_users(
    db: AsyncSession,
    project: Project,
    operator: User,
    q: Optional[str],
    page: int,
    page_size: int,
) -> dict:
    """
    候选用户列表(owner 专属,超管经 get_project_role 虚拟 owner 旁路)。
    数据源=users 全量平台用户(disabled 照常返回,前端按 status/is_member 禁选);
    q 对 phone/nickname LIKE 模糊;phone 打码复用 admin 同一 mask_phone。
    """
    await require_project_role(db, project, operator, "owner")
    started = time.monotonic()
    logger.info(
        "候选用户列表入口 project=%s q=%r page=%s page_size=%s by=%s",
        project.project_id, q, page, page_size, operator.user_id,
    )

    conditions = []
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append((User.phone.like(like)) | (User.nickname.like(like)))

    total = (await db.execute(
        select(func.count(User.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(User).where(*conditions)
        .order_by(User.created_at.asc(), User.id.asc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    # is_member:一次查项目成员全量 user_id 集合,内存标记(成员 ≤50;owner 行懒回填前也视为成员)
    member_ids = set((await db.execute(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project.project_id)
    )).scalars().all())
    member_ids.add(project.owner_id)

    items = [{
        "user_id": u.user_id,
        "phone": mask_phone(u.phone),
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "status": u.status,
        "is_member": u.user_id in member_ids,
    } for u in rows]

    logger.info(
        "候选用户列表完成 project=%s total=%s 耗时=%.0fms by=%s",
        project.project_id, total, (time.monotonic() - started) * 1000, operator.user_id,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
