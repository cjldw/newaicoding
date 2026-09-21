"""Skills 模型 - R17(skills / project_skills 两表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Skill(Base):
    """Skill 表(Claude Code Skills 原生格式:YAML frontmatter + Markdown 正文)

    name 唯一性说明:分片字段表为全局 UNIQUE,但交互规则要求"同名 platform 与
    project Skill 项目级覆盖平台级"——全局唯一会阻止覆盖语义。故实现为:
    platform 作用域内唯一 + 项目作用域内唯一(服务层校验),DB 层不设 name 唯一索引。
    """
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_scope_project_name", "scope", "project_id", "name"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    skill_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    name = Column(String(64), nullable=False, comment="Skill 名(kebab-case;唯一性见类注释)")
    description = Column(String(255), nullable=False, comment="一句话描述")
    content = Column(Text, nullable=False, comment="Markdown 正文(YAML frontmatter + 正文)")
    scope = Column(
        Enum("platform", "project", name="skill_scope_enum"),
        nullable=False,
        default="platform",
        server_default="platform",
        index=True,
        comment="作用域",
    )
    project_id = Column(CHAR(36), nullable=True, index=True, comment="scope=project 时必填")
    created_by = Column(CHAR(36), nullable=False, comment="创建者 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name={self.name}, scope={self.scope})>"


class ProjectSkill(Base):
    """项目-Skill 安装关联表(同项目不可重复安装同一 Skill)"""
    __tablename__ = "project_skills"
    __table_args__ = (
        UniqueConstraint("project_id", "skill_id", name="uq_project_skill"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id")
    skill_id = Column(CHAR(36), nullable=False, index=True, comment="Skill id(skills.skill_id)")
    installed_by = Column(CHAR(36), nullable=False, comment="安装人 user_id")
    installed_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="安装时间")

    def __repr__(self) -> str:
        return f"<ProjectSkill(id={self.id}, project_id={self.project_id}, skill_id={self.skill_id})>"
