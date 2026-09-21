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
from app.models.requirement import Requirement
from app.models.user import User
from app.services import container_service, runner_service
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)


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
    tasks = [
        {
            "task_id": t.task_id,
            "type": t.type,
            "title": t.title,
            "status": t.status,
        }
        for t in result.scalars().all()
    ]

    reviewer = None
    if req.reviewed_by:
        reviewer = await _creator_brief(db, req.reviewed_by)
    return {
        "req_id": req.req_id,
        "title": req.title,
        "background": req.background,
        "description": req.description,
        "acceptance_criteria": req.acceptance_criteria,
        "status": req.status,
        "priority": req.priority,
        "req_branch": req.req_branch,
        "prd_file_path": req.prd_file_path,
        "created_by": await _creator_brief(db, req.created_by),
        "reviewed_by": reviewer,
        "reviewed_at": req.reviewed_at,
        "reject_reason": req.reject_reason,
        "polish_task_id": req.polish_task_id,
        "tasks": tasks,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }


# ---------------------------------------------------------------------------
# 创建(所有绑定 repo 建需求分支)
# ---------------------------------------------------------------------------
async def create_requirement(db: AsyncSession, project: Project, operator: User, req_data: dict) -> dict:
    """
    创建需求:生成 req_id/req_branch → 在所有绑定 repo 上从默认分支切需求分支
    → 写 requirements 表(draft)。分支创建失败即整体失败(GitLab 不可用)。
    """
    from app.services import gitlab_service
    from app.services.platform_settings_service import get_gitlab_bot_config

    logger.info("创建需求 project=%s title=%s by=%s", project.project_id, req_data.get("title"), operator.user_id)

    # 平台 GitLab 配置(建分支用 bot token;未配置 2001)
    gitlab_url, bot_token, _ = await get_gitlab_bot_config(db)

    req_id = str(uuid.uuid4())
    branch = req_data.get("req_branch") or f"req-{req_id[:8]}"

    # 同项目分支名查重(requirements 表口径;GitLab 侧 400 也兜底)
    dup = await db.execute(
        select(Requirement.id).where(
            Requirement.project_id == project.project_id,
            Requirement.req_branch == branch,
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, f"需求分支 {branch} 已存在")

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

    requirement = Requirement(
        req_id=req_id,
        project_id=project.project_id,
        title=req_data["title"],
        background=req_data.get("background"),
        description=req_data["description"],
        acceptance_criteria=req_data.get("acceptance_criteria"),
        req_branch=branch,
        priority=req_data.get("priority", "medium"),
        created_by=operator.user_id,
        status="draft",
    )
    db.add(requirement)
    await db.flush()
    await db.refresh(requirement)

    logger.info("需求创建完成 req=%s branch=%s", requirement.req_id, branch)
    return {"req_id": requirement.req_id, "req_branch": branch}


# ---------------------------------------------------------------------------
# 状态机:开始打磨
# ---------------------------------------------------------------------------
async def start_polish(db: AsyncSession, project: Project, operator: User, req: Requirement) -> str:
    """
    开始打磨(draft → polishing):
    1. 重复校验(3001)
    2. 经 task_service 创建并启动打磨任务(type=requirement;R13 配置校验 + R8 容器)
    3. 生成 prd_file_path(Q26);status=polishing,polish_task_id
    """
    if req.status != "draft":
        raise BizError(ErrCode.POLISH_ALREADY_RUNNING, "已有打磨任务进行中")
    if req.polish_task_id:
        raise BizError(ErrCode.POLISH_ALREADY_RUNNING, "已有打磨任务进行中")

    from app.services import task_service

    task_id = await task_service.create_polish_task(db, project, req, operator)

    req.status = "polishing"
    req.polish_task_id = task_id
    req.prd_file_path = task_service.build_prd_path(req.title, task_id)
    await db.flush()
    logger.info("打磨任务已启动 req=%s task=%s", req.req_id, task_id)
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
    else:
        if not reject_reason:
            raise BizError(ErrCode.NOT_IN_POLISHING, "驳回时必须填写理由")
        req.status = "polishing"
        req.reviewed_by = operator.user_id
        req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        req.reject_reason = reject_reason
        logger.info("需求驳回 req=%s by=%s", req.req_id, operator.user_id)
    await db.flush()


async def cancel_requirement(db: AsyncSession, operator: User, req: Requirement, reason: str) -> None:
    """取消需求(owner;非 done/archived;分支保留只读,30 天清理归 R14)"""
    if req.status in ("done", "archived"):
        raise BizError(ErrCode.NOT_IN_POLISHING, "已完成/已归档需求不可取消")
    req.status = "rejected"
    req.reject_reason = reason
    await db.flush()
    logger.info("需求取消 req=%s by=%s reason=%s", req.req_id, operator.user_id, reason[:50])


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
