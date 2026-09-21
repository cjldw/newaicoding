"""需求模型 - R3(需求管理与打磨;requirements 表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Requirement(Base):
    """需求(状态机:draft → polishing → reviewing → approved → in_progress → done → archived;rejected 可自多个状态)"""
    __tablename__ = "requirements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    req_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id")
    title = Column(String(128), nullable=False, comment="标题")
    background = Column(Text, nullable=True, comment="背景(Markdown)")
    description = Column(Text, nullable=False, comment="描述(Markdown)")
    acceptance_criteria = Column(Text, nullable=True, comment="验收标准(Markdown 勾选清单)")
    req_branch = Column(String(64), nullable=False, index=True, comment="需求分支名(默认 req-{reqId},同 repo 唯一)")
    prd_file_path = Column(String(255), nullable=False, default="", server_default="", comment="PRD repo 内路径(打磨任务创建时按 Q26 生成并固定)")
    status = Column(
        Enum("draft", "polishing", "reviewing", "approved", "in_progress", "done", "archived", "rejected", name="req_status_enum"),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
        comment="状态",
    )
    priority = Column(
        Enum("low", "medium", "high", name="req_priority_enum"),
        nullable=False,
        default="medium",
        server_default="medium",
        comment="优先级(V1 仅展示)",
    )
    created_by = Column(CHAR(36), nullable=False, index=True, comment="创建者 user_id")
    reviewed_by = Column(CHAR(36), nullable=True, comment="评审人 user_id")
    reviewed_at = Column(DateTime, nullable=True, comment="评审时间")
    reject_reason = Column(Text, nullable=True, comment="驳回理由(驳回时必填)")
    polish_task_id = Column(CHAR(36), nullable=True, comment="当前打磨任务 id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Requirement(req_id={self.req_id}, title={self.title}, status={self.status})>"
