"""路由服务 - R10/R15 共享(routes 表注册/摘除/鉴权;网关本体归 R15)"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.route import Route
from app.services.platform_settings_service import get_setting

logger = logging.getLogger(__name__)


async def get_preview_base_domain(db: AsyncSession) -> str:
    """预览泛域名根(平台设置实时读取;默认值与分片一致)"""
    value = await get_setting(db, "preview_base_domain")
    return value or "preview.coding-console.zhanqitv.com.cn"


def build_preview_host(slug: str, task_id: str, port: int) -> str:
    """预览 Host:`{slug}--{taskId}--{port}.{preview_base_domain}`(任务级唯一)"""
    return f"{slug}--{task_id}--{port}"


async def get_by_host(db: AsyncSession, host: str) -> Optional[Route]:
    result = await db.execute(select(Route).where(Route.host == host))
    return result.scalar_one_or_none()


async def upsert_route(
    db: AsyncSession,
    *,
    host: str,
    upstream: str,
    type: str,
    task_id: Optional[str],
    project_id: str,
    port: int,
    auth_required: bool = True,
    status: str = "active",
) -> Route:
    """注册或更新路由(幂等;同 host 复用行)"""
    result = await db.execute(select(Route).where(Route.host == host))
    route = result.scalar_one_or_none()
    if route is None:
        route = Route(
            host=host, upstream=upstream, type=type,
            task_id=task_id, project_id=project_id, port=port,
            auth_required=auth_required, status=status,
        )
        db.add(route)
    else:
        route.upstream = upstream
        route.task_id = task_id
        route.port = port
        route.status = status
    await db.flush()
    logger.info("路由注册 host=%s upstream=%s status=%s", host, upstream, status)
    return route


async def set_route_status(db: AsyncSession, host: str, status: str) -> None:
    """端口关闭 → inactive;重新监听 → active"""
    result = await db.execute(select(Route).where(Route.host == host))
    route = result.scalar_one_or_none()
    if route is not None and route.status != status:
        route.status = status
        await db.flush()
        logger.info("路由状态变更 host=%s → %s", host, status)


async def register_deploy_route(
    db: AsyncSession,
    *,
    project_id: str,
    task_id: str,
    container_id: str,
    runner_id: str,
    deploy_host: str,
    deploy_port: int,
    upstream: str,
) -> Route:
    """
    R7/R15:部署路由注册(deploy_host 默认 {slug}.{deploy_base_domain},可自定义 Q29)。
    deploy_host 全平台唯一(HOST UNIQUE 硬约束;冲突 → 15001);部署路由公开不鉴权。
    """
    from app.core.response import BizError, ErrCode

    host = f"{deploy_host}:{deploy_port}"
    dup = await db.execute(select(Route.id).where(Route.host == host).limit(1))
    if dup.scalar_one_or_none() is not None:
        raise BizError(ErrCode.DEPLOY_HOST_CONFLICT, "部署域名冲突:该 deploy_host 已被占用")
    return await upsert_route(
        db,
        host=host,
        upstream=upstream,
        type="deploy",
        task_id=task_id,
        project_id=project_id,
        port=deploy_port,
        auth_required=False,
        status="active",
    )


async def remove_routes_for_container(db: AsyncSession, container_id: str) -> int:
    """容器销毁:摘除该容器的全部预览路由(URL 失效)"""
    from app.models.container import Container

    result = await db.execute(
        select(Route).where(Route.task_id.in_(
            select(Container.task_id).where(Container.container_id == container_id)
        ), Route.type == "preview")
    )
    routes = result.scalars().all()
    for route in routes:
        await db.delete(route)
    if routes:
        await db.flush()
        logger.info("容器路由摘除 container=%s count=%d", container_id, len(routes))
    return len(routes)


# ---------------------------------------------------------------------------
# 预览访问鉴权(R15 网关调用;非成员 403)
# ---------------------------------------------------------------------------
async def check_preview_access(db: AsyncSession, host: str, user) -> bool:
    """
    预览鉴权:登录 + 项目成员(任意角色)。
    user 为 None(未登录)或非成员 → False(网关转 403)。
    """
    if user is None:
        return False
    route = await get_by_host(db, host)
    if route is None or route.status != "active":
        return False
    result = await db.execute(select(Project).where(Project.project_id == route.project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return False
    from app.services.project_member_service import get_project_role

    role = await get_project_role(db, project, user)
    return bool(role)
