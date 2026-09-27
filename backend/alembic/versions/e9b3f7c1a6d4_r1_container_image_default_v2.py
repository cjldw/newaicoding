"""R1:containers.image 列默认 v1 → v2

需求 docs/20260927_devbox默认skills与mcp/DEVPLAN/R1(devbox 镜像预装 rd-flow plugin):
- 仅改列 server_default(platform/devbox:v1 → platform/devbox:v2),不动列类型/可空性/索引。
- 存量行 image 值不改(ALTER ... SET DEFAULT 为元数据操作,不触发行数据)——
  存量 v1 容器跑完销毁,新任务一律 v2(D5 拍板)。
- 模型层 default/server_default 的 v1→v2 翻转属同需求另一批次,本迁移不依赖其先后。
- 完整 SQL 留痕:docs/20260927_devbox默认skills与mcp/DEPLOY.md(与本迁移等效)。

拓扑说明:接在单头 9c7762778c30(R5 系统级采集,merge 点)之后,downgrade 可回退列默认。

Revision ID: e9b3f7c1a6d4
Revises: 9c7762778c30
Create Date: 2026-09-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9b3f7c1a6d4'
down_revision = '9c7762778c30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """列默认 platform/devbox:v1 → platform/devbox:v2(仅元数据,存量行不变)"""
    op.alter_column(
        'containers', 'image',
        existing_type=sa.String(length=255),
        server_default='platform/devbox:v2',
        existing_nullable=False,
    )


def downgrade() -> None:
    """回退列默认至 platform/devbox:v1(同样不动存量行)"""
    op.alter_column(
        'containers', 'image',
        existing_type=sa.String(length=255),
        server_default='platform/devbox:v1',
        existing_nullable=False,
    )
