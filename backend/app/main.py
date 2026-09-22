"""旗程后端 FastAPI 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# -------------------------------------------------------------------
# 兼容性补丁: pydantic 2.5.3 + pydantic_core 2.18.1 版本不兼容
# pydantic_core 定义了 enum/tuple 两种 core_schema type,
# 但 pydantic 2.5.3 的 GenerateJsonSchema 缺少对应的处理方法,
# 导致 /openapi.json 生成时抛出 TypeError。
# 这里补上缺失的方法,使 OpenAPI schema 能正常生成。
# -------------------------------------------------------------------
from pydantic.json_schema import GenerateJsonSchema
from pydantic._internal._generate_schema import to_jsonable_python


def _enum_schema(self, schema):
    """为 enum core_schema 生成 JSON Schema"""
    members = schema.get("members", [])
    enum_values = [v.value if isinstance(v, Enum) else v for v in members]
    enum_values = [to_jsonable_python(v) for v in enum_values]

    if not enum_values:
        return {}

    types = {type(e) for e in enum_values}
    result = {"enum": enum_values}
    if types == {str}:
        result["type"] = "string"
    elif types == {int}:
        result["type"] = "integer"
    elif types == {float}:
        result["type"] = "number"
    return result


def _tuple_schema(self, schema):
    """为 tuple core_schema 生成 JSON Schema"""
    # tuple 在 JSON Schema 中映射为 array
    items_schema = schema.get("items_schema")
    if items_schema:
        return {
            "type": "array",
            "items": [self.generate_schema(s) for s in items_schema],
        }
    return {"type": "array"}


if not hasattr(GenerateJsonSchema, "enum_schema"):
    GenerateJsonSchema.enum_schema = _enum_schema
if not hasattr(GenerateJsonSchema, "tuple_schema"):
    GenerateJsonSchema.tuple_schema = _tuple_schema

from app.config import settings
from app.database import init_db, close_db
from app.core.response import register_exception_handlers
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.projects import router as projects_router
from app.api.admin.platform_settings import router as platform_settings_router
from app.api.skills import router as skills_router
from app.api.admin.skills import router as admin_skills_router
from app.api.runner_ws import router as runner_ws_router
from app.api.admin.runners import router as admin_runners_router
from app.api.terminal import router as terminal_router
from app.api.previews import router as previews_router
from app.api.files import router as files_router
from app.api.requirements import router as requirements_router
from app.api.tasks import router as tasks_router
from app.api.knowledge import router as knowledge_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.dashboard import router as dashboard_router
from app.api.dashboard_views import router as dashboard_views_router
from app.api.notifications import router as notifications_router
from app.api.admin.users_admin import router as users_admin_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# 生命周期管理
# -------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的资源管理"""
    # 启动：初始化数据库连接
    logger.info("旗程后端启动中... 环境=%s", settings.ENVIRONMENT)
    await init_db()
    logger.info("数据库连接池初始化完成")

    # Runner 心跳超时巡检(R16):每 60s 一轮,>60s 无心跳 → offline
    sweep_task = asyncio.create_task(_runner_offline_sweep())

    # R19:审计异步写入的会话工厂注入
    from app.database import async_session_factory as _asf
    from app.api.admin import users_admin as _users_admin

    _users_admin.set_audit_session_factory(_asf)

    yield

    # 关闭：释放资源
    sweep_task.cancel()
    await close_db()
    logger.info("旗程后端已关闭")


async def _runner_offline_sweep():
    """每 60s 扫描一次 Runner 心跳,超时标 offline(R16)"""
    import asyncio as _asyncio

    from app.database import async_session_factory
    from app.services import runner_service

    while True:
        try:
            await _asyncio.sleep(60)
            async with async_session_factory() as db:
                count = await runner_service.sweep_offline(db)
                await db.commit()
                if count:
                    logger.info("Runner 心跳巡检:%d 个转 offline", count)
        except _asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Runner 心跳巡检异常(下一轮继续)")


# -------------------------------------------------------------------
# 创建 FastAPI 应用
# -------------------------------------------------------------------
app = FastAPI(
    title="旗程 AI Web 开发平台",
    description="旗程后端 API 文档",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# -------------------------------------------------------------------
# CORS 中间件
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境需配置白名单
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# 注册全局异常处理器
# -------------------------------------------------------------------
register_exception_handlers(app)


# -------------------------------------------------------------------
# 注册路由
# -------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(platform_settings_router)
app.include_router(skills_router)
app.include_router(admin_skills_router)
app.include_router(runner_ws_router)
app.include_router(admin_runners_router)
app.include_router(terminal_router)
app.include_router(previews_router)
app.include_router(files_router)
app.include_router(requirements_router)
app.include_router(tasks_router)
app.include_router(knowledge_router)
app.include_router(knowledge_bases_router)
app.include_router(dashboard_router)
app.include_router(dashboard_views_router)
app.include_router(notifications_router)
app.include_router(users_admin_router)


# -------------------------------------------------------------------
# 健康检查
# -------------------------------------------------------------------
@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
