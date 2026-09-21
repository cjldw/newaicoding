"""R8: containers 任务容器表

Revision ID: f6b9d2e4a1c3
Revises: e5a8c3f1d2b7
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "f6b9d2e4a1c3"
down_revision = "e5a8c3f1d2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "containers",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("container_id", sa.String(length=64), nullable=False, comment="Runner 上的 docker id"),
        sa.Column("task_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="任务 id(部署中容器可空)"),
        sa.Column("runner_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="运行该容器的 Runner id"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column(
            "status",
            sa.Enum("creating", "running", "stopped", "failed", "destroyed", name="container_status_enum"),
            nullable=False,
            server_default="creating",
            comment="状态",
        ),
        sa.Column("image", sa.String(length=255), nullable=False, server_default="platform/devbox:v1", comment="镜像"),
        sa.Column("cpu_limit", sa.String(length=16), nullable=False, server_default="2c", comment="CPU 限制"),
        sa.Column("mem_limit", sa.String(length=16), nullable=False, server_default="4g", comment="内存限制"),
        sa.Column("disk_limit", sa.String(length=16), nullable=False, server_default="10g", comment="磁盘限制"),
        sa.Column("exposed_ports", sa.JSON(), nullable=False, comment="容器内端口列表 [5173, 8000]"),
        sa.Column("runner_host_port_5173", mysql.BIGINT(unsigned=True), nullable=True, comment="映射到 5173 的宿主机端口"),
        sa.Column("runner_host_port_8000", mysql.BIGINT(unsigned=True), nullable=True, comment="映射到 8000 的宿主机端口"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("destroyed_at", sa.DateTime(), nullable=True, comment="销毁时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("container_id", name="uq_containers_container_id"),
    )
    op.create_index("ix_containers_task_id", "containers", ["task_id"])
    op.create_index("ix_containers_runner_id", "containers", ["runner_id"])
    op.create_index("ix_containers_project_id", "containers", ["project_id"])
    op.create_index("ix_containers_status", "containers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_containers_status", table_name="containers")
    op.drop_index("ix_containers_project_id", table_name="containers")
    op.drop_index("ix_containers_runner_id", table_name="containers")
    op.drop_index("ix_containers_task_id", table_name="containers")
    op.drop_table("containers")
