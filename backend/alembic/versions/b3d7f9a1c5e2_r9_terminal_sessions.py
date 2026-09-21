"""R9: terminal_sessions 终端会话表

Revision ID: b3d7f9a1c5e2
Revises: a9c1e5f7b2d4
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "b3d7f9a1c5e2"
down_revision = "a9c1e5f7b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terminal_sessions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("session_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="任务 id"),
        sa.Column("container_id", sa.String(length=64), nullable=False, comment="容器 id"),
        sa.Column("runner_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="Runner id"),
        sa.Column("shell", sa.String(length=64), nullable=False, server_default="/bin/bash", comment="shell"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("closed_at", sa.DateTime(), nullable=True, comment="关闭时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_terminal_sessions_session_id"),
    )
    op.create_index("ix_terminal_sessions_task_id", "terminal_sessions", ["task_id"])
    op.create_index("ix_terminal_sessions_container_id", "terminal_sessions", ["container_id"])
    op.create_index("ix_terminal_sessions_runner_id", "terminal_sessions", ["runner_id"])


def downgrade() -> None:
    op.drop_index("ix_terminal_sessions_runner_id", table_name="terminal_sessions")
    op.drop_index("ix_terminal_sessions_container_id", table_name="terminal_sessions")
    op.drop_index("ix_terminal_sessions_task_id", table_name="terminal_sessions")
    op.drop_table("terminal_sessions")
