"""R6 交付提醒:notifications.type ENUM 追加 'req_delivery_reminder'

需求关联用户通知 DEVPLAN/R6(每日巡检向关联用户发交付临近/逾期提醒):
- MySQL ENUM 追加值必须 MODIFY 整列(追加到尾部,含全量现有值防截断)
- 完整 ALTER SQL 留痕:docs/20260926_需求关联用户通知/.scratch/R6/deploy-sql.md
  (及该需求 DEPLOY.md 的 MODIFY 语句)

Revision ID: f8b2d4a6c1e3
Revises: de60f84752af
Create Date: 2026-09-26
"""
from alembic import op

revision = 'f8b2d4a6c1e3'
down_revision = 'de60f84752af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """type ENUM 追加 req_delivery_reminder(尾部追加,不改现有值顺序,存量行不受影响)"""
    op.execute(
        "ALTER TABLE `notifications` "
        "MODIFY COLUMN `type` "
        "ENUM('deploy_failed','runner_offline','task_failed','push_failed',"
        "'review_approved','review_rejected','invited_to_project',"
        "'task_done','deployed','req_delivery_reminder') "
        "NOT NULL COMMENT '通知类型'"
    )


def downgrade() -> None:
    """缩回原枚举(执行前须确认无 type='req_delivery_reminder' 存量行,否则截断报错)"""
    op.execute(
        "ALTER TABLE `notifications` "
        "MODIFY COLUMN `type` "
        "ENUM('deploy_failed','runner_offline','task_failed','push_failed',"
        "'review_approved','review_rejected','invited_to_project',"
        "'task_done','deployed') "
        "NOT NULL COMMENT '通知类型'"
    )
