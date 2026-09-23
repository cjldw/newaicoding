"""R28 — users 表新增 avatar_file_path 列

Revision ID: b2e8f4a6c9d1
Revises: a7b2c8d9e1f3
Create Date: 2026-09-23

本地上传头像的文件存储路径(R28):存量行默认 NULL,代码兼容读
(存量 users.avatar_url 可能仍是外部 URL,读侧对 null 容错)。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2e8f4a6c9d1'
down_revision = 'a7b2c8d9e1f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """users 表新增 avatar_file_path VARCHAR(255) NULL DEFAULT NULL"""
    op.add_column(
        'users',
        sa.Column(
            'avatar_file_path',
            sa.String(length=255),
            nullable=True,
            comment='本地上传头像存储路径(R28,如 ./data/avatars/{user_id}/{filename})',
        )
    )


def downgrade() -> None:
    """回滚:删除 avatar_file_path 列"""
    op.drop_column('users', 'avatar_file_path')
