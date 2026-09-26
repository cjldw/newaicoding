"""R35/RD-20260926(R1)requirements 加 related_user_ids/prototype_links/delivery_date 三列

(slug 编号说明:初版误用 r33——已被 R33「侧栏抽屉+导览弹窗」(commit b1f18d4) 消费,
且 R34 已被并发需求分支策略占用,故顺延取未用的 r35;revision id 不变,开发库已应用不受影响。)

需求关联用户/原型链接/交付时间 三组字段一次建齐(rd-dev 拍板;R4/R5 后续消费):
- related_user_ids JSON NULL:关联用户 id 列表(对齐 knowledge_entry.tags JSON 先例)
- prototype_links JSON NULL:原型链接 [{label,url}]
- delivery_date DATE NULL:交付截止日(R6 巡检 WHERE + 排序需独立列)

存量行 NULL=未设置,不回填;详见 docs/20260926_需求关联用户通知/DEPLOY.md。

Revision ID: de60f84752af
Revises: e8f4a2c6b9d1
Create Date: 2026-09-26
"""
from alembic import op

revision = 'de60f84752af'
down_revision = 'e8f4a2c6b9d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """requirements 一次加三列(JSON×2 + DATE,均 NULL,AFTER priority 链式定位)"""
    op.execute(
        "ALTER TABLE `requirements` "
        "ADD COLUMN `related_user_ids` JSON NULL "
        "COMMENT '关联用户ID列表' "
        "AFTER `priority`, "
        "ADD COLUMN `prototype_links` JSON NULL "
        "COMMENT '原型链接[{label,url}]' "
        "AFTER `related_user_ids`, "
        "ADD COLUMN `delivery_date` DATE NULL "
        "COMMENT '交付截止日' "
        "AFTER `prototype_links`"
    )


def downgrade() -> None:
    op.drop_column('requirements', 'delivery_date')
    op.drop_column('requirements', 'prototype_links')
    op.drop_column('requirements', 'related_user_ids')
