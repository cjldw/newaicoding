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


async def _users_brief_map(db: AsyncSession, user_ids: set[str]) -> dict:
    """R22.F2(BUG-UI-069):批量取创建人摘要(防 N+1),返回 user_id → {user_id,username,nickname}"""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(User.user_id, User.gitlab_username, User.nickname).where(User.user_id.in_(user_ids))
    )).all()
    return {
        uid: {"user_id": uid, "username": glu or "", "nickname": nick}
        for uid, glu, nick in rows
    }


def _brief_or_placeholder(map_: dict, uid: str) -> dict:
    """摘要兜底:查不到的用户(已删)仍返回占位结构,前端渲染不因缺字段崩"""
    return map_.get(uid) or {"user_id": uid, "username": "", "nickname": None}


@router.get("/requirements")
async def list_my_requirements(
    status: str = Query(default=None),
    project_id: str = Query(default=None, description="R22.F2:项目筛选"),
    q: str = Query(default=None, description="R22.F2:标题/编号关键字"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """四维-需求:我创建的需求(status/project_id/q 过滤;分页)"""
    pids = await _visible_project_ids(db, current_user)
    conditions = [Requirement.created_by == current_user.user_id, Requirement.project_id.in_(pids or ["none"])]
    if status:
        conditions.append(Requirement.status == status)
    if project_id:
        conditions.append(Requirement.project_id == project_id)
    if q:
        # 关键字匹配标题或需求编号(MySQL utf8mb4 默认 collation 大小写不敏感)
        conditions.append(
            Requirement.title.like(f"%{q}%") | Requirement.req_id.like(f"%{q}%")
        )

    total = (await db.execute(
        select(func.count(Requirement.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(Requirement).where(*conditions)
        .order_by(Requirement.updated_at.desc(), Requirement.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    name_map = await _projects_name_map(db, pids)
    user_map = await _users_brief_map(db, {r.created_by for r in rows})

    return success(data={
        "items": [
            {
                # BUG-014:前端 DimensionItem 契约为 key(列表渲染 key.slice),补齐字段
                "key": r.req_id,
                "req_id": r.req_id,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                # R22.F2(BUG-UI-059):需求分支 / 创建人列数据源
                "req_branch": r.req_branch,
                "created_by": _brief_or_placeholder(user_map, r.created_by),
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
    project_id: str = Query(default=None, description="R22.F2:项目筛选"),
    q: str = Query(default=None, description="R22.F2:标题/编号关键字"),
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
    if project_id:
        conditions.append(Task.project_id == project_id)
    if q:
        conditions.append(Task.title.like(f"%{q}%") | Task.task_id.like(f"%{q}%"))

    total = (await db.execute(
        select(func.count(Task.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(Task).where(*conditions)
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    name_map = await _projects_name_map(db, pids)
    user_map = await _users_brief_map(db, {t.created_by for t in rows})
    # R22.F2(BUG-UI-060):Runner 名称批量映射(runner_id → name)
    runner_ids = {t.runner_id for t in rows if t.runner_id}
    runner_map: dict[str, str] = {}
    if runner_ids:
        from app.models.runner import Runner

        rr = (await db.execute(
            select(Runner.runner_id, Runner.name).where(Runner.runner_id.in_(runner_ids))
        )).all()
        runner_map = {rid: nm for rid, nm in rr}

    items = []
    for t in rows:
        ext = t.extended_attributes or {}
        item = {
            # BUG-014:前端 DimensionItem 契约为 key(列表渲染 key.slice),补齐字段
            "key": t.task_id,
            "task_id": t.task_id,
            "type": t.type,
            "title": t.title,
            "status": t.status,
            # R22.F2:Runner / 创建人列数据源
            "runner": runner_map.get(t.runner_id or "", t.runner_id or ""),
            "created_by": _brief_or_placeholder(user_map, t.created_by),
            "project": {"project_id": t.project_id, "name": name_map.get(t.project_id, "")},
            "updated_at": t.updated_at,
        }
        # R22.F2(BUG-UI-060):test 维"用例通过"列(pass/total;status ∈ passed/failed 计票)
        if task_type == "test":
            cases = ext.get("test_cases")
            if isinstance(cases, list) and cases:
                passed = sum(1 for c in cases if isinstance(c, dict) and c.get("status") == "passed")
                item["cases_passed"] = f"{passed}/{len(cases)}"
            else:
                item["cases_passed"] = None
        # R22.F2(BUG-UI-060):release 维"部署 URL / 端口"列
        if task_type == "release":
            item["deploy_port"] = ext.get("deploy_port")
            item["deploy_host"] = ext.get("deploy_host")
        items.append(item)

    return success(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
