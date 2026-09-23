"""任务模型 - R4(Task / TaskUploadedFile / TaskMessage 三表)"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import CHAR

from app.database import Base


class Task(Base):
    """任务(统一执行单元:requirement 打磨 / dev 开发 / test 测试 / release 发布)"""
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    req_id = Column(CHAR(36), nullable=False, index=True, comment="需求 id")
    project_id = Column(CHAR(36), nullable=False, index=True, comment="项目 id(冗余便于查询)")
    type = Column(
        Enum("requirement", "dev", "test", "release", name="task_type_enum"),
        nullable=False,
        index=True,
        comment="任务类型",
    )
    title = Column(String(128), nullable=False, comment="标题")
    description = Column(Text, nullable=False, comment="本次要做什么(AI 输入)")
    base_branch = Column(String(64), nullable=False, comment="基础分支")
    work_branch = Column(String(64), nullable=False, comment="工作分支(默认=基础分支)")
    status = Column(
        # R6 扩展:cases_review(用例审阅)/ passed(测试通过,含豁免)
        Enum("pending", "running", "cases_review", "passed", "done", "failed", "cancelled", "timeout",
             name="task_status_enum"),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="状态(R6 扩展 cases_review/passed)",
    )
    container_id = Column(String(64), nullable=True, index=True, comment="任务运行时的 docker id")
    runner_id = Column(CHAR(36), nullable=True, index=True, comment="任务运行的 Runner id")
    conversation_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), nullable=False, comment="Claude 会话 id")
    claude_session_id = Column(CHAR(36), nullable=True, comment="任务级 claude CLI 会话 ID,懒生成;对话与终端共用")
    created_by = Column(CHAR(36), nullable=False, index=True, comment="创建者 user_id")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="完成时间")
    total_tokens_in = Column(Integer, nullable=False, default=0, server_default="0", comment="输入 token 数")
    total_tokens_out = Column(Integer, nullable=False, default=0, server_default="0", comment="输出 token 数")
    error_message = Column(Text, nullable=True, comment="错误信息(failed/timeout)")
    last_commit_sha = Column(String(40), nullable=True, comment="最后 commit sha")
    extended_attributes = Column(JSON, nullable=True, comment="扩展属性(test_cases/deploy_port 等)")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Task(task_id={self.task_id}, type={self.type}, status={self.status})>"


class TaskUploadedFile(Base):
    """任务上传文件(存容器 /tmp/uploads/{task_id}/;任务结束随容器丢弃)"""
    __tablename__ = "task_uploaded_files"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    task_id = Column(CHAR(36), nullable=False, index=True, comment="任务 id")
    filename = Column(String(255), nullable=False, comment="原始文件名")
    stored_filename = Column(String(255), nullable=False, comment="容器内实际文件名(冲突自动 -1)")
    size = Column(BigInteger, nullable=False, comment="字节")
    mime_type = Column(String(64), nullable=False, default="application/octet-stream", server_default="application/octet-stream", comment="MIME")
    container_path = Column(String(255), nullable=False, comment="容器内路径")
    uploaded_by = Column(CHAR(36), nullable=False, comment="上传者 user_id")
    uploaded_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="上传时间")

    def __repr__(self) -> str:
        return f"<TaskUploadedFile(file_id={self.file_id}, filename={self.filename})>"


class TaskMessage(Base):
    """任务对话消息(user/assistant/tool;@file 引用与工具调用记录)"""
    __tablename__ = "task_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(CHAR(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, comment="对外UUID")
    task_id = Column(CHAR(36), nullable=False, index=True, comment="任务 id")
    role = Column(Enum("user", "assistant", "tool", name="task_msg_role_enum"), nullable=False, comment="角色")
    content = Column(Text, nullable=False, comment="内容(Markdown;@filename 前端渲染为链接)")
    file_refs = Column(JSON, nullable=True, comment='[{file_id, filename, container_path, injected}]')
    tool_calls = Column(JSON, nullable=True, comment="[{name, args, result, duration_ms}]")
    tokens_in = Column(Integer, nullable=False, default=0, server_default="0", comment="输入 token")
    tokens_out = Column(Integer, nullable=False, default=0, server_default="0", comment="输出 token")
    created_at = Column(DateTime, default=func.now(), server_default=func.now(), nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<TaskMessage(message_id={self.message_id}, role={self.role})>"
