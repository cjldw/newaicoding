"""R5(系统级采集):新建 claude_system_assets 表

需求 docs/20260926_skills市场安装/DEVPLAN/R5(超管采集镜像内置 skills/MCP):
- Runner 临时容器探测(ls /root/.claude/skills/ + cat /root/.claude.json)结果
  覆盖式入库(先清后插);kind ENUM('skill','mcp');detail 存探测原文(JSON)。
- 完整 SQL 留痕:docs/20260926_skills市场安装/DEPLOY.md(与预告一字不差)。

拓扑说明(收口审查#2):本迁移同时是 merge 点——既有悬挂 head d8e4f2a6b9c3
(r32_runner_tags,down 于 c7d3e9b5a2f4)与主线 b8e4d2f6a9c1 在此归并,
`alembic heads` 归单头,生产 `alembic upgrade head` 不再因多 head 报错。

Revision ID: 9c7762778c30
Revises: ('b8e4d2f6a9c1', 'd8e4f2a6b9c3')
Create Date: 2026-09-27
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '9c7762778c30'
# merge 点:同时接住 R32 runner_tags 悬挂分支与 R3 主线(单头收口)
down_revision = ('b8e4d2f6a9c1', 'd8e4f2a6b9c3')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """建 claude_system_assets(覆盖式快照表;kind 建索引便于按类别查询)"""
    op.execute(
        "CREATE TABLE `claude_system_assets` ("
        "`id` BIGINT PRIMARY KEY AUTO_INCREMENT, "
        "`name` VARCHAR(128) NOT NULL COMMENT 'skill目录名/mcp名', "
        "`kind` ENUM('skill','mcp') NOT NULL COMMENT '类别', "
        "`detail` JSON NULL COMMENT '探测原文', "
        "`collected_at` DATETIME NOT NULL COMMENT '采集时间', "
        "`image_tag` VARCHAR(128) NULL COMMENT '镜像标识', "
        "KEY `idx_kind` (`kind`)"
        ") COMMENT='系统级已安装(容器探测)' DEFAULT CHARSET=utf8mb4"
    )


def downgrade() -> None:
    """对称回滚:删表(采集快照可随时重建,无数据保留义务)"""
    op.execute("DROP TABLE `claude_system_assets`")
