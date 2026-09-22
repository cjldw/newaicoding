"""R19: audit_logs / invitations 双表

Revision ID: d6e3f9a1c8b5
Revises: c4b1d7e9f2a6
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "d6e3f9a1c8b5"
down_revision = "c4b1d7e9f2a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("log_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("user_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="操作者 user_id"),
        sa.Column("operator_role", sa.String(length=20), nullable=False, comment="操作时平台角色快照"),
        sa.Column("action_type", sa.String(length=64), nullable=False, comment="操作类型"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="关联项目"),
        sa.Column("target_type", sa.String(length=64), nullable=True, comment="目标类型"),
        sa.Column("target_id", sa.String(length=64), nullable=True, comment="目标 id"),
        sa.Column("detail", sa.JSON(), nullable=True, comment="变更详情"),
        sa.Column("ip", sa.String(length=45), nullable=True, comment="操作来源 IP"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="操作时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_id", name="uq_audit_logs_log_id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action_type", "audit_logs", ["action_type"])
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "invitations",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("invitation_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("token_hash", sa.String(length=255), nullable=False, comment="邀请 token 哈希(明文仅返回一次)"),
        sa.Column("invited_phone", sa.String(length=11), nullable=True, comment="被邀请人手机号(可空)"),
        sa.Column("status", sa.Enum("pending", "used", "revoked", name="invitation_status_enum"),
                  nullable=False, server_default="pending", comment="状态"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间(7 天)"),
        sa.Column("used_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="使用者 user_id"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="邀请人超管 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invitation_id", name="uq_invitations_invitation_id"),
    )
    op.create_index("ix_invitations_status", "invitations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_invitations_status", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_project_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
