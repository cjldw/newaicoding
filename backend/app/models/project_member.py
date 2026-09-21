"""项目成员模型 - R12 项目成员与协作(project_members 表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class ProjectMember(Base):
    """项目成员表(同一用户在同一项目只有一条记录;owner 记录与 projects.owner_id 冗余一致,
    由服务层在读取/变更时懒回填保证——R2 建项目时尚无本表,owner 行按需补建)"""
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id(projects.project_id)")
    user_id = Column(CHAR(36), nullable=False, index=True, comment="用户 id(users.user_id)")
    role = Column(
        Enum("owner", "editor", "viewer", name="member_role_enum"),
        nullable=False,
        server_default="viewer",
        comment="角色(owner/editor/viewer)",
    )
    invited_by = Column(String(36), nullable=False, comment="邀请人 user_id(owner 初始回填行为自身)")
    joined_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="加入时间")

    def __repr__(self) -> str:
        return f"<ProjectMember(id={self.id}, project_id={self.project_id}, user_id={self.user_id}, role={self.role})>"
