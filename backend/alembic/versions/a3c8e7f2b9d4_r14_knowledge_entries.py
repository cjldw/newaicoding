"""R14: knowledge_entries 知识条目表(含 ngram FULLTEXT 索引)

Revision ID: a3c8e7f2b9d4
Revises: f2a7c9e4b8d1
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "a3c8e7f2b9d4"
down_revision = "f2a7c9e4b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("entry_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="对外UUID"),
        sa.Column("project_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=True, comment="项目 id(null=平台级)"),
        sa.Column("req_id", mysql.CHAR(charset="utf8mb4", length=36), nullable=False, comment="来源需求 id"),
        sa.Column("type", sa.Enum("code_snippet", "pattern", "pitfall", "doc", name="knowledge_type_enum"),
                  nullable=False, comment="类型"),
        sa.Column("title", sa.String(length=128), nullable=False, comment="标题"),
        sa.Column("content", mysql.TEXT(charset="utf8mb4"), nullable=False, comment="内容(Markdown)"),
        sa.Column("tags", sa.JSON(), nullable=True, comment="标签数组"),
        sa.Column("source_links", sa.JSON(), nullable=True, comment="关联链接"),
        sa.Column("created_by", sa.Enum("ai", "human", name="knowledge_creator_enum"),
                  nullable=False, server_default="ai", comment="创建者类型"),
        sa.Column("status", sa.Enum("draft", "published", name="knowledge_status_enum"),
                  nullable=False, server_default="draft", comment="状态"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", name="uq_knowledge_entries_entry_id"),
    )
    op.create_index("ix_knowledge_entries_project_id", "knowledge_entries", ["project_id"])
    op.create_index("ix_knowledge_entries_req_id", "knowledge_entries", ["req_id"])
    op.create_index("ix_knowledge_entries_type", "knowledge_entries", ["type"])
    op.create_index("ix_knowledge_entries_status", "knowledge_entries", ["status"])
    op.create_index("ix_knowledge_project_status", "knowledge_entries", ["project_id", "status"])
    # FULLTEXT(ngram,支持中文分词;MySQL 8 内置 ngram)
    op.execute(
        "ALTER TABLE `knowledge_entries` ADD FULLTEXT INDEX `ft_knowledge_title_content` "
        "(`title`, `content`) WITH PARSER ngram"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE `knowledge_entries` DROP INDEX `ft_knowledge_title_content`")
    op.drop_index("ix_knowledge_project_status", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_status", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_type", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_req_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_project_id", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
