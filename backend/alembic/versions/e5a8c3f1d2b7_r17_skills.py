"""R17: skills / project_skills 两表(mcp_config_encrypted 列已随 R2 projects 建表存在,无需变更)

Revision ID: e5a8c3f1d2b7
Revises: d4f9a1e2b6c8
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "e5a8c3f1d2b7"
down_revision = "d4f9a1e2b6c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # skills 表(name 唯一性:platform 作用域内 + 项目作用域内由服务层保证,
    # 不设全局 UNIQUE —— 见模型注释;交互规则要求项目级可覆盖平台级同名)
    # ------------------------------------------------------------------
    op.create_table(
        "skills",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("skill_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="Skill 名(kebab-case)"),
        sa.Column("description", sa.String(length=255), nullable=False, comment="一句话描述"),
        sa.Column("content", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="Markdown 正文(YAML frontmatter + 正文)"),
        sa.Column(
            "scope",
            sa.Enum("platform", "project", name="skill_scope_enum"),
            nullable=False,
            server_default="platform",
            comment="作用域",
        ),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="scope=project 时必填"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", name="uq_skills_skill_id"),
    )
    op.create_index("ix_skills_scope", "skills", ["scope"])
    op.create_index("ix_skills_project_id", "skills", ["project_id"])
    op.create_index("ix_skills_scope_project_name", "skills", ["scope", "project_id", "name"])

    # ------------------------------------------------------------------
    # project_skills 安装关联表
    # ------------------------------------------------------------------
    op.create_table(
        "project_skills",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("skill_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="Skill id"),
        sa.Column("installed_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="安装人 user_id"),
        sa.Column("installed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="安装时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "skill_id", name="uq_project_skill"),
    )
    op.create_index("ix_project_skills_project_id", "project_skills", ["project_id"])
    op.create_index("ix_project_skills_skill_id", "project_skills", ["skill_id"])


def downgrade() -> None:
    op.drop_index("ix_project_skills_skill_id", table_name="project_skills")
    op.drop_index("ix_project_skills_project_id", table_name="project_skills")
    op.drop_table("project_skills")
    op.drop_index("ix_skills_scope_project_name", table_name="skills")
    op.drop_index("ix_skills_project_id", table_name="skills")
    op.drop_index("ix_skills_scope", table_name="skills")
    op.drop_table("skills")
