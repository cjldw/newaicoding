"""R31 本机 Runner 快速创建与生命周期服务

平台在**本机**启动 runner(注入 token/地址),并提供指令式停止(WS runner_shutdown)、
删除代停(先停容器=强制 push 链)编排。

启动形态(R31.F3/BUG-049,用户指令修正):**Docker 容器形态**——镜像 platform/runner:v1
缺失时自动构建(docker/runner/Dockerfile,源码即所得),`docker run -d` 挂载 docker.sock、
env 四键注入,容器内经 host.docker.internal 回连平台;用户零命令复制。
旧「python 子进程」句柄路径仅作存量兼容(不再新启)。

安全边界(分片"响应最小化"):
- token 明文只进容器环境,不落库/不进日志/不进响应;
- 容器名由 runner_id 确定性推出(qicheng-runner-<id前8>),平台重启后仍可凭名停止,无盲杀;
- V1 单机单管理员信任模型(挂载 docker.sock 等价宿主 docker 权限)。
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.runner import Runner

logger = logging.getLogger(__name__)

# 仓库根:backend/app/services/xxx.py → parents = [services, app, backend, 仓库根] → [3]
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_MAIN = REPO_ROOT / "runner" / "main.py"
RUNNER_DIR = REPO_ROOT / "runner"
LOG_DIR = REPO_ROOT / "data" / "logs"

# 平台 WS 地址:子进程形态遗留常量(容器形态从容器内回连——容器内 127.0.0.1 是容器自身)
PLATFORM_URL_DEFAULT = "ws://127.0.0.1:8000/ws/runner"
# R31.F3(BUG-049):容器形态常量
PLATFORM_URL_CONTAINER = "ws://host.docker.internal:8000/ws/runner"
RUNNER_IMAGE = "platform/runner:v1"
RUNNER_DOCKERFILE = REPO_ROOT / "docker" / "runner" / "Dockerfile"
IMAGE_BUILD_TIMEOUT = 600.0              # 首次镜像构建预算(pip install 数分钟,缓存后秒级)
DOCKER_STOP_TIMEOUT = 10                 # docker stop 优雅退出秒数

LOCAL_RUNNER_MAX = 3                     # 本机快速创建上限(固定值,不入平台设置)
REGISTER_WAIT_TIMEOUT = 10.0             # 注册等待
REGISTER_WAIT_INTERVAL = 0.5
SHUTDOWN_CMD_TIMEOUT = 5.0               # 停止指令等待
CONTAINER_STOP_TIMEOUT = 30.0            # 单容器停止等待
DELETE_BUDGET = 60.0                     # 删除代停整体预算
_PROBE_TIMEOUT = 5.0

# runner_id → Popen 句柄(内存态,平台重启清空;存量子进程形态兼容用,不再新启)
_local_processes: dict[str, "subprocess.Popen"] = {}
# R31.F3:runner_id → 容器名(名字可由 id 确定性推出,登记仅为语义清晰)
_local_containers: dict[str, str] = {}


def _container_name(runner_id: str) -> str:
    """容器名确定性推出:平台重启后仍可凭名 stop/rm(替代子进程形态的 PID 句柄,无盲杀)"""
    return f"qicheng-runner-{runner_id[:8]}"
# per-runner_id in-flight 锁(start/restart 防连点)
_inflight: set[str] = set()


class PreflightError(Exception):
    """内部:preflight 失败携带 sub 标识(仅日志/审计 detail,不进 message)"""

    def __init__(self, sub: str, message: str):
        self.sub = sub
        self.message = message
        super().__init__(message)


def _err(code: int, message: str) -> BizError:
    return BizError(code, message)


async def preflight() -> None:
    """
    环境四项校验(点击时,失败抛 BizError(16002, 细分文案)):
    1. runner 代码存在(平台源码方式部署)
    2. runner 依赖可 import(用子进程探测,避免污染平台进程)
    3. 本机 Docker daemon 可用
    (上限 16003 需要 DB,由调用端点先行检查)
    """
    if not RUNNER_MAIN.is_file():
        raise _err(
            ErrCode.RUNNER_LOCAL_ENV,
            "当前部署未包含 Runner 代码(runner/main.py),快速创建仅支持平台源码方式部署",
        )

    # 依赖探测:一次性子进程 import(runner 的依赖,平台进程本身不装也无妨)
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-c", "import docker, websockets"],
            capture_output=True, timeout=_PROBE_TIMEOUT,
            cwd=str(RUNNER_DIR),
        )
        if proc.returncode != 0:
            raise _err(
                ErrCode.RUNNER_LOCAL_ENV,
                "Runner 依赖未安装,请在平台运行环境执行 pip install -r runner/requirements.txt",
            )
    except subprocess.TimeoutExpired:
        raise _err(
            ErrCode.RUNNER_LOCAL_ENV,
            "Runner 依赖未安装,请在平台运行环境执行 pip install -r runner/requirements.txt",
        )

    # Docker 可用性(带 daemon ping)
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-c", "import docker; docker.from_env().ping()"],
            capture_output=True, timeout=_PROBE_TIMEOUT,
            cwd=str(RUNNER_DIR),
        )
        if proc.returncode != 0:
            raise _err(ErrCode.RUNNER_LOCAL_ENV, "本机 Docker 不可用,请先启动 Docker 后重试")
    except subprocess.TimeoutExpired:
        raise _err(ErrCode.RUNNER_LOCAL_ENV, "本机 Docker 不可用,请先启动 Docker 后重试")


async def check_local_limit(db: AsyncSession) -> None:
    """本机快速创建 runner 上限(16003)"""
    cnt = (await db.execute(
        select(func.count(Runner.id)).where(Runner.is_local == 1)
    )).scalar() or 0
    if cnt >= LOCAL_RUNNER_MAX:
        raise _err(ErrCode.RUNNER_LOCAL_LIMIT, "本机快速创建的 Runner 已达上限(3 个),请先删除闲置 Runner")


async def check_name_free(db: AsyncSession, name: str) -> None:
    """名称冲突显式校验(16005;原远程创建端点不改,分片决策 A1)"""
    dup = await db.execute(select(Runner.id).where(Runner.name == name).limit(1))
    if dup.scalar_one_or_none() is not None:
        raise _err(ErrCode.RUNNER_NAME_EXISTS, "Runner 名称已存在,请更换")


def _reap(handle: "subprocess.Popen", wait: float = 3.0) -> None:
    """terminate → 短等待 → kill 兜底(仅对平台持有的句柄)"""
    try:
        handle.terminate()
        handle.wait(timeout=wait)
    except Exception:
        try:
            handle.kill()
        except Exception:
            pass


async def _stop_container_by_name(name: str, remove: bool = False) -> bool:
    """docker stop(可选 rm);容器不存在返回 False(调用方决定降级路径)"""
    import docker as docker_sdk

    def _sync() -> bool:
        client = docker_sdk.from_env()
        try:
            container = client.containers.get(name)
        except docker_sdk.errors.NotFound:
            return False
        container.stop(timeout=DOCKER_STOP_TIMEOUT)
        if remove:
            container.remove(force=True)
        return True

    try:
        return await asyncio.to_thread(_sync)
    except Exception:
        logger.exception("本机 runner 容器停止失败 name=%s", name)
        return False


async def remove_local_container(runner_id: str) -> None:
    """删除链路收尾:移除本机 runner 容器(不存在则忽略;R31.F3)"""
    await _stop_container_by_name(_container_name(runner_id), remove=True)
    _local_containers.pop(runner_id, None)


async def _ensure_image() -> None:
    """镜像存在性检查,缺失自动构建(docker CLI,与 DEPLOY.md §4 同参数;零命令复制)。
    基础镜像自适应(Docker Hub 不可达环境,如国内网络):本地无 python:3.12-slim
    但有 python:3.10 时,用 --build-arg BASE_IMAGE=python:3.10 回退(Dockerfile 已参数化);
    pypi 直连可达(R8.F1 devbox 构建实证)"""
    import docker as docker_sdk

    def _sync() -> None:
        client = docker_sdk.from_env()
        try:
            client.images.get(RUNNER_IMAGE)
            return  # 镜像已就绪(首次构建后缓存,后续秒级)
        except docker_sdk.errors.ImageNotFound:
            pass
        cmd = ["docker", "build", "-t", RUNNER_IMAGE, "-f", str(RUNNER_DOCKERFILE), str(RUNNER_DIR)]
        # 基础镜像回退:默认 base 本地不存在且 3.10 在本地 → 用 3.10(免外网拉取)
        try:
            client.images.get("python:3.12-slim")
        except docker_sdk.errors.ImageNotFound:
            try:
                client.images.get("python:3.10")
                cmd += ["--build-arg", "BASE_IMAGE=python:3.10"]
                logger.info("基础镜像 python:3.12-slim 本地不存在,回退 python:3.10 构建 runner 镜像")
            except docker_sdk.errors.ImageNotFound:
                pass  # 两者皆无 → 保持默认,让构建报出真实的拉取错误
        proc = subprocess.run(cmd, capture_output=True, timeout=IMAGE_BUILD_TIMEOUT)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or b"").decode(errors="replace")[-200:]
            raise _err(ErrCode.RUNNER_LOCAL_ENV, f"Runner 镜像构建失败({RUNNER_IMAGE}):{tail}")
        client.images.get(RUNNER_IMAGE)  # 构建后确认可见

    await asyncio.to_thread(_sync)


async def spawn_local(runner: Runner, token_plain: str) -> dict:
    """
    以 Docker 容器启动本机 runner(R31.F3/BUG-049,用户指令:本机=直接跑 Docker 容器、
    不再复制命令;旧 python 子进程形态废弃不再新启):
    镜像缺失自动构建 → `docker run -d` 挂载 docker.sock(管理本机任务容器)、
    env 四键注入(token 明文只进容器环境),容器内经 host.docker.internal 回连平台。
    返回 launch 元信息(env_keys 不含值);启动失败 → 16002 细分文案;
    容器秒退场景由 wait_online 超时语义兜底(记录保留,可排障/重启)。
    """
    await _ensure_image()

    import docker as docker_sdk

    name = _container_name(runner.runner_id)

    def _run_sync() -> str:
        client = docker_sdk.from_env()
        try:  # 同名残留容器(上次异常未清)先移除,保证名字可复用
            client.containers.get(name).remove(force=True)
        except docker_sdk.errors.NotFound:
            pass
        container = client.containers.run(
            RUNNER_IMAGE,
            detach=True,
            name=name,
            restart_policy={"Name": "unless-stopped"},
            environment={
                "PLATFORM_URL": PLATFORM_URL_CONTAINER,
                "RUNNER_TOKEN": token_plain,
                "RUNNER_ROLE": "worker",
                "RUNNER_ID": runner.runner_id,
            },
            mounts=[docker_sdk.types.Mount(
                "/var/run/docker.sock", "/var/run/docker.sock", type="bind",
            )],
            extra_hosts={"host.docker.internal": "host-gateway"},
        )
        return container.short_id

    logger.info("spawn 本机 runner(容器形态)id=%s name=%s container=%s", runner.runner_id, runner.name, name)
    try:
        container_id = await asyncio.to_thread(_run_sync)
    except BizError:
        raise
    except Exception as e:
        raise _err(ErrCode.RUNNER_LOCAL_ENV, f"Runner 容器启动失败:{str(e)[:120]}")

    _local_containers[runner.runner_id] = name
    return {
        "argv": ["docker", "run", "-d", "--name", name, RUNNER_IMAGE],
        "env_keys": ["PLATFORM_URL", "RUNNER_TOKEN", "RUNNER_ROLE", "RUNNER_ID"],
        "image": RUNNER_IMAGE,
        "container_name": name,
        "container_id": container_id,
    }


async def wait_online(db: AsyncSession, runner_id: str, timeout: float = REGISTER_WAIT_TIMEOUT) -> str:
    """轮询注册结果:registry 命中或 DB status=online → 'online';超时 → 'offline'(不回滚)"""
    import time as _t

    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        # 注册链接由 runner_ws 建立(runner_registry 命中即注册成功)
        from app.services.runner_service import runner_registry

        conn = runner_registry.get(runner_id)
        if conn is not None and conn.websocket is not None:
            return "online"
        await asyncio.sleep(REGISTER_WAIT_INTERVAL)
    # 兜底再查一次 DB(连接可能刚建立尚未入注册表)
    row = (await db.execute(select(Runner.status).where(Runner.runner_id == runner_id))).scalar_one_or_none()
    return "online" if row == "online" else "offline"


async def shutdown_local(runner: Runner) -> None:
    """
    指令式停止(Q55):
    1. online(或注册表有连接)→ WS 下发 runner_shutdown(5s);
    2. 指令失败/无连接 → 有内存句柄则 terminate 强杀;
    3. 无连接且无句柄:status=online → 16007(平台重启后孤儿,需手动处理);
       其余(offline/disabled)→ 视为已停止,no-op。
    """
    from app.services import runner_service

    conn = runner_service.runner_registry.get(runner.runner_id)
    if runner.status == "online":
        # 库标 online 即尝试指令(注册表无连接=库位滞后/半死,下发会在 send 阶段抛错转下降级)
        try:
            res = await runner_service.request_runner(
                conn, {"type": "runner_shutdown"}, timeout=SHUTDOWN_CMD_TIMEOUT,
            )
            logger.info("runner_shutdown 已回执 runner=%s ok=%s", runner.runner_id, res.get("ok"))
        except Exception as e:  # 含 TimeoutError(request_runner 归一化)
            logger.warning("runner_shutdown 指令失败,降级句柄强杀 runner=%s: %s", runner.runner_id, e)
        else:
            # 指令生效后 runner 自行退出;句柄存在则回收(容错:旧版 runner 不退 → 强杀)
            handle = _local_processes.get(runner.runner_id)
            if handle is not None and handle.poll() is None:
                try:
                    await asyncio.to_thread(handle.wait, SHUTDOWN_CMD_TIMEOUT)
                except Exception:
                    pass
                if handle.poll() is None:
                    logger.warning("runner 收指令后未退出,强杀句柄 runner=%s", runner.runner_id)
                    _reap(handle)
            _local_processes.pop(runner.runner_id, None)
            return

    handle = _local_processes.pop(runner.runner_id, None)
    if handle is not None:
        _reap(handle)
        return
    # R31.F3:容器形态——凭确定性容器名 docker stop(平台重启后依旧可用,替代 PID 句柄)
    if await _stop_container_by_name(_container_name(runner.runner_id)):
        _local_containers.pop(runner.runner_id, None)
        return
    if runner.status == "online":
        raise _err(
            ErrCode.RUNNER_NO_PROCESS_HANDLE,
            "无法连接该 Runner 进程且无本地句柄(平台重启后),请在任务机手动结束 runner 进程",
        )
    # offline 且无句柄:进程本就不在,视为已停止


async def stop_all_containers_and_wait(db: AsyncSession, runner: Runner, budget: float = DELETE_BUDGET) -> int:
    """
    删除代停(Q56):对该 runner 全部 creating/running 容器下发既有 stop(强制 push 链),
    轮询到 destroyed;单容器 30s、整体 budget;任一失败 → 16004(指明容器短码,记录保留)。
    已 destroyed 容器天然不入快照,重试幂等。
    """
    import time as _t

    from app.services import container_service

    rows = (await db.execute(
        select(Container).where(
            Container.runner_id == runner.runner_id,
            Container.status.in_(["creating", "running"]),
        ).order_by(Container.id.asc())
    )).scalars().all()
    if not rows:
        return 0

    deadline = _t.monotonic() + budget
    logger.info("删除代停开始 runner=%s containers=%d", runner.runner_id, len(rows))
    for container in rows:
        try:
            await container_service.request_stop(db, container)
        except Exception as e:
            raise _err(
                ErrCode.RUNNER_LOCAL_STOP_FAILED,
                f"Runner 上有容器未能停止({container.container_id[:6]}),Runner 已保留,请先处理该容器后重试",
            ) from e
        per_deadline = min(deadline, _t.monotonic() + CONTAINER_STOP_TIMEOUT)
        destroyed = False
        while _t.monotonic() < per_deadline:
            await db.rollback()  # 释放读事务,拿容器回报的新快照
            st = (await db.execute(
                select(Container.status).where(Container.id == container.id)
            )).scalar_one_or_none()
            if st in ("destroyed", "stopped"):
                destroyed = True
                break
            await asyncio.sleep(1.0)
        if not destroyed:
            raise _err(
                ErrCode.RUNNER_LOCAL_STOP_FAILED,
                f"Runner 上有容器未能停止({container.container_id[:6]}),Runner 已保留,请先处理该容器后重试",
            )
    logger.info("删除代停完成 runner=%s", runner.runner_id)
    return len(rows)


def try_acquire(runner_id: str) -> bool:
    """in-flight 锁:拿不到返回 False(调用方按幂等/进行中处理)"""
    if runner_id in _inflight:
        return False
    _inflight.add(runner_id)
    return True


def release(runner_id: str) -> None:
    _inflight.discard(runner_id)
