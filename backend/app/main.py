"""旗程后端 FastAPI 应用入口"""

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

    yield

    # 关闭：释放数据库连接
    await close_db()
    logger.info("旗程后端已关闭")


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


# -------------------------------------------------------------------
# 健康检查
# -------------------------------------------------------------------
@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
