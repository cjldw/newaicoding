"""四维管理菜单聚合 - R22(需求/开发/测试/发布四维列表;created_by=me 口径)"""

import logging

from fastapi import APIRouter, Depends, Query
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


async def _visible_project_ids(db: AsyncSession, user: User) -> list[str]:
    from sqlalchemy import or_

    from app.models.project_member import ProjectMember

    conditions = [Project.status == "active"]
    if user.role != "superadmin":
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


async def _projects_name_map(db: AsyncSession, pids: list[str]) -> dict:
    rows = (await db.execute(
        select(Project.project_id, Project.name).where(Project.project_id.in_(pids))
    )).all()
    return {pid: name for pid, name in rows}


@router.get("/requirements")
async def list_my_requirements(
    status: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """四维-需求:我创建的需求(status 过滤;分页)"""
    pids = await _visible_project_ids(db, current_user)
    conditions = [Requirement.created_by == current_user.user_id, Requirement.project_id.in_(pids or ["none"])]
    if status:
        conditions.append(Requirement.status == status)

    total = (await db.execute(
        select(func.count(Requirement.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(Requirement).where(*conditions)
        .order_by(Requirement.updated_at.desc(), Requirement.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    name_map = await _projects_name_map(db, pids)

    return success(data={
        "items": [
            {
                # BUG-014:前端 DimensionItem 契约为 key(列表渲染 key.slice),补齐字段
                "key": r.req_id,
                "req_id": r.req_id,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "project": {"project_id": r.project_id, "name": name_map.get(r.project_id, "")},
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/tasks/{task_type}")
async def list_my_tasks(
    task_type: str,
    status: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """四维-任务列表(dev/test/release;created_by=me 口径)"""
    if task_type not in ("dev", "test", "release"):
        from app.core.response import BizError

        raise BizError(404, "未知任务维度", status_code=404)
    pids = await _visible_project_ids(db, current_user)
    conditions = [
        Task.created_by == current_user.user_id,
        Task.type == task_type,
        Task.project_id.in_(pids or ["none"]),
    ]
    if status:
        conditions.append(Task.status == status)

    total = (await db.execute(
        select(func.count(Task.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(Task).where(*conditions)
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    name_map = await _projects_name_map(db, pids)

    return success(data={
        "items": [
            {
                # BUG-014:前端 DimensionItem 契约为 key(列表渲染 key.slice),补齐字段
                "key": t.task_id,
                "task_id": t.task_id,
                "type": t.type,
                "title": t.title,
                "status": t.status,
                "project": {"project_id": t.project_id, "name": name_map.get(t.project_id, "")},
                "updated_at": t.updated_at,
            }
            for t in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })
