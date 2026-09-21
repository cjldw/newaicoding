"""终端会话模型 - R9(terminal_sessions 表)"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, String, func
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class TerminalSession(Base):
    """终端会话(每 Tab 一个;pty 实体在 Runner 上,本表为平台侧台账)"""
    __tablename__ = "terminal_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    task_id = Column(CHAR(36), nullable=False, index=True, comment="任务 id")
    container_id = Column(String(64), nullable=False, index=True, comment="容器 id(containers.container_id)")
    runner_id = Column(CHAR(36), nullable=False, index=True, comment="Runner id")
    shell = Column(String(64), nullable=False, default="/bin/bash", server_default="/bin/bash", comment="shell")
    created_by = Column(CHAR(36), nullable=False, comment="创建者 user_id")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="创建时间")
    closed_at = Column(DateTime, nullable=True, comment="关闭时间")

    def __repr__(self) -> str:
        return f"<TerminalSession(session_id={self.session_id}, task_id={self.task_id})>"
