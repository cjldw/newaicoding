"""R1/PRD 平台副本存储 requirements 加 prd_content 列

需求目录:docs/20260929_打磨PRD持久化/DEVPLAN/R1.md
- 新增 prd_content MEDIUMTEXT NULL 列,存放 PRD.md 最新内容副本
- 定位 AFTER prd_file_path(与现有列顺序保持一致)
- 存量行 NULL 不回填(源在容器的才拉得到);代码侧 NULL 容错走 R3「库无副本」分支
- 无索引无唯一约束;写入仅系统内部路径(R2 主链 / R3 兜底),无 API 暴露

完整 SQL 留痕:docs/20260929_打磨PRD持久化/DEPLOY.md

Revision ID: 30088c854a08
Revises: b4f8e2a9c1d7
Create Date: 2026-09-29
"""
from alembic import op

revision = '30088c854a08'
down_revision = 'b4f8e2a9c1d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """requirements 加 prd_content MEDIUMTEXT NULL 列(AFTER prd_file_path)"""
    op.execute(
        "ALTER TABLE `requirements` "
        "ADD COLUMN `prd_content` MEDIUMTEXT NULL "
        "COMMENT 'PRD.md 平台副本(最新值);NULL=尚无副本' "
        "AFTER `prd_file_path`"
    )


def downgrade() -> None:
    """回退:删除 prd_content 列"""
    op.drop_column('requirements', 'prd_content')
