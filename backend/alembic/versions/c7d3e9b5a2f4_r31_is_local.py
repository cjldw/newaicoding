"""R31 — runners 表新增 is_local 列(本机快速创建标记)

Revision ID: c7d3e9b5a2f4
Revises: b2e8f4a6c9d1
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import TINYINT

revision = 'c7d3e9b5a2f4'
down_revision = 'b2e8f4a6c9d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """runners 表新增 is_local TINYINT(1) NOT NULL DEFAULT 0(存量行=0,即远程 token 型)"""
    op.add_column(
        'runners',
        sa.Column(
            'is_local',
            TINYINT(1),
            nullable=False,
            server_default='0',
            comment='本机快速创建标记(R31)',
        ),
    )


def downgrade() -> None:
    op.drop_column('runners', 'is_local')
