"""通知路由 - R18(通知中心/未读计数/个人通知设置/项目钉钉设置)"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.notification import Notification, UserNotificationSettings
from app.models.project import Project
from app.models.user import User
from app.services import notification_service

router = APIRouter(prefix="/api", tags=["通知"])


# ---------------------------------------------------------------------------
# 通知列表 / 未读计数
# ---------------------------------------------------------------------------
@router.get("/notifications")
async def list_notifications(
    type: str = Query(default=None),
    level: str = Query(default=None),
    read: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的通知列表(type/level/read 过滤;含 unread_count)"""
    conditions = [Notification.recipient_id == current_user.user_id]
    if type:
        conditions.append(Notification.type == type)
    if level:
        conditions.append(Notification.level == level)
    if read == "true":
        conditions.append(Notification.read_at.isnot(None))
    elif read == "false":
        conditions.append(Notification.read_at.is_(None))

    total = (await db.execute(
        select(func.count(Notification.id)).where(*conditions)
    )).scalar() or 0
    unread_count = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == current_user.user_id,
            Notification.read_at.is_(None),
        )
    )).scalar() or 0

    rows = (await db.execute(
        select(Notification).where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return success(data={
        "items": [
            {
                "notification_id": n.notification_id,
                "type": n.type,
                "level": n.level,
                "title": n.title,
                "content": n.content,
                "link": n.link,
                "project_id": n.project_id,
                "task_id": n.task_id,
                "read_at": n.read_at,
                "created_at": n.created_at,
            }
            for n in rows
        ],
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "page_size": page_size,
    })


@router.get("/notifications/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """未读计数(导航栏铃铛红点)"""
    count = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == current_user.user_id,
            Notification.read_at.is_(None),
        )
    )).scalar() or 0
    return success(data={"unread_count": count})


# ---------------------------------------------------------------------------
# 已读 / 全部已读 / 删除
# ---------------------------------------------------------------------------
@router.post("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记单条已读(仅本人)"""
    from datetime import datetime, timezone

    notification = (await db.execute(
        select(Notification).where(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.user_id,
        )
    )).scalars().first()
    if notification is None:
        raise BizError(404, "通知不存在", status_code=404)
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
    return success(message="已标记为已读")


@router.post("/notifications/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """全部标记已读"""
    from datetime import datetime, timezone

    from sqlalchemy import update

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        update(Notification)
        .where(
            Notification.recipient_id == current_user.user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    return success(message="全部标记为已读")


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除通知(仅本人)"""
    notification = (await db.execute(
        select(Notification).where(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.user_id,
        )
    )).scalars().first()
    if notification is None:
        raise BizError(404, "通知不存在", status_code=404)
    await db.delete(notification)
    await db.flush()
    return success(message="已删除")


# ---------------------------------------------------------------------------
# 个人通知设置
# ---------------------------------------------------------------------------
async def _get_or_create_settings(db: AsyncSession, user_id: str) -> UserNotificationSettings:
    settings = (await db.execute(
        select(UserNotificationSettings).where(UserNotificationSettings.user_id == user_id)
    )).scalars().first()
    if settings is None:
        settings = UserNotificationSettings(user_id=user_id)
        db.add(settings)
        await db.flush()
    return settings


@router.get("/users/me/notification-settings")
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """个人通知设置"""
    settings = await _get_or_create_settings(db, current_user.user_id)
    return success(data={
        "dingtalk_webhook": settings.dingtalk_webhook,
        "dingtalk_enabled": settings.dingtalk_enabled,
        "realtime_toast_enabled": settings.realtime_toast_enabled,
    })


class UpdateNotificationSettingsRequest(BaseModel):
    dingtalk_webhook: str = Field(default=None, max_length=255)
    dingtalk_enabled: bool = Field(default=None)
    realtime_toast_enabled: bool = Field(default=None)


@router.put("/users/me/notification-settings")
async def update_notification_settings(
    req: UpdateNotificationSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新个人通知设置"""
    settings = await _get_or_create_settings(db, current_user.user_id)
    if req.dingtalk_webhook is not None:
        settings.dingtalk_webhook = req.dingtalk_webhook
    if req.dingtalk_enabled is not None:
        settings.dingtalk_enabled = req.dingtalk_enabled
    if req.realtime_toast_enabled is not None:
        settings.realtime_toast_enabled = req.realtime_toast_enabled
    await db.flush()
    return success(message="保存成功")


class TestDingtalkResult(BaseModel):
    ok: bool
    message: str


@router.post("/users/me/notification-settings/test-dingtalk")
async def test_dingtalk(
    req: UpdateNotificationSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """测试钉钉 webhook(18001=无效)"""
    settings = await _get_or_create_settings(db, current_user.user_id)
    webhook = req.dingtalk_webhook or settings.dingtalk_webhook
    if not webhook:
        raise BizError(18001, "钉钉 Webhook 无效,请检查后重试")
    ok, message = await notification_service.test_dingtalk_webhook(webhook)
    if not ok:
        raise BizError(18001, message)
    return success(message=message)


# ---------------------------------------------------------------------------
# 项目钉钉设置(owner)
# ---------------------------------------------------------------------------
class ProjectDingtalkRequest(BaseModel):
    dingtalk_webhook: str = Field(min_length=1, max_length=255)
    dingtalk_enabled: bool = True


@router.put("/projects/{project_id}/dingtalk-settings")
async def update_project_dingtalk(
    project_id: str,
    req: ProjectDingtalkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 配置项目钉钉群 webhook(critical 告警用)"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    # 仅 owner(超管等同 owner,R19)
    role_ok = project.owner_id == current_user.user_id or current_user.role == "superadmin"
    if not role_ok:
        raise BizError(ErrCode.NO_PROJECT_PERMISSION, "仅项目所有者可配置", status_code=403)
    project.dingtalk_webhook = req.dingtalk_webhook
    project.dingtalk_enabled = req.dingtalk_enabled
    await db.flush()
    return success(message="保存成功")
