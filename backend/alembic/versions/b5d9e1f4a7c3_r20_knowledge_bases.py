"""R20: knowledge_bases / knowledge_docs 双表(含 ngram FULLTEXT)

Revision ID: b5d9e1f4a7c3
Revises: a3c8e7f2b9d4
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "b5d9e1f4a7c3"
down_revision = "a3c8e7f2b9d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("kb_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="项目 id"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="显示名(同项目唯一)"),
        sa.Column("description", sa.String(length=255), nullable=True, server_default="", comment="描述"),
        sa.Column("source_type", sa.Enum("blank", "repo_import", name="kb_source_enum"),
                  nullable=False, server_default="blank", comment="类型"),
        sa.Column("source_config", sa.JSON(), nullable=True, comment="{repo_id,branch,paths}"),
        sa.Column("import_status", sa.Enum("idle", "importing", "done", "failed", name="kb_import_status_enum"),
                  nullable=False, server_default="idle", comment="导入状态(blank 恒 idle)"),
        sa.Column("import_error", sa.String(length=255), nullable=True, comment="最近失败原因"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True, comment="最近导入/同步时间"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kb_id", name="uq_knowledge_bases_kb_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_kb_project_name"),
    )
    op.create_index("ix_knowledge_bases_project_id", "knowledge_bases", ["project_id"])
    op.create_index("ix_knowledge_bases_import_status", "knowledge_bases", ["import_status"])
    op.create_index("ix_knowledge_bases_created_by", "knowledge_bases", ["created_by"])

    op.create_table(
        "knowledge_docs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("doc_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("kb_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="所属知识库"),
        sa.Column("title", sa.String(length=128), nullable=False, comment="页面标题"),
        sa.Column("path", sa.String(length=255), nullable=False, comment="树形路径(同库唯一)"),
        sa.Column("content", mysql.TEXT(charset="utf8mb4"), nullable=False, server_default="", comment="Markdown 正文"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="同级排序"),
        sa.Column("source_file_path", sa.String(length=255), nullable=True, comment="导入来源路径(blank 为 NULL)"),
        sa.Column("created_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="创建者"),
        sa.Column("updated_by", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="更新者"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id", name="uq_knowledge_docs_doc_id"),
        sa.UniqueConstraint("kb_id", "path", name="uq_kb_doc_path"),
    )
    op.create_index("ix_knowledge_docs_kb_id", "knowledge_docs", ["kb_id"])
    op.execute(
        "ALTER TABLE `knowledge_docs` ADD FULLTEXT INDEX `ft_kb_docs_title_content` "
        "(`title`, `content`) WITH PARSER ngram"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `knowledge_docs` DROP INDEX `ft_kb_docs_title_content`")
    op.drop_index("ix_knowledge_docs_kb_id", table_name="knowledge_docs")
    op.drop_table("knowledge_docs")
    op.drop_index("ix_knowledge_bases_created_by", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_import_status", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_project_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
