"""项目模型 - Project / ProjectRepo / PlatformSetting(R2 项目管理)"""

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
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Project(Base):
    """项目表(软删:status=deleted + deleted_at,7 天后物理删除)"""
    __tablename__ = "projects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    name = Column(String(64), nullable=False, comment="显示名(同用户下唯一由服务层校验)")
    slug = Column(String(64), unique=True, nullable=False, comment="全局唯一,小写字母数字-,子域/主仓库名")
    description = Column(String(255), default="", server_default="", comment="描述")
    default_branch = Column(String(64), default="master", server_default="master", nullable=False, comment="项目默认分支,所有仓库的需求分支从这里切")
    visibility = Column(Enum("private", "internal", name="project_visibility_enum"),
                        default="private", nullable=False, server_default="private", comment="可见性")
    owner_id = Column(CHAR(36), nullable=False, index=True, comment="创建者 user_id(users.user_id)")
    status = Column(Enum("active", "archived", "deleted", name="project_status_enum"),
                    default="active", nullable=False, server_default="active", index=True, comment="状态")
    mcp_config_encrypted = Column(Text, nullable=True, comment="AES-GCM 加密的项目级 MCP 配置(R17 用)")
    deleted_at = Column(DateTime, nullable=True, comment="软删时间(7 天后物理删除定时任务用)")
    dingtalk_webhook = Column(String(255), nullable=True, comment="项目钉钉群 webhook URL(R18)")
    dingtalk_enabled = Column(Boolean, nullable=False, default=False, server_default="0", comment="启用项目钉钉通知(R18)")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, slug={self.slug}, status={self.status})>"


class ProjectRepo(Base):
    """项目仓库关联表

    约束说明:
    - MySQL 无部分唯一索引,`(project_id, role='main')` 唯一由服务层保证:
      create 项目时恰好写一条 main、add-repo 接口拒绝 main 角色 → 这里只建普通组合索引
    - 同一 repo 不可重复绑定到同一项目:用 (project_id, gitlab_repo_id) 组合唯一约束硬保证
    """
    __tablename__ = "project_repos"
    __table_args__ = (
        UniqueConstraint("project_id", "gitlab_repo_id", name="uq_project_gitlab_repo"),
        Index("ix_project_repos_project_role", "project_id", "role"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="平台内部对外UUID")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id(projects.project_id)")
    role = Column(Enum("main", "test", "docs", "other", name="repo_role_enum"),
                  nullable=False, comment="仓库角色(main 每项目唯一/test/docs/other)")
    gitlab_repo_url = Column(String(255), nullable=False, comment="GitLab 仓库 URL")
    gitlab_repo_id = Column(Integer, nullable=False, comment="GitLab 内部 id")
    gitlab_bind_type = Column(Enum("auto", "manual", name="repo_bind_type_enum"),
                              default="auto", nullable=False, server_default="auto", comment="绑定方式(auto=平台建/manual=用户绑)")
    created_by = Column(CHAR(36), nullable=False, comment="绑定时操作人 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="绑定时间")

    def __repr__(self) -> str:
        return f"<ProjectRepo(id={self.id}, project_id={self.project_id}, role={self.role})>"


class PlatformSetting(Base):
    """平台设置表(单例键值表;敏感项 AES-256-GCM 加密后存 JSON;读取处实时查表,变更即时生效)"""
    __tablename__ = "platform_settings"

    key = Column(String(64), primary_key=True, comment="配置键(白名单枚举,见 R2 分片)")
    value = Column(JSON, nullable=False, comment='配置值;敏感项存 {"__encrypted": <base64>}')
    updated_by = Column(CHAR(36), nullable=False, comment="最近修改人(超管 user_id)")
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PlatformSetting(key={self.key})>"
