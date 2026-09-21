"""R3: requirements 需求表

Revision ID: d9b4f8e2a6c1
Revises: c8e2a6d9f1b4
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "d9b4f8e2a6c1"
down_revision = "c8e2a6d9f1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requirements",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("req_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("title", sa.String(length=128), nullable=False, comment="标题"),
        sa.Column("background", mysql.TEXT(charset="utf8mb4"), nullable=True, comment="背景(Markdown)"),
        sa.Column("description", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="描述(Markdown)"),
        sa.Column("acceptance_criteria", mysql.TEXT(charset="utf8mb4"), nullable=True, comment="验收标准(Markdown)"),
        sa.Column("req_branch", sa.String(length=64), nullable=False, comment="需求分支名"),
        sa.Column("prd_file_path", sa.String(length=255), nullable=False, server_default="", comment="PRD repo 内路径(Q26)"),
        sa.Column("status", sa.Enum("draft", "polishing", "reviewing", "approved", "in_progress",
                                    "done", "archived", "rejected", name="req_status_enum"),
                  nullable=False, server_default="draft", comment="状态"),
        sa.Column("priority", sa.Enum("low", "medium", "high", name="req_priority_enum"),
                  nullable=False, server_default="medium", comment="优先级"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column("reviewed_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="评审人 user_id"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True, comment="评审时间"),
        sa.Column("reject_reason", mysql.TEXT(charset="utf8mb4"), nullable=True, comment="驳回理由"),
        sa.Column("polish_task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="当前打磨任务 id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("req_id", name="uq_requirements_req_id"),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])
    op.create_index("ix_requirements_req_branch", "requirements", ["req_branch"])
    op.create_index("ix_requirements_status", "requirements", ["status"])
    op.create_index("ix_requirements_created_by", "requirements", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_requirements_created_by", table_name="requirements")
    op.drop_index("ix_requirements_status", table_name="requirements")
    op.drop_index("ix_requirements_req_branch", table_name="requirements")
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_table("requirements")
