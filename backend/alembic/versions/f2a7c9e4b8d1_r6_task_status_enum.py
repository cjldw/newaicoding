"""R6: tasks.status 枚举扩展(cases_review / passed)

Revision ID: f2a7c9e4b8d1
Revises: e1f6b3a8d5c2
Create Date: 2026-09-22
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2a7c9e4b8d1"
down_revision = "e1f6b3a8d5c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `tasks` MODIFY COLUMN `status` "
        "ENUM('pending','running','cases_review','passed','done','failed','cancelled','timeout') "
        "NOT NULL DEFAULT 'pending' COMMENT '状态(R6 扩展 cases_review/passed)'"
    )


def downgrade() -> None:
    # 回退前需把 cases_review → pending、passed → done,否则 ALTER 失败
    op.execute("UPDATE `tasks` SET `status`='pending' WHERE `status`='cases_review'")
    op.execute("UPDATE `tasks` SET `status`='done' WHERE `status`='passed'")
    op.execute(
        "ALTER TABLE `tasks` MODIFY COLUMN `status` "
        "ENUM('pending','running','done','failed','cancelled','timeout') "
        "NOT NULL DEFAULT 'pending' COMMENT '状态'"
    )
