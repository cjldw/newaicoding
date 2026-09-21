"""add_login_lockout_fields

Revision ID: b7e2a1c3d4f5
Revises: 2c13321fa03e
Create Date: 2026-09-21 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2a1c3d4f5'
down_revision: Union[str, Sequence[str], None] = '2c13321fa03e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add login_fail_count and locked_until columns for login lockout."""
    op.add_column('users', sa.Column(
        'login_fail_count', sa.Integer(),
        server_default='0', nullable=False,
        comment='连续登录失败次数',
    ))
    op.add_column('users', sa.Column(
        'locked_until', sa.DateTime(),
        nullable=True,
        comment='锁定截止时间(null表示未锁定)',
    ))


def downgrade() -> None:
    """Remove login lockout columns."""
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'login_fail_count')
