"""R12: project_members 项目成员表

Revision ID: c2e8b4d7a910
Revises: a7d21c9e5f40
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c2e8b4d7a910"
down_revision = "a7d21c9e5f40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("user_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="用户 id"),
        sa.Column(
            "role",
            sa.Enum("owner", "editor", "viewer", name="member_role_enum"),
            nullable=False,
            server_default="viewer",
            comment="角色(owner/editor/viewer)",
        ),
        sa.Column("invited_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="邀请人 user_id"),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="加入时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")
