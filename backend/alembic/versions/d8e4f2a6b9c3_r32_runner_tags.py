"""R32 runners tags

Revision ID: d8e4f2a6b9c3
Revises: c7d3e9b5a2f4
Create Date: 2026-09-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e4f2a6b9c3'
down_revision = 'c7d3e9b5a2f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('runners', sa.Column('tags', sa.JSON(), nullable=True, comment='任务类型标签(R32);NULL/空=兜底接所有 worker 任务'))


def downgrade() -> None:
    op.drop_column('runners', 'tags')
