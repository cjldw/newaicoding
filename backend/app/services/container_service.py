"""容器服务 - R8 调度与生命周期(平台侧)

- 启动:配额校验 → 调度 Runner → 下发 start_container → 登记 creating
- 回报:container_started → running + 端口映射;container_stopped → destroyed;die 事件 → failed
- 停止:下发 stop_container(Runner 销毁前强制 push)
- 注入契约:env 中 LLM/GitLab 等由调用方(R4)组装;MCP/Skills 注入 R17 已提供读取函数

R8 最小边界:任务流程(R4)尚未建,本服务提供编排函数供 R4 调用;
Runner 注册表为内存态,R16 升级 DB。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import PlatformSetting, Project
from app.services import runner_service
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "platform/devbox:v1"
EXPOSED_PORTS = [5173, 8000]
MAX_USER_RUNNING_CONTAINERS = 5   # 单用户同时运行容器 ≤ 5(含部署中)


async def _platform_container_limit(db: AsyncSession) -> int:
    """平台总容器数上限(平台设置实时读取,默认 50)"""
    result = await db.execute(
        select(PlatformSetting.value).where(PlatformSetting.key == "max_containers_total")
    )
    value = result.scalar_one_or_none()
    if value is None:
        return 50
    try:
        return int(value)
    except (TypeError, ValueError):
        return 50


async def check_quotas(db: AsyncSession, owner_user_id: str) -> None:
    """配额:单用户运行中 ≤5(8001);平台总数 ≤ max_containers_total(8002)"""
    # 单用户:containers.project_id → projects.project_id,projects.owner_id = 用户
    user_cnt = await db.execute(
        select(func.count(Container.id))
        .join(Project, Project.project_id == Container.project_id)
        .where(
            Project.owner_id == owner_user_id,
            Container.status.in_(["creating", "running"]),
        )
    )
    if (user_cnt.scalar() or 0) >= MAX_USER_RUNNING_CONTAINERS:
        raise BizError(ErrCode.USER_CONTAINER_LIMIT, "同时运行容器数已达上限(5 个)")

    total_cnt = await db.execute(
        select(func.count(Container.id)).where(Container.status.in_(["creating", "running"]))
    )
    limit = await _platform_container_limit(db)
    if (total_cnt.scalar() or 0) >= limit:
        raise BizError(ErrCode.PLATFORM_CONTAINER_LIMIT, "平台容器总数已达上限")


async def schedule_and_start(
    db: AsyncSession,
    *,
    project_id: str,
    task_id: Optional[str],
    owner_user_id: str,
    env: dict,
    repos: list[dict],
    required_role: str = "general",
    image: str = DEFAULT_IMAGE,
    cpu_limit: str = "2c",
    mem_limit: str = "4g",
    disk_limit: str = "10g",
) -> Container:
    """
    调度并启动容器:
    1. 配额校验(用户 ≤5 → 8001;平台 → 8002)
    2. 调度器选 Runner(最少负载 + role 匹配;无可用 → 8003)
    3. 登记 containers(status=creating)并下发 start_container
    Runner 回报 container_started 后由 handle_container_started 置 running。
    """
    logger.info("容器启动入口 project=%s task=%s role=%s", project_id, task_id, required_role)

    # ---- 配额 ----
    await check_quotas(db, owner_user_id)

    # ---- 调度 ----
    conn = runner_registry.pick_runner(required_role)
    if conn is None:
        raise BizError(
            ErrCode.NO_RUNNER_AVAILABLE,
            "无可用 Runner" if required_role == "general" else "无可用部署 Runner",
        )

    # ---- 登记 ----
    container = Container(
        container_id=f"pending-{task_id or project_id}-{id(conn)}",
        task_id=task_id,
        runner_id=conn.runner_id,
        project_id=project_id,
        status="creating",
        image=image,
        cpu_limit=cpu_limit,
        mem_limit=mem_limit,
        disk_limit=disk_limit,
        exposed_ports=EXPOSED_PORTS,
    )
    db.add(container)
    await db.flush()

    # ---- 下发 ----
    message = runner_service.build_start_container_message(
        task_id=task_id or container.container_id,
        image=image,
        env=env,
        ports=EXPOSED_PORTS,
        repos=repos,
        cpu_limit=cpu_limit,
        mem_limit=mem_limit,
        disk_limit=disk_limit,
    )
    try:
        await runner_service.send_to_runner(conn, message)
    except Exception as e:
        container.status = "failed"
        container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
        logger.warning("start_container 下发失败 runner=%s: %s", conn.runner_id, e)
        raise BizError(ErrCode.NO_RUNNER_AVAILABLE, "Runner 指令下发失败")

    conn.load += 1
    logger.info("容器指令已下发 container=%s runner=%s", container.container_id, conn.runner_id)
    return container


async def request_stop(db: AsyncSession, container: Container) -> None:
    """
    请求停止容器:下发 stop_container(Runner 销毁前强制 push 未 push commit;
    push 失败 Runner 保留容器 30 分钟由平台重试——R4/R16 联调完善)。
    """
    conn = runner_registry.get(container.runner_id)
    if conn is None:
        # Runner 离线:标记 stopped 待 Runner 恢复对账(R16)
        container.status = "stopped"
        await db.flush()
        logger.warning("Runner 离线,容器标记 stopped container=%s", container.container_id)
        return
    await runner_service.send_to_runner(
        conn, runner_service.build_stop_container_message(container.container_id)
    )
    logger.info("stop_container 已下发 container=%s", container.container_id)


# ---------------------------------------------------------------------------
# Runner 回报处理(WebSocket 端点调用)
# ---------------------------------------------------------------------------
async def handle_container_started(
    db: AsyncSession,
    task_id: str,
    docker_container_id: str,
    ports: dict,
) -> None:
    """container_started 回报:置 running + 记录端口映射;container_id 替换 pending 占位"""
    result = await db.execute(
        select(Container).where(
            Container.task_id == task_id,
            Container.status == "creating",
        ).order_by(Container.id.desc()).limit(1)
    )
    container = result.scalar_one_or_none()
    if container is None:
        logger.warning("container_started 无匹配记录 task=%s", task_id)
        return

    # pending 占位 id 替换为真实 docker id(UNIQUE 冲突时追加随机后缀)
    from app.models.container import Container as _C

    dup = await db.execute(
        select(_C.id).where(_C.container_id == docker_container_id).limit(1)
    )
    container.container_id = (
        docker_container_id if dup.scalar_one_or_none() is None
        else f"{docker_container_id}-{container.id}"
    )
    container.status = "running"
    container.runner_host_port_5173 = ports.get("5173")
    container.runner_host_port_8000 = ports.get("8000")
    await db.flush()
    logger.info(
        "容器已启动 container=%s runner=%s ports=%s",
        container.container_id, container.runner_id, ports,
    )


async def handle_container_stopped(db: AsyncSession, docker_container_id: str) -> None:
    """container_stopped 回报:destroyed + destroyed_at;调度负载减一"""
    result = await db.execute(
        select(Container).where(Container.container_id == docker_container_id)
    )
    container = result.scalar_one_or_none()
    if container is None:
        logger.warning("container_stopped 无匹配记录 %s", docker_container_id)
        return

    container.status = "destroyed"
    container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    conn = runner_registry.get(container.runner_id)
    if conn is not None and conn.load > 0:
        conn.load -= 1
    logger.info("容器已销毁 container=%s", docker_container_id)


async def handle_container_event(
    db: AsyncSession,
    event: str,
    docker_container_id: str,
    exit_code: Optional[int] = None,
) -> None:
    """容器事件回报:start → running;die/oom → failed(Runner 侧重启 ≤3 次由 Runner 侧自理)"""
    result = await db.execute(
        select(Container).where(Container.container_id == docker_container_id)
    )
    container = result.scalar_one_or_none()
    if container is None:
        logger.warning("container_event 无匹配记录 %s %s", event, docker_container_id)
        return

    if event == "start" and container.status in ("creating", "stopped"):
        container.status = "running"
    elif event in ("die", "oom"):
        # Runner 侧自动重启 ≤3 次;最终失败事件由 Runner 置 restart_failed 上报,
        # 这里按 die 先标 failed(R16 联调细化)
        container.status = "failed"
        if exit_code is not None:
            logger.warning("容器异常退出 container=%s exit=%s", docker_container_id, exit_code)
    await db.flush()
