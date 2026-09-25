"""R32(R3 条目编辑与删除)— knowledge_entries 新增 created_by_user_id

knowledge_entries 加 created_by_user_id CHAR(36) NULL(AFTER created_by):
- 新建条目由 create_entry 写入 operator.user_id,用于「创建者本人可编删」判定
- 存量行该列为 NULL → 创建者判定不命中,回落 owner/editor/超管 角色判定(回落安全)

Revision ID: e8f4a2c6b9d1
Revises: c7d3e9b5a2f4
Create Date: 2026-09-25
"""
from alembic import op

revision = 'e8f4a2c6b9d1'
down_revision = 'c7d3e9b5a2f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """knowledge_entries 加 created_by_user_id CHAR(36) NULL(AFTER created_by)"""
    op.execute(
        "ALTER TABLE `knowledge_entries` "
        "ADD COLUMN `created_by_user_id` CHAR(36) NULL "
        "COMMENT '创建者用户 id(R3:创建者本人可编删判定;历史行 NULL 回落角色判定)' "
        "AFTER `created_by`"
    )


def downgrade() -> None:
    op.drop_column('knowledge_entries', 'created_by_user_id')
