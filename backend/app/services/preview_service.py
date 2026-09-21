"""预览服务 - R10(端口探测回报处理 + 预览 URL)

链路:Runner 探测容器端口(5173/8000)→ 回报 port_listening / port_closed
→ 平台注册/摘除路由(routes 表,type=preview)→ 网关(R15)按 Host 转发。
容器销毁(handle_container_stopped)时摘除全部路由。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.container import Container
from app.models.project import Project
from app.models.route import Route
from app.services import route_service

logger = logging.getLogger(__name__)

PREVIEW_PORTS = (5173, 8000)


async def get_task_previews(db: AsyncSession, task_id: str) -> list[dict]:
    """任务工作台预览列表(port/preview_url/status)"""
    result = await db.execute(
        select(Route).where(Route.task_id == task_id, Route.type == "preview")
        .order_by(Route.port.asc())
    )
    routes = result.scalars().all()
    return [
        {
            "port": r.port,
            "preview_url": _preview_url(r.host),
            "status": r.status,
        }
        for r in routes
    ]


def _preview_url(host: str) -> str:
    return f"http://{host}"


# ---------------------------------------------------------------------------
# Runner 回报处理
# ---------------------------------------------------------------------------
async def handle_port_listening(db: AsyncSession, container_id: str, port: int) -> None:
    """
    端口开始监听:注册/激活路由。
    host = {slug}--{taskId}--{port}.{preview_base_domain}
    upstream = http://{runner_host}:{mapped_port}(D20 网关直连 Runner 宿主机)
    """
    from app.services.runner_service import runner_registry

    result = await db.execute(select(Container).where(Container.container_id == container_id))
    container = result.scalar_one_or_none()
    if container is None or container.status != "running":
        logger.info("port_listening 忽略(容器不在跑)container=%s", container_id)
        return

    project_result = await db.execute(select(Project).where(Project.project_id == container.project_id))
    project = project_result.scalar_one_or_none()
    slug = project.slug if project else "unknown"

    base_domain = await route_service.get_preview_base_domain(db)
    host = f"{route_service.build_preview_host(slug, container.task_id or '', port)}.{base_domain}"

    conn = runner_registry.get(container.runner_id)
    runner_host = conn.host if conn else ""
    upstream = f"http://{runner_host}:{_mapped_port(container, port)}"

    await route_service.upsert_route(
        db,
        host=host,
        upstream=upstream,
        type="preview",
        task_id=container.task_id,
        project_id=container.project_id,
        port=port,
        auth_required=True,
        status="active",
    )
    logger.info("预览路由激活 task=%s port=%s host=%s", container.task_id, port, host)


async def handle_port_closed(db: AsyncSession, container_id: str, port: int) -> None:
    """端口关闭:路由置 inactive(前端显示"服务未启动")"""
    result = await db.execute(select(Container).where(Container.container_id == container_id))
    container = result.scalar_one_or_none()
    if container is None:
        return

    project_result = await db.execute(select(Project).where(Project.project_id == container.project_id))
    project = project_result.scalar_one_or_none()
    slug = project.slug if project else "unknown"

    base_domain = await route_service.get_preview_base_domain(db)
    host = f"{route_service.build_preview_host(slug, container.task_id or '', port)}.{base_domain}"
    await route_service.set_route_status(db, host, "inactive")
    logger.info("预览路由停用 task=%s port=%s", container.task_id, port)


def _mapped_port(container: Container, container_port: int) -> int:
    """容器端口 → Runner 宿主机映射端口(R8 回报)"""
    if container_port == 5173:
        return container.runner_host_port_5173 or 0
    if container_port == 8000:
        return container.runner_host_port_8000 or 0
    return 0
