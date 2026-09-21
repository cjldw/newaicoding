"""R13: model_configs 模型配置表

Revision ID: d4f9a1e2b6c8
Revises: c2e8b4d7a910
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "d4f9a1e2b6c8"
down_revision = "c2e8b4d7a910"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("config_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="配置名"),
        sa.Column("base_url", sa.String(length=255), nullable=False, comment="OpenAI 兼容 endpoint"),
        sa.Column("api_key_encrypted", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="AES-GCM 加密的 api_key"),
        sa.Column("model", sa.String(length=64), nullable=False, comment="模型名"),
        sa.Column("is_default", mysql.TINYINT(display_width=1), nullable=False, server_default="0", comment="是否默认(同项目最多一个,服务层保证)"),
        sa.Column("enabled", mysql.TINYINT(display_width=1), nullable=False, server_default="1", comment="是否启用"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_id", name="uq_model_configs_config_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_model_config_name"),
    )
    op.create_index("ix_model_configs_project_id", "model_configs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_model_configs_project_id", table_name="model_configs")
    op.drop_table("model_configs")
