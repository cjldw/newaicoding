"""用户管理 / 平台邀请 / 审计日志路由 - R19(超管)"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.services import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["平台管理"])

_LAST_SUPERADMIN = 19001  # 最后一个超管保护(局部常量,避免散落)


# ---------------------------------------------------------------------------
# 用户列表
# ---------------------------------------------------------------------------
@router.get("/users")
async def list_users(
    status: str = Query(default=None),
    q: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """用户列表(超管;手机号打码;响应最小化,不含 token 密文)"""
    from app.core.security import mask_phone

    conditions = []
    if status:
        conditions.append(User.status == status)
    if q:
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

    items = []
    for u in rows:
        items.append({
            "user_id": u.user_id,
            "phone": mask_phone(u.phone),
            "nickname": u.nickname,
            "avatar_url": u.avatar_url,
            "role": u.role,
            "status": u.status,
            "gitlab_bound": u.gitlab_token_encrypted is not None,
            "created_at": u.created_at,
        })
    return success(data={"items": items, "total": total})


# ---------------------------------------------------------------------------
# 禁用 / 启用
# ---------------------------------------------------------------------------
class UpdateUserStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


async def _count_active_superadmins(db: AsyncSession, exclude_user_id: Optional[str] = None) -> int:
    conditions = [User.role == "superadmin", User.status == "active"]
    if exclude_user_id:
        conditions.append(User.user_id != exclude_user_id)
    return (await db.execute(
        select(func.count(User.id)).where(*conditions)
    )).scalar() or 0


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    req: UpdateUserStatusRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    禁用/启用用户(R19/D17):
    - 禁用:status=disabled + token_version+=1(在途 JWT 立即 401)+ running 任务取消(销毁前强制 push)
    - 最后一个 active 超管不可禁用(19001)
    """
    target = (await db.execute(select(User).where(User.user_id == user_id))).scalars().first()
    if target is None:
        raise BizError(404, "用户不存在", status_code=404)

    cancelled_tasks = 0
    if req.status == "disabled":
        # 最后一个超管保护:目标是 active 超管且无其他 active 超管 → 19001
        if target.role == "superadmin" and target.status == "active":
            other = await _count_active_superadmins(db, exclude_user_id=user_id)
            if other == 0:
                raise BizError(_LAST_SUPERADMIN, "最后一个超级管理员不可禁用")
        target.status = "disabled"
        target.token_version = (target.token_version or 0) + 1  # D17 立即失效

        # 取消其 running 任务(销毁前强制 push 由 Runner 兜底)
        from app.models.container import Container

        tasks = (await db.execute(
            select(Task).where(
                Task.created_by == user_id, Task.status == "running"
            )
        )).scalars().all()
        for t in tasks:
            t.status = "cancelled"
            t.finished_at = datetime.now()
            # 容器销毁指令由 Runner 兜底(R8 request_stop;销毁前强制 push)
            cancelled_tasks += 1
            logger.info("禁用用户取消任务 task=%s user=%s", t.task_id, user_id)
    else:
        target.status = "active"

    await db.flush()

    # 审计(异步独立会话写入;factory 未注入[测试 ASGI]时跳过)
    factory = _session_factory_holder.get("factory")
    if factory is not None:
        audit_service.spawn_audit_write(
            factory,
            {"user_id": current_user.user_id, "role": current_user.role},
            action_type="user.disable" if req.status == "disabled" else "user.enable",
            target_type="user", target_id=user_id,
            detail={"status": req.status},
        )

    return success(data={"user_id": user_id, "status": target.status, "cancelled_tasks": cancelled_tasks})


_session_factory_holder: dict = {}


def set_audit_session_factory(factory) -> None:
    _session_factory_holder["factory"] = factory


# ---------------------------------------------------------------------------
# 平台注册邀请
# ---------------------------------------------------------------------------
class CreateInvitationRequest(BaseModel):
    invited_phone: str = Field(default=None, max_length=11)


@router.post("/invitations")
async def create_invitation(
    req: CreateInvitationRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """生成平台注册邀请(一次性 token,仅此响应返回明文;7 天有效)"""
    invitation, token = await audit_service.create_invitation(
        db, current_user, invited_phone=req.invited_phone,
    )
    from datetime import timedelta

    return success(data={
        "invitation_id": invitation.invitation_id,
        "invitation_token": token,
        "expires_at": invitation.expires_at + timedelta(days=0),
    }, message="邀请已生成,token 仅显示一次,请立即复制")


@router.get("/invitations")
async def list_invitations(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """邀请记录列表(手机号打码)"""
    from app.models.audit_log import Invitation

    rows = (await db.execute(
        select(Invitation).order_by(Invitation.created_at.desc())
    )).scalars().all()

    from app.core.security import mask_phone

    items = []
    for inv in rows:
        items.append({
            "invitation_id": inv.invitation_id,
            "invited_phone": mask_phone(inv.invited_phone) if inv.invited_phone else None,
            "status": inv.status,
            "created_by": inv.created_by,
            "created_at": inv.created_at,
            "expires_at": inv.expires_at,
        })
    return success(data={"items": items, "total": len(items)})


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """撤销 pending 邀请(token 失效)"""
    try:
        await audit_service.revoke_invitation(db, invitation_id)
    except ValueError:
        raise BizError(404, "邀请不存在或已撤销", status_code=404)
    return success(message="邀请已撤销")


# ---------------------------------------------------------------------------
# 审计日志查询(只读)
# ---------------------------------------------------------------------------
@router.get("/audit-logs")
async def list_audit_logs(
    start_time: datetime = Query(default=None),
    end_time: datetime = Query(default=None),
    user_id: str = Query(default=None),
    action_type: str = Query(default=None),
    project_id: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """审计日志查询(时间/用户/类型/项目过滤;created_at 倒序;只读)"""
    from app.models.audit_log import AuditLog

    conditions = []
    if start_time:
        conditions.append(AuditLog.created_at >= start_time)
    if end_time:
        conditions.append(AuditLog.created_at <= end_time)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if action_type:
        conditions.append(AuditLog.action_type == action_type)
    if project_id:
        conditions.append(AuditLog.project_id == project_id)

    total = (await db.execute(
        select(func.count(AuditLog.id)).where(*conditions)
    )).scalar() or 0
    rows = (await db.execute(
        select(AuditLog).where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    users_map = {}
    if rows:
        uids = list({r.user_id for r in rows})
        urows = (await db.execute(
            select(User).where(User.user_id.in_(uids))
        )).scalars().all()
        users_map = {u.user_id: u.nickname for u in urows}

    items = []
    for r in rows:
        items.append({
            "log_id": r.log_id,
            "user_id": r.user_id,
            "operator_nickname": users_map.get(r.user_id),
            "operator_role": r.operator_role,
            "action_type": r.action_type,
            "project_id": r.project_id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "detail": r.detail,
            "ip": r.ip,
            "created_at": r.created_at,
        })
    return success(data={"items": items, "total": total})
