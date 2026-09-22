"""审计与邀请服务 - R19(异步审计写入 + 平台邀请生命周期)"""

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, Invitation
from app.models.user import User

logger = logging.getLogger(__name__)

INVITATION_EXPIRES_DAYS = 7
_AUDIT_RETRY_DELAYS = (1, 5, 30)  # 异步写失败重试间隔(秒)


# ---------------------------------------------------------------------------
# 审计写入(异步队列;失败重试 3 次;写失败不阻塞业务)
# ---------------------------------------------------------------------------
def _role_snapshot(user) -> str:
    return getattr(user, "role", "user") or "user"


async def audit_write(
    db: AsyncSession, operator, action_type: str,
    project_id: Optional[str] = None,
    target_type: Optional[str] = None, target_id: Optional[str] = None,
    detail: Optional[dict] = None, ip: Optional[str] = None,
) -> None:
    """同步写入审计(调用方事务内;写失败仅告警不抛出——不阻塞业务操作)"""
    try:
        db.add(AuditLog(
            user_id=operator.user_id,
            operator_role=_role_snapshot(operator),
            action_type=action_type,
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip=ip,
        ))
        await db.flush()
    except Exception as e:
        logger.warning("审计写入失败(不阻塞业务) action=%s: %s", action_type, e)


def spawn_audit_write(session_factory, operator_snapshot: dict, action_type: str,
                      project_id: Optional[str] = None,
                      target_type: Optional[str] = None, target_id: Optional[str] = None,
                      detail: Optional[dict] = None, ip: Optional[str] = None) -> None:
    """
    异步审计写入(独立会话 + 重试 1s/5s/30s;连续失败告警日志)。
    operator_snapshot: {"user_id": str, "role": str}(避免跨会话引用 ORM 对象)
    """
    async def _attempt(session_factory, snapshot, retries) -> bool:
        for i in range(retries):
            try:
                async with session_factory() as session:
                    session.add(AuditLog(
                        user_id=snapshot["user_id"],
                        operator_role=snapshot["role"],
                        action_type=action_type,
                        project_id=project_id,
                        target_type=target_type,
                        target_id=target_id,
                        detail=detail,
                        ip=ip,
                    ))
                    await session.commit()
                return True
            except Exception as e:
                logger.warning("审计异步写入第 %d 次失败: %s", i + 1, e)
                await asyncio.sleep(_AUDIT_RETRY_DELAYS[min(i, len(_AUDIT_RETRY_DELAYS) - 1)])
        return False

    async def _runner():
        snapshot = dict(operator_snapshot)
        ok = await _attempt(session_factory, snapshot, 3)
        if not ok:
            # 连续失败 → critical 告警(接收人=超管;R18 通道;此处先记录)
            logger.critical("审计写入连续失败告警 action=%s operator=%s", action_type, snapshot)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_runner())
    except RuntimeError:
        logger.warning("无运行中事件循环,审计写入跳过 action=%s", action_type)


async def sweep_audit_retention(db: AsyncSession, days: int = 365) -> int:
    """保留期清理:删除 created_at < now()-365d 的审计记录(每日定时任务调用)"""
    from sqlalchemy import delete

    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)
    result = await db.execute(
        AuditLog.__table__.delete().where(AuditLog.created_at < threshold)
    )
    await db.commit()
    count = result.rowcount or 0
    if count:
        logger.info("审计保留期清理:%d 条", count)
    return count


# ---------------------------------------------------------------------------
# 平台邀请生命周期
# ---------------------------------------------------------------------------
def generate_invitation_token() -> tuple[str, str]:
    """生成 (明文 token, hash);明文仅创建响应返回一次"""
    from app.core.security import hash_password

    token = f"qc-invite-{secrets.token_hex(16)}"
    return token, hash_password(token)


async def create_invitation(db: AsyncSession, operator, invited_phone: Optional[str]) -> tuple[Invitation, str]:
    token, token_hash = generate_invitation_token()
    invitation = Invitation(
        token_hash=token_hash,
        invited_phone=invited_phone,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=INVITATION_EXPIRES_DAYS),
        created_by=operator.user_id,
    )
    db.add(invitation)
    await db.flush()
    await db.refresh(invitation)
    logger.info("平台邀请创建 invitation=%s by=%s", invitation.invitation_id, operator.user_id)
    return invitation, token


async def consume_invitation(db: AsyncSession, token: str, user_id: str) -> bool:
    """注册时消费邀请:pending 且未过期 → used(被邀请人绑定)"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    from app.core.security import verify_password

    result = await db.execute(
        select(Invitation).where(Invitation.status == "pending", Invitation.expires_at > now)
    )
    for invitation in result.scalars().all():
        if verify_password(token, invitation.token_hash):
            invitation.status = "used"
            invitation.used_by = user_id
            await db.flush()
            logger.info("邀请已消费 invitation=%s by=%s", invitation.invitation_id, user_id)
            return True
    return False


async def revoke_invitation(db: AsyncSession, invitation_id: str) -> None:
    """撤销 pending 邀请(status=revoked;token 失效)"""
    result = await db.execute(select(Invitation).where(Invitation.invitation_id == invitation_id))
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise ValueError("邀请不存在")
    invitation.status = "revoked"
    await db.flush()
    logger.info("邀请撤销 invitation=%s", invitation_id)
