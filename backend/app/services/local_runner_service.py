"""R31 本机 Runner 快速创建与生命周期服务

平台在**本机** spawn `python runner/main.py` 子进程(注入 token/地址),
并提供指令式停止(WS runner_shutdown)、删除代停(先停容器=强制 push 链)编排。

安全边界(分片"响应最小化"):
- token 明文只进子进程环境,不落库/不进日志/不进响应;
- 进程句柄仅存内存(平台重启自然清空,停止走指令式仍可用;无句柄无连接 → 16007,绝不盲杀 PID);
- V1 单机单管理员信任模型(子进程继承平台环境)。
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

# 平台 WS 地址(单机形态默认;多网卡/非默认端口为已知限制,V2 平台设置项)
PLATFORM_URL_DEFAULT = "ws://127.0.0.1:8000/ws/runner"

LOCAL_RUNNER_MAX = 3                     # 本机快速创建上限(固定值,不入平台设置)
REGISTER_WAIT_TIMEOUT = 10.0             # 注册等待
REGISTER_WAIT_INTERVAL = 0.5
SHUTDOWN_CMD_TIMEOUT = 5.0               # 停止指令等待
CONTAINER_STOP_TIMEOUT = 30.0            # 单容器停止等待
DELETE_BUDGET = 60.0                     # 删除代停整体预算
_PROBE_TIMEOUT = 5.0

# runner_id → Popen 句柄(内存态,平台重启清空)
_local_processes: dict[str, "subprocess.Popen"] = {}
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


async def spawn_local(runner: Runner, token_plain: str) -> dict:
    """
    以子进程方式启动 runner/main.py(注入 env 四键;token 明文只进子进程环境)。
    返回 launch_command 元信息(argv + env 键名,**不含值**)。
    失败(1s 内退出/Popen 抛错)→ BizError(16002, "Runner 启动失败:…")。
    """
    old = _local_processes.pop(runner.runner_id, None)
    if old is not None and old.poll() is None:
        _reap(old)  # 防御:同 id 已有活进程(理论上 start 幂等已拦截)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"runner-{runner.runner_id[:8]}.log"

    env = {
        **os.environ,
        "PLATFORM_URL": PLATFORM_URL_DEFAULT,
        "RUNNER_TOKEN": token_plain,
        "RUNNER_ROLE": "worker",
        "RUNNER_ID": runner.runner_id,
    }
    argv = [sys.executable, str(RUNNER_MAIN)]
    kwargs: dict = {
        "cwd": str(RUNNER_DIR),
        "env": env,
        "stdout": open(log_path, "ab"),  # noqa: SIM115 句柄随进程生命周期,刻意不关
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        # 脱离平台控制台:平台退出/控制台关闭不连带杀掉 runner
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    logger.info("spawn 本机 runner id=%s name=%s log=%s", runner.runner_id, runner.name, log_path)
    try:
        handle = await asyncio.to_thread(subprocess.Popen, argv, **kwargs)
    except Exception as e:
        raise _err(ErrCode.RUNNER_LOCAL_ENV, f"Runner 启动失败:{str(e)[:120]}")

    # 1s 内即退出 = 启动失败(如依赖缺失竞态);之后注册失败走 wait_online 超时语义(记录保留)
    try:
        code = await asyncio.to_thread(handle.wait, 1)
    except Exception:
        code = None
    if code is not None and code != 0:
        raise _err(ErrCode.RUNNER_LOCAL_ENV, f"Runner 启动失败:进程立即退出(code={code}),详见 {log_path.name}")

    _local_processes[runner.runner_id] = handle
    return {
        "argv": argv,
        "env_keys": ["PLATFORM_URL", "RUNNER_TOKEN", "RUNNER_ROLE", "RUNNER_ID"],
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
