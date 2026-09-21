"""R2: projects / project_repos / platform_settings 三表

Revision ID: a7d21c9e5f40
Revises: b7e2a1c3d4f5
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "a7d21c9e5f40"
down_revision = "b7e2a1c3d4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # projects 项目表
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="显示名(同用户下唯一由服务层校验)"),
        sa.Column("slug", sa.String(length=64), nullable=False, comment="全局唯一,小写字母数字-,子域/主仓库名"),
        sa.Column("description", sa.String(length=255), nullable=True, server_default="", comment="描述"),
        sa.Column("default_branch", sa.String(length=64), nullable=False, server_default="master", comment="项目默认分支"),
        sa.Column(
            "visibility",
            sa.Enum("private", "internal", name="project_visibility_enum"),
            nullable=False,
            server_default="private",
            comment="可见性",
        ),
        sa.Column("owner_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者 user_id"),
        sa.Column(
            "status",
            sa.Enum("active", "archived", "deleted", name="project_status_enum"),
            nullable=False,
            server_default="active",
            comment="状态",
        ),
        sa.Column("mcp_config_encrypted", sa.Text(), nullable=True, comment="AES-GCM 加密的项目级 MCP 配置(R17 用)"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删时间(7 天后物理删除定时任务用)"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_projects_project_id"),
        sa.UniqueConstraint("slug", name="uq_projects_slug"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index("ix_projects_status", "projects", ["status"])

    # ------------------------------------------------------------------
    # project_repos 项目-仓库关联表
    # ------------------------------------------------------------------
    op.create_table(
        "project_repos",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("repo_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="平台内部对外UUID"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column(
            "role",
            sa.Enum("main", "test", "docs", "other", name="repo_role_enum"),
            nullable=False,
            comment="仓库角色(main 每项目唯一由服务层保证)",
        ),
        sa.Column("gitlab_repo_url", sa.String(length=255), nullable=False, comment="GitLab 仓库 URL"),
        sa.Column("gitlab_repo_id", sa.Integer(), nullable=False, comment="GitLab 内部 id"),
        sa.Column(
            "gitlab_bind_type",
            sa.Enum("auto", "manual", name="repo_bind_type_enum"),
            nullable=False,
            server_default="auto",
            comment="绑定方式",
        ),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="绑定时操作人 user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="绑定时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_id", name="uq_project_repos_repo_id"),
        sa.UniqueConstraint("project_id", "gitlab_repo_id", name="uq_project_gitlab_repo"),
    )
    op.create_index("ix_project_repos_project_id", "project_repos", ["project_id"])
    op.create_index("ix_project_repos_project_role", "project_repos", ["project_id", "role"])

    # ------------------------------------------------------------------
    # platform_settings 平台设置单例键值表
    # ------------------------------------------------------------------
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=64), nullable=False, comment="配置键(白名单枚举)"),
        sa.Column("value", sa.JSON(), nullable=False, comment='配置值;敏感项存 {"__encrypted": <base64>}'),
        sa.Column("updated_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="最近修改人(超管)"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_index("ix_project_repos_project_role", table_name="project_repos")
    op.drop_index("ix_project_repos_project_id", table_name="project_repos")
    op.drop_table("project_repos")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
