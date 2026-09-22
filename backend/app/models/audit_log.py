"""审计日志与平台邀请模型 - R19(audit_logs / invitations 双表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class AuditLog(Base):
    """审计日志(只读追加,不可删改;保留 1 年,每日定时清理)"""
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    log_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    user_id = Column(CHAR(36), nullable=False, index=True, comment="操作者 user_id")
    operator_role = Column(String(20), nullable=False, comment="操作时平台角色快照(superadmin/user)")
    action_type = Column(String(64), nullable=False, index=True, comment="操作类型(枚举见 R19 分片)")
    project_id = Column(CHAR(36), nullable=True, index=True, comment="关联项目(可空)")
    target_type = Column(String(64), nullable=True, comment="目标类型(user/project/task/…)")
    target_id = Column(String(64), nullable=True, comment="目标 id")
    detail = Column(JSON, nullable=True, comment="变更详情")
    ip = Column(String(45), nullable=True, comment="操作来源 IP")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(log_id={self.log_id}, action={self.action_type})>"


class Invitation(Base):
    """平台注册邀请(超管生成一次性 token;7 天有效;使用/撤销后不可复用)"""
    __tablename__ = "invitations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invitation_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    token_hash = Column(String(255), nullable=False, comment="邀请 token 哈希(明文仅创建响应返回一次)")
    invited_phone = Column(String(11), nullable=True, comment="被邀请人手机号(可空备注)")
    status = Column(
        Enum("pending", "used", "revoked", name="invitation_status_enum"),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="状态",
    )
    expires_at = Column(DateTime, nullable=False, comment="过期时间(7 天)")
    used_by = Column(CHAR(36), nullable=True, comment="使用者 user_id")
    created_by = Column(CHAR(36), nullable=False, comment="邀请人(超管)user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Invitation(invitation_id={self.invitation_id}, status={self.status})>"
