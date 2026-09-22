"""工作台聚合服务与路由 - R21(无新表;成员项目口径;超管=全部 active 项目)"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import success
from app.database import get_db
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["工作台"])

# 状态全集(0 也返回,前端渲染稳定)
REQ_STATUSES = ("draft", "polishing", "reviewing", "approved", "in_progress", "done", "archived", "rejected")
TASK_STATUSES = ("pending", "running", "cases_review", "passed", "failed", "done", "cancelled", "timeout")


async def _visible_project_ids(db: AsyncSession, user: User) -> list[str]:
    """可见项目集合:超管=全部 active;普通用户=成员/owner 的 active 项目(R12 口径)"""
    from sqlalchemy import or_

    conditions = [Project.status == "active"]
    if user.role != "superadmin":
        from app.models.project_member import ProjectMember

        conditions.append(
            or_(
                Project.owner_id == user.user_id,
                Project.project_id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == user.user_id)
                ),
            )
        )
    rows = (await db.execute(select(Project.project_id).where(*conditions))).scalars().all()
    return list(rows)


def _by_status_zero_filled(statuses, counter_rows) -> dict:
    base = {s: 0 for s in statuses}
    for status, cnt in counter_rows:
        if status in base:
            base[status] = cnt
    return base


@router.get("/summary")
async def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    工作台汇总(口径:created_by=我;范围=可见 active 项目;超管=全部 active 项目):
    四类卡片(需求/dev/test/release)状态分布 + 每类最近 5 条(按 updated_at 倒序)。
    """
    user = current_user
    pids = await _visible_project_ids(db, user)

    def _empty_block():
        return {"total": 0, "by_status": {}, "recent": []}

    result = {"requirements": _empty_block(), "dev_tasks": _empty_block(),
              "test_tasks": _empty_block(), "release_tasks": _empty_block()}

    if not pids:
        return success(data=result)

    # ---------------- 需求 ----------------
    total_req = (await db.execute(
        select(func.count(Requirement.id)).where(
            Requirement.created_by == user.user_id,
            Requirement.project_id.in_(pids),
        )
    )).scalar() or 0

    by_status_rows = (await db.execute(
        select(Requirement.status, func.count(Requirement.id))
        .where(Requirement.created_by == user.user_id, Requirement.project_id.in_(pids))
        .group_by(Requirement.status)
    )).all()
    req_block = {
        "total": total_req,
        "by_status": _by_status_zero_filled(REQ_STATUSES, by_status_rows),
        "recent": [],
    }
    reqs = (await db.execute(
        select(Requirement).where(
            Requirement.created_by == user.user_id, Requirement.project_id.in_(pids)
        ).order_by(Requirement.updated_at.desc(), Requirement.id.desc()).limit(5)
    )).scalars().all()
    projects_map = await _projects_name_map(db, pids)
    for r in reqs:
        req_block["recent"].append({
            "req_id": r.req_id,
            "title": r.title,
            "status": r.status,
            "project": {"project_id": r.project_id, "name": projects_map.get(r.project_id, "")},
            "updated_at": r.updated_at,
        })
    result["requirements"] = req_block

    # ---------------- 任务三类 ----------------
    for key, task_type in (("dev_tasks", "dev"), ("test_tasks", "test"), ("release_tasks", "release")):
        total = (await db.execute(
            select(func.count(Task.id)).where(
                Task.created_by == user.user_id,
                Task.type == task_type,
                Task.project_id.in_(pids),
            )
        )).scalar() or 0
        by_status_rows = (await db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.created_by == user.user_id, Task.type == task_type, Task.project_id.in_(pids))
            .group_by(Task.status)
        )).all()
        block = {
            "total": total,
            "by_status": _by_status_zero_filled(TASK_STATUSES, by_status_rows),
            "recent": [],
        }
        recent = (await db.execute(
            select(Task).where(
                Task.created_by == user.user_id, Task.type == task_type, Task.project_id.in_(pids)
            ).order_by(Task.updated_at.desc(), Task.id.desc()).limit(5)
        )).scalars().all()
        for t in recent:
            block["recent"].append({
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status,
                "project": {"project_id": t.project_id, "name": projects_map.get(t.project_id, "")},
                "updated_at": t.updated_at,
            })
        result[key] = block

    logger.info("工作台汇总 user=%s", user.user_id)
    return success(data=result)


async def _projects_name_map(db: AsyncSession, pids: list[str]) -> dict:
    rows = (await db.execute(
        select(Project.project_id, Project.name).where(Project.project_id.in_(pids))
    )).all()
    return {pid: name for pid, name in rows}


def include_router(app):
    app.include_router(router)
