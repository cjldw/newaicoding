"""R10: routes 网关路由表

Revision ID: c8e2a6d9f1b4
Revises: b3d7f9a1c5e2
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c8e2a6d9f1b4"
down_revision = "b3d7f9a1c5e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("route_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("host", sa.String(length=255), nullable=False, comment="匹配 Host(Host 精确匹配)"),
        sa.Column("upstream", sa.String(length=255), nullable=False, comment="上游 http://{runner_host}:{mapped_port}"),
        sa.Column("type", sa.Enum("preview", "deploy", name="route_type_enum"),
                  nullable=False, server_default="preview", comment="路由类型"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="任务 id"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("port", sa.Integer(), nullable=False, comment="容器内端口"),
        sa.Column("status", sa.Enum("active", "inactive", name="route_status_enum"),
                  nullable=False, server_default="inactive", comment="状态"),
        sa.Column("auth_required", mysql.TINYINT(display_width=1), nullable=False, server_default="1", comment="是否需要鉴权"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_id", name="uq_routes_route_id"),
        sa.UniqueConstraint("host", name="uq_routes_host"),
    )
    op.create_index("ix_routes_task_id", "routes", ["task_id"])
    op.create_index("ix_routes_project_id", "routes", ["project_id"])
    op.create_index("ix_routes_type_status", "routes", ["type", "status"])


def downgrade() -> None:
    op.drop_index("ix_routes_type_status", table_name="routes")
    op.drop_index("ix_routes_project_id", table_name="routes")
    op.drop_index("ix_routes_task_id", table_name="routes")
    op.drop_table("routes")
