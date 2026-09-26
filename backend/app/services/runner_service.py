"""Runner 服务 - R8/R16(WebSocket 传输层 + DB 注册表 + 注册/心跳/对账)

分层:
- 传输层(内存):RunnerConnection / runner_registry —— WebSocket 连接 ↔ runner_id,
  仅作消息下发通道;进程重启即空(Runner 断线自动重连)
- 注册表(DB):runners 表 —— token/bcrypt、心跳、容器数、状态;调度与管理的唯一事实源

协议(D13/R8/R16):
  平台→Runner: start_container / stop_container / register_ack / register_success
  Runner→平台: register(token+machine_info) / heartbeat(timestamp) / sync(containers)
               / container_started / container_stopped / container_event
"""

import asyncio
import logging
import random
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.core.security import hash_password, verify_password
from app.models.container import Container
from app.models.task import Task
from app.models.runner import Runner

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "plt-runner-"
HEARTBEAT_OFFLINE_SECONDS = 60      # 60s 无心跳 → offline
HEARTBEAT_DRIFT_REJECT = 300        # 时钟漂移 > 5min 拒绝心跳(防重放)
HEARTBEAT_DRIFT_TOLERANCE = 30      # 平台容忍 ±30s 时钟差


# ---------------------------------------------------------------------------
# 传输层(内存连接表;R8 引入,R16 保留作下发通道)
# ---------------------------------------------------------------------------
@dataclass
class RunnerConnection:
    """一条已连接的 Runner"""
    runner_id: str
    role: str = "worker"
    websocket: Optional[WebSocket] = None
    host: str = ""
    load: int = 0
    last_heartbeat_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RunnerRegistry:
    """内存连接注册表(传输层)"""

    def __init__(self) -> None:
        self._runners: dict[str, RunnerConnection] = {}

    def register(self, runner_id: str, role: str, websocket: Optional[WebSocket], host: str) -> RunnerConnection:
        conn = RunnerConnection(runner_id=runner_id, role=role, websocket=websocket, host=host)
        self._runners[runner_id] = conn
        logger.info("Runner 连接注册 runner=%s role=%s host=%s", runner_id, role, host)
        return conn

    def unregister(self, runner_id: str) -> None:
        if runner_id in self._runners:
            logger.info("Runner 连接注销 runner=%s", runner_id)
            del self._runners[runner_id]

    def get(self, runner_id: str) -> Optional[RunnerConnection]:
        return self._runners.get(runner_id)

    def list_online(self) -> list[RunnerConnection]:
        return list(self._runners.values())


runner_registry = RunnerRegistry()


async def send_to_runner(conn: RunnerConnection, message: dict) -> None:
    """平台 → Runner 下发 JSON 消息(并发安全)"""
    if conn.websocket is None:
        raise RuntimeError(f"Runner {conn.runner_id} websocket 未连接")
    async with conn.lock:
        await conn.websocket.send_json(message)


# ---------------------------------------------------------------------------
# 消息构造(R8)
# ---------------------------------------------------------------------------
def build_start_container_message(
    task_id: str,
    image: str,
    env: dict,
    ports: list[int],
    repos: list[dict],
    cpu_limit: str = "2c",
    mem_limit: str = "4g",
    disk_limit: str = "10g",
) -> dict:
    return {
        "type": "start_container",
        "task_id": task_id,
        "image": image,
        "env": env,
        "ports": ports,
        "cpu_limit": cpu_limit,
        "mem_limit": mem_limit,
        "disk_limit": disk_limit,
        "repos": repos,
    }


def build_stop_container_message(container_id: str) -> dict:
    return {"type": "stop_container", "container_id": container_id}


# ---------------------------------------------------------------------------
# 请求-响应关联(R11 文件操作等需要回值的指令)
# Runner 收到带 req_id 的消息,执行后回报 {"type":"result","req_id","ok","data"};
# 平台侧 pending Future 表在此结算。
# ---------------------------------------------------------------------------
_pending_requests: dict[str, asyncio.Future] = {}
# R32.F3:流式请求注册表(req_id → {task_id, queue})——claude_stream 事件按 req_id 路由
_stream_requests: dict[str, dict] = {}


async def request_runner(conn: RunnerConnection, message: dict, timeout: float = 15.0) -> dict:
    """下发指令并等待 Runner 结果(超时抛 TimeoutError)"""
    req_id = uuid.uuid4().hex
    message = {**message, "req_id": req_id}
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _pending_requests[req_id] = fut
    try:
        # 死连接上 send_json 常"静默成功"(TCP 本地缓冲),future 永不结算 → 调用方
        # 等满 timeout(对话 600s)→ 用户"发送中"卡 10 分钟(BUG-032)。send 阶段
        # 任何异常立即转 TimeoutError,复用调用方既有超时处理,秒级暴露
        try:
            await send_to_runner(conn, message)
        except Exception as e:
            raise TimeoutError(f"Runner 连接不可用: {e}") from e
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            # py3.10 上 asyncio.TimeoutError 与内建 TimeoutError 是两个类,
            # 调用方 `except TimeoutError` 接不住 → 裸奔成 500(BUG-033 实证);
            # 这里统一归一化为内建 TimeoutError
            raise TimeoutError("Runner 响应超时") from None
    finally:
        _pending_requests.pop(req_id, None)


def resolve_request(req_id: str, ok: bool, data=None, error: str = "") -> bool:
    """Runner 回报结算 pending Future(无匹配 req_id 返回 False)"""
    fut = _pending_requests.get(req_id)
    if fut is None or fut.done():
        return False
    if ok:
        fut.set_result({"ok": True, "data": data})
    else:
        fut.set_result({"ok": False, "error": error, "data": None})
    return True


# ---------------------------------------------------------------------------
# R32.F3:流式对话请求(request_runner 的流式变体)
# ---------------------------------------------------------------------------
async def request_runner_stream(
    conn: RunnerConnection, message: dict, timeout: float = 600.0
) -> tuple[str, "asyncio.Queue"]:
    """
    下发流式指令:返回 (req_id, queue)。Runner 的每条 claude_stream 事件
    由 route_stream_event 投入 queue;终态由 resolve_stream_request(同样吃
    result 回报)投 {"type":"done", ok, data|error} 并注销。调用方消费队列直到 done。
    """
    req_id = uuid.uuid4().hex
    message = {**message, "req_id": req_id}
    queue: asyncio.Queue = asyncio.Queue()
    _stream_requests[req_id] = {"task_id": message.get("task_id", ""), "queue": queue}
    try:
        await send_to_runner(conn, message)
    except Exception as e:
        _stream_requests.pop(req_id, None)
        raise TimeoutError(f"Runner 连接不可用: {e}") from e

    async def _timeout_guard() -> None:
        await asyncio.sleep(timeout)
        if req_id in _stream_requests:
            resolve_stream_request(req_id, False, error="Runner 响应超时")

    asyncio.get_running_loop().create_task(_timeout_guard())
    return req_id, queue


def route_stream_event(req_id: str, line: str) -> bool:
    """Runner claude_stream 事件路由(无匹配 req_id 返回 False)"""
    entry = _stream_requests.get(req_id)
    if entry is None:
        return False
    entry["queue"].put_nowait({"type": "stream", "line": line})
    return True


def resolve_stream_request(req_id: str, ok: bool, data=None, error: str = "") -> bool:
    """流式请求终态结算:投 done 事件并注销(result 回报与 stream 共用 req_id)"""
    entry = _stream_requests.pop(req_id, None)
    if entry is None:
        return False
    entry["queue"].put_nowait({"type": "done", "ok": ok, "data": data, "error": error})
    return True


# ---------------------------------------------------------------------------
# R16:Runner 管理(超管)
# ---------------------------------------------------------------------------
def _generate_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_hex(16)}"


async def create_runner(
    db: AsyncSession, operator_user_id: str,
    name: str, role: str, max_containers: int = 10, public_ip: Optional[str] = None,
) -> tuple[Runner, str]:
    """
    超管创建 Runner 并生成一次性 token(仅创建响应显示一次,平台只存 bcrypt hash)。
    deploy 角色必须提供 public_ip(部署 URL 指向)。
    """
    dup = await db.execute(select(Runner.id).where(Runner.name == name).limit(1))
    if dup.scalar_one_or_none() is not None:
        raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, "同名 Runner 已存在")
    if role == "deploy" and not public_ip:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, "deploy 角色必须填写公网 IP")

    token = _generate_token()
    runner = Runner(
        name=name,
        role=role,
        token_hash=hash_password(token),
        max_containers=max_containers,
        public_ip=public_ip,
        created_by=operator_user_id,
        status="offline",
    )
    db.add(runner)
    await db.flush()
    await db.refresh(runner)
    logger.info("Runner 创建 name=%s role=%s by=%s", name, role, operator_user_id)
    return runner, token


async def get_runner_or_404(db: AsyncSession, runner_id: str) -> Runner:
    result = await db.execute(select(Runner).where(Runner.runner_id == runner_id))
    runner = result.scalar_one_or_none()
    if runner is None:
        raise BizError(404, "Runner 不存在", status_code=404)
    return runner


async def reset_token(db: AsyncSession, runner_id: str) -> str:
    """重置 token:换 hash → 旧 token 失效(旧连接由平台主动断开)"""
    runner = await get_runner_or_404(db, runner_id)
    token = _generate_token()
    runner.token_hash = hash_password(token)
    await db.flush()
    logger.info("Runner token 重置 runner=%s", runner_id)

    # 踢掉旧连接(旧 token 的 Runner 需用新 token 重启)
    conn = runner_registry.get(runner_id)
    if conn is not None and conn.websocket is not None:
        try:
            await conn.websocket.close(code=4003)
        except Exception:
            pass
        runner_registry.unregister(runner_id)
    return token


async def disable_runner(db: AsyncSession, runner_id: str) -> None:
    """禁用 Runner:不再调度新任务(status=disabled);断开连接"""
    runner = await get_runner_or_404(db, runner_id)
    runner.status = "disabled"
    await db.flush()
    conn = runner_registry.get(runner_id)
    if conn is not None and conn.websocket is not None:
        try:
            await conn.websocket.close(code=4004)
        except Exception:
            pass
        runner_registry.unregister(runner_id)
    logger.info("Runner 已禁用 runner=%s", runner_id)


async def delete_runner(db: AsyncSession, runner_id: str) -> None:
    """删除 Runner:有运行中容器且关联任务仍进行中(running)→ 16001(R16.F3/BUG-042 收窄:
    任务非 running(取消/完成)的容器行不再拦截;task_id 为空的部署容器放行)"""
    runner = await get_runner_or_404(db, runner_id)
    cnt = await db.execute(
        select(func.count(Container.id))
        .join(Task, Task.task_id == Container.task_id)
        .where(
            Container.runner_id == runner_id,
            Container.status.in_(["creating", "running"]),
            Task.status == "running",
        )
    )
    if (cnt.scalar() or 0) > 0:
        raise BizError(ErrCode.RUNNER_HAS_CONTAINERS, "Runner 上有进行中任务的容器,不可删除")

    conn = runner_registry.get(runner_id)
    if conn is not None and conn.websocket is not None:
        try:
            await conn.websocket.close(code=4005)
        except Exception:
            pass
        runner_registry.unregister(runner_id)

    await db.delete(runner)
    await db.flush()
    logger.info("Runner 已删除 runner=%s", runner_id)


# ---------------------------------------------------------------------------
# R16:注册 / 心跳 / offline 判定 / 对账
# ---------------------------------------------------------------------------
async def handle_register(db: AsyncSession, token: str, machine_info: Optional[dict]) -> Optional[Runner]:
    """
    Runner 注册:token 与 runners.token_hash 逐一 bcrypt 比对(Runner 数量小;
    token 不内嵌 id,防信息泄露)。disabled 拒绝。
    成功 → status=online + machine_info + 心跳时间;返回 Runner;失败返回 None。
    """
    if not token:
        return None
    result = await db.execute(select(Runner).where(Runner.status != "disabled"))
    for runner in result.scalars():
        if verify_password(token, runner.token_hash):
            runner.status = "online"
            runner.last_heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if machine_info:
                runner.machine_info = machine_info
            await db.flush()
            logger.info("Runner 注册上线 runner=%s(%s)", runner.name, runner.runner_id)
            return runner
    logger.warning("Runner 注册失败:token 无匹配")
    return None


async def handle_heartbeat(db: AsyncSession, runner: Runner, timestamp: Optional[float]) -> bool:
    """
    心跳:更新 last_heartbeat_at。
    时钟漂移 > 5min → 拒绝(返回 False,调用方关闭连接);±30s 容忍。
    """
    now = datetime.now(timezone.utc)
    if timestamp is not None:
        drift = abs(now.timestamp() - float(timestamp))
        if drift > HEARTBEAT_DRIFT_REJECT:
            logger.warning("Runner 心跳时钟漂移过大 runner=%s drift=%.0fs", runner.runner_id, drift)
            return False
    runner.last_heartbeat_at = now.replace(tzinfo=None)
    await db.flush()
    return True


async def sweep_offline(db: AsyncSession) -> int:
    """
    offline 判定(平台定时任务每 60s 调):last_heartbeat_at 超 60s → offline。
    Runner 上的容器继续跑(Runner 是薄代理)。
    """
    threshold = (datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_OFFLINE_SECONDS)).replace(tzinfo=None)
    result = await db.execute(
        select(Runner).where(
            Runner.status == "online",
            Runner.last_heartbeat_at.isnot(None),
            Runner.last_heartbeat_at < threshold,
        )
    )
    count = 0
    for runner in result.scalars():
        runner.status = "offline"
        count += 1
        runner_registry.unregister(runner.runner_id)
        logger.info("Runner 心跳超时 → offline runner=%s", runner.runner_id)
    if count:
        await db.flush()
        # R25 审计:系统事件(占位全零 user_id + role=system,detail 带 reason;不记 ip)
        from app.database import async_session_factory
        from app.services.audit_service import spawn_audit_write

        spawn_audit_write(
            async_session_factory,
            {"user_id": "00000000-0000-0000-0000-000000000000", "role": "system"},
            "runner.offline_sweep",
            detail={"reason": "heartbeat_timeout_sweep", "count": count},
        )
    return count


async def handle_sync(db: AsyncSession, runner: Runner, reported: list[dict]) -> None:
    """
    Runner 恢复后对账(以 Runner 上报为准):
    - DB 有(creating/running)但上报没有 → destroyed
    - 状态不一致 → 以上报为准(running/stopped)
    - 上报有但 DB 没有 → 记日志(理论不应发生)
    """
    result = await db.execute(
        select(Container).where(
            Container.runner_id == runner.runner_id,
            Container.status.in_(["creating", "running", "stopped"]),
        )
    )
    db_containers = {c.container_id: c for c in result.scalars().all()}
    reported_map = {r.get("container_id"): r.get("status", "running") for r in reported}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for container_id, container in db_containers.items():
        if container_id not in reported_map:
            container.status = "destroyed"
            container.destroyed_at = now
        elif container.status != reported_map[container_id]:
            container.status = reported_map[container_id]
    missing = [cid for cid in reported_map if cid not in db_containers]
    if missing:
        logger.warning("对账发现未知容器(忽略) runner=%s %s", runner.runner_id, missing)

    # 同步 current_containers(只数 running/creating)
    runner.current_containers = sum(
        1 for cid, st in reported_map.items() if st in ("running", "creating") and cid in db_containers
    )
    await db.flush()
    logger.info("Runner 状态对账完成 runner=%s db=%d reported=%d", runner.runner_id, len(db_containers), len(reported_map))


# ---------------------------------------------------------------------------
# R16:DB 调度器(container_service 消费)
# ---------------------------------------------------------------------------
async def pick_runner_db(db: AsyncSession, required_role: str = "worker") -> Optional[Runner]:
    """
    任务调度:status=online AND current_containers < max_containers AND role 匹配,
    current_containers 最少;并列时按随机(ORDER BY 随机成本高,取前 5 随机选)。
    角色:worker → role=worker;deploy → role=deploy。
    """
    role = "deploy" if required_role == "deploy" else "worker"
    result = await db.execute(
        select(Runner)
        .where(
            Runner.status == "online",
            Runner.role == role,
            Runner.current_containers < Runner.max_containers,
        )
        .order_by(Runner.current_containers.asc(), Runner.id.asc())
        .limit(5)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return None
    min_load = candidates[0].current_containers
    least = [r for r in candidates if r.current_containers == min_load]
    return random.choice(least)


async def adjust_container_count(db: AsyncSession, runner_id: str, delta: int) -> None:
    """current_containers ±delta(started +1 / stopped -1,下限 0)"""
    result = await db.execute(select(Runner).where(Runner.runner_id == runner_id))
    runner = result.scalar_one_or_none()
    if runner is None:
        return
    runner.current_containers = max(0, (runner.current_containers or 0) + delta)
    await db.flush()
