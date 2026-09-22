"""R18: notifications / user_notification_settings 双表 + projects 加钉钉字段

Revision ID: c4b1d7e9f2a6
Revises: b5d9e1f4a7c3
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c4b1d7e9f2a6"
down_revision = "b5d9e1f4a7c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("notification_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("recipient_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="接收人 user_id"),
        sa.Column("type", sa.Enum("deploy_failed", "runner_offline", "task_failed", "push_failed",
                                  "review_approved", "review_rejected", "invited_to_project",
                                  "task_done", "deployed", name="notification_type_enum"),
                  nullable=False, comment="通知类型"),
        sa.Column("level", sa.Enum("critical", "normal", "info", name="notification_level_enum"),
                  nullable=False, server_default="normal", comment="级别"),
        sa.Column("title", sa.String(length=255), nullable=False, comment="标题"),
        sa.Column("content", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="内容(Markdown)"),
        sa.Column("link", sa.String(length=255), nullable=True, comment="跳转链接"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="关联项目 id"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="关联任务 id"),
        sa.Column("read_at", sa.DateTime(), nullable=True, comment="已读时间"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", name="uq_notifications_notification_id"),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_level", "notifications", ["level"])
    op.create_index("ix_notifications_project_id", "notifications", ["project_id"])
    op.create_index("ix_notifications_task_id", "notifications", ["task_id"])
    op.create_index("ix_notifications_read_at", "notifications", ["read_at"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "user_notification_settings",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="用户 id"),
        sa.Column("dingtalk_webhook", sa.String(length=255), nullable=True, comment="钉钉 webhook URL"),
        sa.Column("dingtalk_enabled", mysql.TINYINT(display_width=1), nullable=False, server_default="0", comment="启用钉钉"),
        sa.Column("realtime_toast_enabled", mysql.TINYINT(display_width=1), nullable=False, server_default="1", comment="实时 toast"),
        sa.Column("dingtalk_fail_count", sa.Integer(), nullable=False, server_default="0", comment="连续失败次数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_notification_settings_user"),
    )

    op.add_column(
        "projects",
        sa.Column("dingtalk_webhook", sa.String(length=255), nullable=True, comment="项目钉钉群 webhook"),
    )
    op.add_column(
        "projects",
        sa.Column("dingtalk_enabled", mysql.TINYINT(display_width=1), nullable=False, server_default="0",
                  comment="启用项目钉钉通知"),
    )


def downgrade() -> None:
    op.drop_column("projects", "dingtalk_enabled")
    op.drop_column("projects", "dingtalk_webhook")
    op.drop_table("user_notification_settings")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_task_id", table_name="notifications")
    op.drop_index("ix_notifications_project_id", table_name="notifications")
    op.drop_index("ix_notifications_level", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
