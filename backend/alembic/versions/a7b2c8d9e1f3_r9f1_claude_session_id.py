"""R9.F1 — tasks 表新增 claude_session_id 列

Revision ID: a7b2c8d9e1f3
Revises: d6e3f9a1c8b5
Create Date: 2026-09-23

任务级 claude CLI 会话 ID,懒生成;对话与终端共用同一会话。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import CHAR


# revision identifiers, used by Alembic.
revision = 'a7b2c8d9e1f3'
down_revision = 'd6e3f9a1c8b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """tasks 表新增 claude_session_id CHAR(36) NULL"""
    op.add_column(
        'tasks',
        sa.Column(
            'claude_session_id',
            CHAR(36),
            nullable=True,
            comment='任务级 claude CLI 会话 ID,懒生成;对话与终端共用'
        )
    )


def downgrade() -> None:
    """回滚:删除 claude_session_id 列"""
    op.drop_column('tasks', 'claude_session_id')
