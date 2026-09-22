"""知识库空间模型 - R20(KnowledgeBase / KnowledgeDoc 双表;wiki 形态)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    JSON,
    String,
    TEXT,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class KnowledgeBase(Base):
    """项目级知识库空间(blank 平台编辑 / repo_import 目录导入只读快照)"""
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_kb_project_name"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id")
    name = Column(String(64), nullable=False, comment="显示名(同项目唯一)")
    description = Column(String(255), nullable=True, default="", server_default="", comment="描述")
    source_type = Column(
        Enum("blank", "repo_import", name="kb_source_enum"),
        nullable=False,
        default="blank",
        server_default="blank",
        comment="类型(blank=平台编辑/repo_import=目录导入只读)",
    )
    source_config = Column(JSON, nullable=True, comment='{repo_id, branch, paths: string[]}(repo_import 必填)')
    import_status = Column(
        Enum("idle", "importing", "done", "failed", name="kb_import_status_enum"),
        nullable=False,
        default="idle",
        server_default="idle",
        index=True,
        comment="导入后台任务状态(blank 恒 idle)",
    )
    import_error = Column(String(255), nullable=True, comment="最近失败原因")
    last_synced_at = Column(DateTime, nullable=True, comment="最近导入/同步时间")
    created_by = Column(CHAR(36), nullable=False, index=True, comment="创建者 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<KnowledgeBase(kb_id={self.kb_id}, name={self.name}, source={self.source_type})>"


class KnowledgeDoc(Base):
    """知识库页面(path 同库唯一;repo_import 页面 source_file_path 非空)"""
    __tablename__ = "knowledge_docs"
    __table_args__ = (
        UniqueConstraint("kb_id", "path", name="uq_kb_doc_path"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doc_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    kb_id = Column(CHAR(36), nullable=False, index=True, comment="所属知识库")
    title = Column(String(128), nullable=False, comment="页面标题(导入取文件名)")
    path = Column(String(255), nullable=False, comment="树形路径(同库唯一,如 guide/intro)")
    content = Column(TEXT, nullable=False, default="", server_default="", comment="Markdown 正文")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0", comment="同级排序")
    source_file_path = Column(String(255), nullable=True, comment="导入来源 repo 完整路径(blank 为 NULL)")
    created_by = Column(CHAR(36), nullable=False, comment="创建者 user_id")
    updated_by = Column(CHAR(36), nullable=False, comment="最后更新者 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<KnowledgeDoc(doc_id={self.doc_id}, path={self.path})>"
