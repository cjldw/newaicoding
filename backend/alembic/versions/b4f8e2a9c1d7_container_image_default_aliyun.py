"""container_image:containers.image 列默认 v2 → aliyun registry 地址

需求 docs/20260927_devbox默认skills与mcp/DEVPLAN/R5(容器镜像后台可配置):
- 仅改列 server_default(platform/devbox:v2 →
  registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2),不动列类型/可空性/索引。
- 应用层恒显式传值(schedule_and_start 镜像解析链:显式传参 > 设置项 container_image >
  DEFAULT_IMAGE 常量),列默认仅为兜底;模型层 default/server_default 同批翻转。
- 存量行 image 值不改(ALTER ... SET DEFAULT 为元数据操作,不触发行数据);
  镜像在容器创建时刻定格,设置改动不影响存量/运行中容器。
- 完整 SQL 留痕:docs/20260927_devbox默认skills与mcp/DEPLOY.md(与本迁移等效)。

拓扑说明:接在单头 e9b3f7c1a6d4(R1 列默认 v1→v2)之后,downgrade 可回退列默认。

Revision ID: b4f8e2a9c1d7
Revises: e9b3f7c1a6d4
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4f8e2a9c1d7'
down_revision = 'e9b3f7c1a6d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """列默认 platform/devbox:v2 → aliyun registry 地址(仅元数据,存量行不变)"""
    op.alter_column(
        'containers', 'image',
        existing_type=sa.String(length=255),
        server_default='registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2',
        existing_nullable=False,
    )


def downgrade() -> None:
    """回退列默认至 platform/devbox:v2(同样不动存量行)"""
    op.alter_column(
        'containers', 'image',
        existing_type=sa.String(length=255),
        server_default='platform/devbox:v2',
        existing_nullable=False,
    )
