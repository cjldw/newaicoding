"""R5.F5(BUG-076):task_messages.content TEXT -> MEDIUMTEXT

根因:TEXT 列 64KB 上限,长 AI 回复被 sql_mode=IGNORE_SPACE 静默截断。
改为 MEDIUMTEXT(16MB 上限),兼容存量行读(存量数据不变)。

完整 SQL 留痕:docs/20260920_ai_web开发平台/DEPLOY.md

Revision ID: a1b2c3d4e5f6
Revises: 30088c854a08
Create Date: 2026-09-29
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = '30088c854a08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """task_messages.content TEXT -> MEDIUMTEXT(存量行不动)"""
    op.execute(
        "ALTER TABLE `task_messages` "
        "MODIFY COLUMN `content` MEDIUMTEXT NOT NULL "
        "COMMENT '内容(Markdown;@filename 前端渲染为链接)'"
    )


def downgrade() -> None:
    """回退:MEDIUMTEXT -> TEXT(注意:若已有 >64KB 数据会截断)"""
    op.execute(
        "ALTER TABLE `task_messages` "
        "MODIFY COLUMN `content` TEXT NOT NULL "
        "COMMENT '内容(Markdown;@filename 前端渲染为链接)'"
    )
