"""用户模型 - 对应 users 表"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum as SAEnum,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class User(Base):
    """用户表模型"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部自增ID")
    user_id = Column(CHAR(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), comment="对外UUID")
    phone = Column(String(11), unique=True, nullable=False, comment="手机号(登录名)")
    password_hash = Column(String(255), nullable=False, comment="bcrypt密码哈希")
    nickname = Column(String(32), nullable=True, comment="显示名")
    avatar_url = Column(String(255), nullable=True, comment="头像URL")
    status = Column(SAEnum("active", "disabled", name="user_status"), nullable=False, default="active", server_default="active", comment="状态")
    role = Column(SAEnum("superadmin", "user", name="user_role"), nullable=False, default="user", server_default="user", comment="平台角色")
    token_version = Column(Integer, nullable=False, default=0, server_default="0", comment="会话版本号")
    # 登录锁定相关字段
    login_fail_count = Column(Integer, nullable=False, default=0, server_default="0", comment="连续登录失败次数")
    locked_until = Column(DateTime, nullable=True, comment="锁定截止时间(null表示未锁定)")
    # GitLab 相关字段
    gitlab_username = Column(String(64), nullable=True, comment="GitLab用户名")
    gitlab_token_encrypted = Column(Text, nullable=True, comment="AES-GCM加密的GitLab token")
    gitlab_token_scopes = Column(JSON, nullable=True, comment="GitLab token scope列表")
    gitlab_token_bound_at = Column(DateTime, nullable=True, comment="GitLab token绑定时间")
    # 时间戳
    created_at = Column(DateTime, nullable=False, default=func.now(), server_default=func.now(), comment="创建时间")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, phone={self.phone}, role={self.role})>"
