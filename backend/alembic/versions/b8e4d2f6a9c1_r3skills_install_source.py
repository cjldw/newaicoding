"""R3(skills 市场安装):skills 表加 source ENUM + source_url 两列

需求 docs/20260926_skills市场安装/DEVPLAN/R3(一键安装到项目):
- source ENUM('platform','project','market') NOT NULL DEFAULT 'platform'(AFTER scope):
  存量行回填口径——scope='project' 的历史行来自上传语义,回填 'project';
  其余(scope='platform')留 server_default 'platform'
- source_url VARCHAR(512) NULL(AFTER source):仅 source=market 时有值,
  记录安装时的实际外呼 URL(审计/溯源口径)
- down 对称:先删 source_url 再删 source

完整 ALTER SQL 留痕:docs/20260926_skills市场安装/DEPLOY.md(R3)

Revision ID: b8e4d2f6a9c1
Revises: f8b2d4a6c1e3
Create Date: 2026-09-27
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b8e4d2f6a9c1'
down_revision = 'f8b2d4a6c1e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """skills 加 source(AFTER scope)/ source_url(AFTER source),存量按 scope 回填"""
    op.execute(
        "ALTER TABLE `skills` "
        "ADD COLUMN `source` "
        "ENUM('platform','project','market') "
        "NOT NULL DEFAULT 'platform' "
        "COMMENT '来源(platform 内置/project 上传/market 市场安装)' "
        "AFTER `scope`"
    )
    op.execute(
        "ALTER TABLE `skills` "
        "ADD COLUMN `source_url` VARCHAR(512) NULL DEFAULT NULL "
        "COMMENT '来源 URL(仅 source=market 时有值:安装时的实际外呼 URL)' "
        "AFTER `source`"
    )
    # 存量回填:scope=project 的历史行均为上传语义(安装接口本需求才引入)
    op.execute("UPDATE `skills` SET `source` = 'project' WHERE `scope` = 'project'")


def downgrade() -> None:
    """对称回滚:删 source_url、source(市场安装溯源信息随列删除)"""
    op.execute("ALTER TABLE `skills` DROP COLUMN `source_url`")
    op.execute("ALTER TABLE `skills` DROP COLUMN `source`")
