"""Alembic 迁移环境配置 - 异步模式(asyncmy)"""
import asyncio
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# 确保 backend/ 在 sys.path 中,以便 import app.*
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
# 导入所有模型,确保 metadata 包含完整表定义
from app.models.user import User  # noqa: E402, F401
from app.models.project import Project, ProjectRepo, PlatformSetting  # noqa: E402, F401
from app.models.project_member import ProjectMember  # noqa: E402, F401
from app.models.model_config import ModelConfig  # noqa: E402, F401
from app.models.skill import Skill, ProjectSkill  # noqa: E402, F401
from app.models.container import Container  # noqa: E402, F401
from app.models.runner import Runner  # noqa: E402, F401
from app.models.terminal import TerminalSession  # noqa: E402, F401
from app.models.route import Route  # noqa: E402, F401
from app.models.requirement import Requirement  # noqa: E402, F401
from app.models.task import Task, TaskUploadedFile, TaskMessage  # noqa: E402, F401
from app.models.knowledge_entry import KnowledgeEntry  # noqa: E402, F401
from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc  # noqa: E402, F401
from app.models.notification import Notification, UserNotificationSettings  # noqa: E402, F401
from app.models.audit_log import AuditLog, Invitation  # noqa: E402, F401

# Alembic Config 对象
config = context.config

# Python 日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata - 用于 autogenerate 支持
target_metadata = Base.metadata

# 注意: 不在这里 set_main_option,因为 URL 中含 %40 等字符
# 会与 configparser 的 % 插值语法冲突;改为在 engine 创建时直接使用 settings.URL


def run_migrations_offline() -> None:
    """离线模式 - 仅生成 SQL 脚本,不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """在线模式下实际执行迁移的辅助函数"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步在线模式 - 使用 asyncmy 驱动连接数据库"""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口 - 使用 asyncio 运行异步迁移"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
