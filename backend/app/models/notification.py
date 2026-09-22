"""通知模型 - R18(notifications / user_notification_settings 双表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Notification(Base):
    """站内通知(分类 Tab/未读计数/跳转链接)"""
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    recipient_id = Column(CHAR(36), nullable=False, index=True, comment="接收人 user_id")
    type = Column(
        Enum("deploy_failed", "runner_offline", "task_failed", "push_failed",
             "review_approved", "review_rejected", "invited_to_project",
             "task_done", "deployed", name="notification_type_enum"),
        nullable=False,
        index=True,
        comment="通知类型",
    )
    level = Column(
        Enum("critical", "normal", "info", name="notification_level_enum"),
        nullable=False,
        default="normal",
        server_default="normal",
        index=True,
        comment="级别(critical 走钉钉+toast;info 仅站内信)",
    )
    title = Column(String(255), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="内容(Markdown)")
    link = Column(String(255), nullable=True, comment="跳转链接")
    project_id = Column(CHAR(36), nullable=True, index=True, comment="关联项目 id")
    task_id = Column(CHAR(36), nullable=True, index=True, comment="关联任务 id")
    read_at = Column(DateTime, nullable=True, index=True, comment="已读时间(null=未读)")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Notification(notification_id={self.notification_id}, type={self.type}, level={self.level})>"


class UserNotificationSettings(Base):
    """用户通知设置(钉钉 webhook/实时 toast;一对一)"""
    __tablename__ = "user_notification_settings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(CHAR(36), unique=True, nullable=False, comment="用户 id")
    dingtalk_webhook = Column(String(255), nullable=True, comment="钉钉 webhook URL")
    dingtalk_enabled = Column(Boolean, nullable=False, default=False, server_default="0", comment="启用钉钉")
    realtime_toast_enabled = Column(Boolean, nullable=False, default=True, server_default="1", comment="实时 toast")
    dingtalk_fail_count = Column(Integer, nullable=False, default=0, server_default="0", comment="连续失败次数(≥3 标记失效)")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<UserNotificationSettings(user_id={self.user_id}, dingtalk_enabled={self.dingtalk_enabled})>"
