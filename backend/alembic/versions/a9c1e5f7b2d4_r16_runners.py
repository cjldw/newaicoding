"""R16: runners 表

Revision ID: a9c1e5f7b2d4
Revises: f6b9d2e4a1c3
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "a9c1e5f7b2d4"
down_revision = "f6b9d2e4a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("runner_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="Runner 名"),
        sa.Column("role", sa.Enum("worker", "deploy", name="runner_role_enum"),
                  nullable=False, server_default="worker", comment="角色"),
        sa.Column("token_hash", sa.String(length=255), nullable=False, comment="Runner token bcrypt hash"),
        sa.Column("status", sa.Enum("online", "offline", "disabled", name="runner_status_enum"),
                  nullable=False, server_default="offline", comment="状态"),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True, comment="最后心跳时间"),
        sa.Column("machine_info", sa.JSON(), nullable=True, comment="{os,arch,cpu_count,mem_total_gb,docker_version}"),
        sa.Column("current_containers", sa.Integer(), nullable=False, server_default="0", comment="当前运行容器数"),
        sa.Column("max_containers", sa.Integer(), nullable=False, server_default="10", comment="最大容器数"),
        sa.Column("public_ip", sa.String(length=64), nullable=True, comment="deploy Runner 公网 IP"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者超管 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runner_id", name="uq_runners_runner_id"),
        sa.UniqueConstraint("name", name="uq_runners_name"),
    )
    op.create_index("ix_runners_role", "runners", ["role"])
    op.create_index("ix_runners_status", "runners", ["status"])


def downgrade() -> None:
    op.drop_index("ix_runners_status", table_name="runners")
    op.drop_index("ix_runners_role", table_name="runners")
    op.drop_table("runners")
