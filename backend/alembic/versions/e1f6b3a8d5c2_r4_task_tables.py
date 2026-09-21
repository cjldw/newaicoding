"""R4: tasks / task_uploaded_files / task_messages 三表

Revision ID: e1f6b3a8d5c2
Revises: d9b4f8e2a6c1
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "e1f6b3a8d5c2"
down_revision = "d9b4f8e2a6c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("req_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="需求 id"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("type", sa.Enum("requirement", "dev", "test", "release", name="task_type_enum"),
                  nullable=False, comment="任务类型"),
        sa.Column("title", sa.String(length=128), nullable=False, comment="标题"),
        sa.Column("description", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="描述(AI 输入)"),
        sa.Column("base_branch", sa.String(length=64), nullable=False, comment="基础分支"),
        sa.Column("work_branch", sa.String(length=64), nullable=False, comment="工作分支"),
        sa.Column("status", sa.Enum("pending", "running", "done", "failed", "cancelled", "timeout",
                                    name="task_status_enum"),
                  nullable=False, server_default="pending", comment="状态"),
        sa.Column("container_id", sa.String(length=64), nullable=True, comment="任务运行时 docker id"),
        sa.Column("runner_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="Runner id"),
        sa.Column("conversation_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="Claude 会话 id"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.Column("total_tokens_in", sa.Integer(), nullable=False, server_default="0", comment="输入 token"),
        sa.Column("total_tokens_out", sa.Integer(), nullable=False, server_default="0", comment="输出 token"),
        sa.Column("error_message", mysql.TEXT(charset="utf8mb4"), nullable=True, comment="错误信息"),
        sa.Column("last_commit_sha", sa.String(length=40), nullable=True, comment="最后 commit sha"),
        sa.Column("extended_attributes", sa.JSON(), nullable=True, comment="扩展属性"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_tasks_task_id"),
    )
    op.create_index("ix_tasks_req_id", "tasks", ["req_id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_type", "tasks", ["type"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_container_id", "tasks", ["container_id"])
    op.create_index("ix_tasks_runner_id", "tasks", ["runner_id"])
    op.create_index("ix_tasks_created_by", "tasks", ["created_by"])

    op.create_table(
        "task_uploaded_files",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("file_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="任务 id"),
        sa.Column("filename", sa.String(length=255), nullable=False, comment="原始文件名"),
        sa.Column("stored_filename", sa.String(length=255), nullable=False, comment="容器内实际文件名"),
        sa.Column("size", mysql.BIGINT(unsigned=True), nullable=False, comment="字节"),
        sa.Column("mime_type", sa.String(length=64), nullable=False, server_default="application/octet-stream", comment="MIME"),
        sa.Column("container_path", sa.String(length=255), nullable=False, comment="容器内路径"),
        sa.Column("uploaded_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="上传者 user_id"),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="上传时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_task_uploaded_files_file_id"),
    )
    op.create_index("ix_task_uploaded_files_task_id", "task_uploaded_files", ["task_id"])

    op.create_table(
        "task_messages",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("message_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="任务 id"),
        sa.Column("role", sa.Enum("user", "assistant", "tool", name="task_msg_role_enum"),
                  nullable=False, comment="角色"),
        sa.Column("content", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="内容(Markdown)"),
        sa.Column("file_refs", sa.JSON(), nullable=True, comment="文件引用"),
        sa.Column("tool_calls", sa.JSON(), nullable=True, comment="工具调用"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0", comment="输入 token"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0", comment="输出 token"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_task_messages_message_id"),
    )
    op.create_index("ix_task_messages_task_id", "task_messages", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_messages_task_id", table_name="task_messages")
    op.drop_table("task_messages")
    op.drop_index("ix_task_uploaded_files_task_id", table_name="task_uploaded_files")
    op.drop_table("task_uploaded_files")
    op.drop_index("ix_tasks_created_by", table_name="tasks")
    op.drop_index("ix_tasks_runner_id", table_name="tasks")
    op.drop_index("ix_tasks_container_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_index("ix_tasks_req_id", table_name="tasks")
    op.drop_table("tasks")
