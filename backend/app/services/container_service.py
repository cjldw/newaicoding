"""容器服务 - R8 调度与生命周期(平台侧)

- 启动:配额校验 → 调度 Runner → 下发 start_container → 登记 creating
- 回报:container_started → running + 端口映射;container_stopped → destroyed;die 事件 → failed
- 停止:下发 stop_container(Runner 销毁前强制 push)
- 注入契约:env 中 LLM/GitLab 等由调用方(R4)组装;MCP/Skills 注入 R17 已提供读取函数

R8 最小边界:任务流程(R4)尚未建,本服务提供编排函数供 R4 调用;
Runner 注册表为内存态,R16 升级 DB。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import PlatformSetting, Project
from app.models.task import Task
from app.services import runner_service
from app.services.platform_settings_service import get_setting
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)

# F2.a: request_stop 等待 Runner container_stopped 回报的超时秒数
# 超时后强制置 container.status=destroyed + destroyed_at,防止 DB+docker 双驻留
STOP_TIMEOUT_SECONDS = 60.0

# 默认任务容器镜像(兜底值;后台设置项 container_image 优先于本常量,见 schedule_and_start)
DEFAULT_IMAGE = "registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2"
EXPOSED_PORTS = [5173, 8000]


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


async def _user_container_limit(db: AsyncSession) -> int:
    """单用户容器数上限(平台设置实时读取,默认 5)"""
    result = await db.execute(
        select(PlatformSetting.value).where(PlatformSetting.key == "max_containers_per_user")
    )
    value = result.scalar_one_or_none()
    if value is None:
        return 5
    try:
        return int(value)
    except (TypeError, ValueError):
        return 5


async def check_quotas(db: AsyncSession, owner_user_id: str) -> None:
    """配额:单用户运行中 ≤ max_containers_per_user(8001);平台总数 ≤ max_containers_total(8002)"""
    # 单用户:containers.project_id → projects.project_id,projects.owner_id = 用户
    user_cnt = await db.execute(
        select(func.count(Container.id))
        .join(Project, Project.project_id == Container.project_id)
        .where(
            Project.owner_id == owner_user_id,
            Container.status.in_(["creating", "running"]),
        )
    )
    user_limit = await _user_container_limit(db)
    if (user_cnt.scalar() or 0) >= user_limit:
        raise BizError(ErrCode.USER_CONTAINER_LIMIT, f"同时运行容器数已达上限({user_limit} 个)")

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
    task_tag: Optional[str] = None,
    image: Optional[str] = None,
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

    镜像解析(创建时刻定格,改动不影响存量容器):
    显式传参 > 后台设置 container_image > DEFAULT_IMAGE 常量兜底。
    """
    logger.info("容器启动入口 project=%s task=%s role=%s", project_id, task_id, required_role)

    # ---- 镜像解析(显式传参优先;设置项未配置返回 None,再回落常量) ----
    if image is None:
        image = await get_setting(db, "container_image") or DEFAULT_IMAGE

    # ---- 配额 ----
    await check_quotas(db, owner_user_id)

    # ---- 调度(R16:DB 注册表;最少负载 + role 匹配) ----
    # R32:task_tag 透传做 tags 匹配(空/NULL=兜底;deploy 路径恒 None 行为不变)
    runner = await runner_service.pick_runner_db(db, required_role, task_tag=task_tag)
    if runner is None:
        raise BizError(
            ErrCode.NO_RUNNER_AVAILABLE,
            "无可用 Runner" if required_role == "general" else "无可用部署 Runner",
        )
    conn = runner_registry.get(runner.runner_id)
    if conn is None:
        # DB 在线但连接不在(Runner 刚断开):按无可用处理
        raise BizError(ErrCode.NO_RUNNER_AVAILABLE, "无可用 Runner")

    # ---- 登记 ----
    container = Container(
        container_id=f"pending-{task_id or project_id}-{id(conn)}",
        task_id=task_id,
        runner_id=runner.runner_id,
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
        logger.warning("start_container 下发失败 runner=%s: %s", runner.runner_id, e)
        raise BizError(ErrCode.NO_RUNNER_AVAILABLE, "Runner 指令下发失败")

    # 调度占用:+1(DB);stopped/die→failed 时 -1
    runner.current_containers = (runner.current_containers or 0) + 1
    conn.load = runner.current_containers
    await db.flush()
    logger.info("容器指令已下发 container=%s runner=%s", container.container_id, runner.runner_id)
    return container


async def request_stop(db: AsyncSession, container: Container) -> None:
    """
    请求停止容器:下发 stop_container(Runner 销毁前强制 push 未 push commit;
    push 失败 Runner 保留容器 30 分钟由平台重试——R4/R16 联调完善)。

    F2.a:下发后等 Runner container_stopped 回报(超时 STOP_TIMEOUT_SECONDS);
    超时未回报 → 直接置 container.status=destroyed + destroyed_at,防止 DB+docker 双驻留。
    """
    conn = runner_registry.get(container.runner_id)
    if conn is None:
        # Runner 离线:标记 stopped 待 Runner 恢复对账(F2.b 补发)
        container.status = "stopped"
        await db.flush()
        logger.warning("Runner 离线,容器标记 stopped container=%s", container.container_id)
        return

    # 下发 stop_container 消息
    await runner_service.send_to_runner(
        conn, runner_service.build_stop_container_message(container.container_id)
    )
    logger.info("stop_container 已下发 container=%s", container.container_id)

    # F2.a:等待 Runner 回报 container_stopped(超时兜底)
    # 使用 asyncio.Event 等待 handle_container_stopped 回调
    stop_event = asyncio.Event()
    _pending_stop_events[container.container_id] = stop_event

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=STOP_TIMEOUT_SECONDS)
        # 正常回报:由 handle_container_stopped 处理状态更新
        logger.info("收到 container_stopped 回报 container=%s", container.container_id)
    except asyncio.TimeoutError:
        # 超时未回报:强制置 destroyed,防止 DB+docker 双驻留
        container.status = "destroyed"
        container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
        logger.warning(
            "等待 container_stopped 超时(%ss),强制置 destroyed container=%s",
            STOP_TIMEOUT_SECONDS, container.container_id
        )
    finally:
        _pending_stop_events.pop(container.container_id, None)


# F2.a:待回报的 container_id → asyncio.Event 映射
# handle_container_stopped 回调时 set() 对应 event
_pending_stop_events: dict[str, asyncio.Event] = {}


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
        # R8.F7(BUG-081)复活:回报迟到/重发时,行可能已被对账误置 destroyed——
        # 按 task 找最近一条 pending 占位行,且该 task 尚无 running 行时复活承接回报
        dead = (await db.execute(
            select(Container).where(
                Container.task_id == task_id,
                Container.container_id.like("pending-%"),
            ).order_by(Container.id.desc()).limit(1)
        )).scalar_one_or_none()
        running_row = (await db.execute(
            select(Container.id).where(
                Container.task_id == task_id, Container.status == "running"
            ).limit(1)
        )).scalar_one_or_none()
        if dead is None or running_row is not None:
            logger.warning("container_started 无匹配记录 task=%s", task_id)
            return
        dead.status = "creating"
        dead.destroyed_at = None
        await db.flush()
        container = dead
        logger.info(
            "container_started 复活占位行 task=%s row=%s(回报迟到自愈)", task_id, dead.id
        )

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

    # R32.F1(BUG-082 前置):容器就绪后注入项目 Skills/MCP ——
    # 打磨/开发/测试/发布全类型生效(claude CLI 进程级读取 ~/.claude/skills 与 ~/.claude.json)
    from app.services import task_service as _task_service

    task_row = (
        await db.execute(select(Task).where(Task.task_id == task_id).limit(1))
    ).scalar_one_or_none()
    if task_row is not None:
        # R32.F8(BUG-060):新容器内无旧 claude 会话——残留 session_id 会让首条消息
        # --resume 静默失败(stderr 被 runner 吞)→ 空回复落库;置空让下条消息重建会话
        if task_row.claude_session_id is not None:
            task_row.claude_session_id = None
            await db.flush()
        try:
            await _task_service.inject_task_claude_assets(db, task_row, container)
        except Exception as e:  # 注入失败不阻塞容器就绪(降级为无技能/无 MCP)
            logger.warning("claude 资产注入失败 task=%s: %s", task_id, e)

    # BUG-030:任务行回填 container_id/runner_id(任务详情展示、停止/取消链路依赖;
    # 原实现只更新 containers 表,tasks 行两字段恒空)
    await db.execute(
        update(Task)
        .where(Task.task_id == task_id, Task.status == "running")
        .values(container_id=container.container_id, runner_id=container.runner_id)
    )
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

    # F2.a:通知 request_stop 等待协程(超时机制已不再需要)
    stop_event = _pending_stop_events.get(docker_container_id)
    if stop_event is not None:
        stop_event.set()

    # R10:容器销毁 → 摘除预览路由(URL 失效)
    from app.services import route_service

    await route_service.remove_routes_for_container(db, container.container_id)

    # 调度占用:-1(DB + 内存)
    await runner_service.adjust_container_count(db, container.runner_id, -1)
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
        # 调度占用释放(die→failed 不再占用;重启场景由 Runner 重新回报 started 补偿)
        await runner_service.adjust_container_count(db, container.runner_id, -1)
    await db.flush()


# ---------------------------------------------------------------------------
# F2.b: Runner 离线补发 stop(Runner 重连时调用)
# ---------------------------------------------------------------------------
async def resend_stop_for_offline_containers(db: AsyncSession, runner_id: str) -> None:
    """
    F2.b: Runner 重连后,对该 Runner 上 status=stopped 且 destroyed_at IS NULL 的容器补发 stop。
    原 request_stop 在 Runner 离线时只标 stopped 不销毁,Runner 恢复后需补发 stop_container。
    """
    result = await db.execute(
        select(Container).where(
            Container.runner_id == runner_id,
            Container.status == "stopped",
            Container.destroyed_at.is_(None),
        )
    )
    containers = result.scalars().all()
    if not containers:
        return

    conn = runner_registry.get(runner_id)
    if conn is None:
        logger.warning("Runner 重连但连接不在,无法补发 stop runner=%s", runner_id)
        return

    for container in containers:
        await runner_service.send_to_runner(
            conn, runner_service.build_stop_container_message(container.container_id)
        )
        logger.info("Runner 重连补发 stop_container container=%s", container.container_id)


# ---------------------------------------------------------------------------
# F2.d: 启动时孤儿对账(lifespan 调用)
# ---------------------------------------------------------------------------
async def inspect_container_docker(container_id: str) -> Optional[dict]:
    """
    检查 docker 真实状态(经 Runner 或本机 docker SDK)。
    返回约定:
      - None: 未知(inspect 调用失败/超时/未实现) → 调用方应 fail-safe 跳过,绝不置 destroyed
      - {"exists": False}: 明确证据表明 docker 侧不存在 → 可安全置 destroyed
      - {"exists": True, "status": "running"/"exited"/...}: docker 侧存在
    当前实现:占位函数(返回 None = 未知),测试时 mock;生产环境需经 Runner WebSocket 查询 docker inspect。
    """
    # TODO: 生产实现需经 Runner WebSocket 发 docker_inspect 指令,返回 {"exists": True/False, ...}
    return None


async def reconcile_orphan_containers(db: AsyncSession) -> None:
    """
    F2.d: 启动时一次性孤儿对账(fail-safe + 并发补发)。
    扫描 containers.status IN (running, creating):
    - inspect 返回 {"exists": False}(明确不存在证据) → 置 destroyed
    - 否则(exists=True 或 inspect 无结论):若对应 task 已终态 → 后台并发补发 stop(不阻塞 lifespan)
    - inspect 无结论不阻断补发(状态收敛交给 F2.a 超时兜底)
    """
    result = await db.execute(
        select(Container).where(
            Container.status.in_(["running", "creating"])
        )
    )
    containers = result.scalars().all()
    if not containers:
        return

    from app.models.task import Task

    dispatched = 0
    for container in containers:
        # 检查 docker 真实状态
        try:
            docker_state = await inspect_container_docker(container.container_id)
        except Exception as e:
            # inspect 异常 → 视为未知,不阻断后续补发逻辑
            logger.warning(
                "孤儿对账:inspect 异常(视为未知) container=%s: %s",
                container.container_id, e
            )
            docker_state = None

        # 明确证据:docker 侧不存在 → 安全置 destroyed
        if docker_state is not None and not docker_state.get("exists", True):
            container.status = "destroyed"
            container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            logger.info("孤儿对账:docker 明确无此容器,置 destroyed container=%s", container.container_id)
            continue

        # 否则(exists=True 或 inspect 无结论):检查 task 是否已终态 → 补发 stop
        if container.task_id:
            task_result = await db.execute(
                select(Task).where(Task.task_id == container.task_id).limit(1)
            )
            task = task_result.scalar_one_or_none()
            if task is not None and task.status in ("done", "cancelled", "timeout", "failed"):
                # task 已终态但容器还在 → 后台并发补发 stop(不阻塞 lifespan)
                asyncio.create_task(_dispatch_stop_in_background(container.container_id))
                dispatched += 1
                logger.info(
                    "孤儿对账:task 已终态,派发补发 stop(后台) container=%s task=%s",
                    container.container_id, container.task_id
                )

    if dispatched > 0:
        logger.info("孤儿对账:已派发 %d 条补发 stop(后台执行)", dispatched)

    await db.flush()


async def _dispatch_stop_in_background(container_id: str) -> None:
    """
    后台补发 stop:独立 db session,避免阻塞 lifespan 启动。
    由 reconcile_orphan_containers 调用,并发执行;DB 置 destroyed 由 F2.a 超时回调完成。
    """
    from app.database import async_session_factory

    try:
        async with async_session_factory() as db:
            # 重新查询容器(避免跨 session 使用 detached 对象)
            result = await db.execute(
                select(Container).where(Container.container_id == container_id)
            )
            container = result.scalar_one_or_none()
            if container is None:
                logger.warning("后台补发 stop:容器不存在 container=%s", container_id)
                return
            await request_stop(db, container)
            await db.commit()
            logger.info("后台补发 stop 完成 container=%s", container_id)
    except Exception as e:
        logger.warning("后台补发 stop 失败 container=%s: %s", container_id, e)
