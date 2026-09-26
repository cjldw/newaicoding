"""工作台聚合服务与路由 - R21(无新表;成员项目口径;超管=全部 active 项目)"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
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


def _mine_requirement_condition(uid: str):
    """R7「与我相关」需求口径:我创建 ∪ 我是关联用户。

    related_user_ids 存量行为 NULL:JSON_CONTAINS(NULL, …) 返回 NULL(非命中),
    显式加 IS NOT NULL 守卫双保险;空数组 JSON_CONTAINS 对任意标量返回 0,同样不命中。
    """
    return or_(
        Requirement.created_by == uid,
        and_(
            Requirement.related_user_ids.is_not(None),
            func.json_contains(Requirement.related_user_ids, func.json_quote(uid)),
        ),
    )


@router.get("/summary")
async def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    工作台汇总(R7 口径:「与我相关」= 我创建 ∪ 我是关联用户;范围=可见 active 项目;超管=全部 active 项目):
    四类卡片(需求/dev/test/release)状态分布 + 每类最近 5 条(按 updated_at 倒序)。
    任务维传导:我相关需求下的任务计入(OR 单查询天然去重)。
    """
    user = current_user
    uid = user.user_id
    pids = await _visible_project_ids(db, user)

    def _empty_block():
        return {"total": 0, "by_status": {}, "recent": []}

    result = {"requirements": _empty_block(), "dev_tasks": _empty_block(),
              "test_tasks": _empty_block(), "release_tasks": _empty_block()}

    if not pids:
        return success(data=result)

    # ---------------- 需求(R7:与我相关 = 我创建 ∪ 我是关联用户) ----------------
    mine_req = _mine_requirement_condition(uid)
    req_scope = (mine_req, Requirement.project_id.in_(pids))

    total_req = (await db.execute(
        select(func.count(Requirement.id)).where(*req_scope)
    )).scalar() or 0

    by_status_rows = (await db.execute(
        select(Requirement.status, func.count(Requirement.id))
        .where(*req_scope)
        .group_by(Requirement.status)
    )).all()
    req_block = {
        "total": total_req,
        "by_status": _by_status_zero_filled(REQ_STATUSES, by_status_rows),
        "recent": [],
    }
    reqs = (await db.execute(
        select(Requirement).where(*req_scope)
        .order_by(Requirement.updated_at.desc(), Requirement.id.desc()).limit(5)
    )).scalars().all()
    projects_map = await _projects_name_map(db, pids)
    for r in reqs:
        req_block["recent"].append({
            "req_id": r.req_id,
            "title": r.title,
            "status": r.status,
            "project": {"project_id": r.project_id, "name": projects_map.get(r.project_id, "")},
            "updated_at": r.updated_at,
            # R7:交付时间透传(Date → ISO 字符串;NULL 传 None,前端徽章自行判定)
            "delivery_date": r.delivery_date.isoformat() if r.delivery_date else None,
        })
    result["requirements"] = req_block

    # ---------------- 任务三类(R7:传导口径 = 我创建 ∪ 我相关需求下的任务) ----------------
    # 我相关需求 id 集(含我创建的需求);OR 单查询,同任务命中两分支天然去重
    related_req_ids = list((await db.execute(
        select(Requirement.req_id).where(mine_req, Requirement.project_id.in_(pids))
    )).scalars().all())
    task_scope_base = (or_(Task.created_by == uid, Task.req_id.in_(related_req_ids)),)

    for key, task_type in (("dev_tasks", "dev"), ("test_tasks", "test"), ("release_tasks", "release")):
        task_scope = (*task_scope_base, Task.type == task_type, Task.project_id.in_(pids))
        total = (await db.execute(
            select(func.count(Task.id)).where(*task_scope)
        )).scalar() or 0
        by_status_rows = (await db.execute(
            select(Task.status, func.count(Task.id))
            .where(*task_scope)
            .group_by(Task.status)
        )).all()
        block = {
            "total": total,
            "by_status": _by_status_zero_filled(TASK_STATUSES, by_status_rows),
            "recent": [],
        }
        recent = (await db.execute(
            select(Task).where(*task_scope)
            .order_by(Task.updated_at.desc(), Task.id.desc()).limit(5)
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
