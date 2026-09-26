"""知识条目模型 - R14(knowledge_entries 表;项目级 + 平台级)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Index,
    JSON,
    String,
    TEXT,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class KnowledgeEntry(Base):
    """知识条目(AI 提取默认 draft;项目级/平台级;FULLTEXT 检索)"""
    __tablename__ = "knowledge_entries"
    __table_args__ = (
        Index("ix_knowledge_project_status", "project_id", "status"),
        # FULLTEXT 在迁移中以 ngram parser 创建(中文分词;见 alembic 迁移)
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entry_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    project_id = Column(CHAR(36), nullable=True, index=True, comment="项目 id(null=平台级)")
    req_id = Column(CHAR(36), nullable=False, index=True, comment="来源需求 id")
    type = Column(
        Enum("code_snippet", "pattern", "pitfall", "doc", name="knowledge_type_enum"),
        nullable=False,
        index=True,
        comment="类型",
    )
    title = Column(String(128), nullable=False, comment="标题")
    content = Column(TEXT, nullable=False, comment="内容(Markdown)")
    tags = Column(JSON, nullable=True, comment="标签数组")
    source_links = Column(JSON, nullable=True, comment="关联 commit/任务/部署 URL")
    created_by = Column(
        Enum("ai", "human", name="knowledge_creator_enum"),
        nullable=False,
        default="ai",
        server_default="ai",
        comment="创建者类型",
    )
    created_by_user_id = Column(
        CHAR(36),
        nullable=True,
        comment="创建者用户 id(R3:创建者本人可编删判定;历史行 NULL 回落角色判定)",
    )
    status = Column(
        Enum("draft", "published", name="knowledge_status_enum"),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
        comment="状态(AI 提取默认 draft,人审后 published)",
    )
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<KnowledgeEntry(entry_id={self.entry_id}, title={self.title}, status={self.status})>"
