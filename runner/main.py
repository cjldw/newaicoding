"""Runner 主进程 - R8/R16(WebSocket 客户端,连接平台)

启动:
    PLATFORM_URL=wss://platform.example.com/ws/runner \
    RUNNER_TOKEN=plt-runner-xxx \
    RUNNER_ID=runner-01 \
    RUNNER_ROLE=worker \
    RUNNER_HOST=1.2.3.4 \
    python3 main.py

协议(R16):
- register:{type, token, machine_info, host} → register_success(runner_id)
- heartbeat:{type, timestamp}(30s;平台 >5min 漂移拒绝、60s 无心跳判 offline)
- sync:连接后上报本地容器列表,平台对账(状态以 Runner 为准)
- start_container / stop_container 指令处理;Docker events 回报
- 断线自动重连(指数退避)
"""

import asyncio
import logging
import os
import platform as py_platform
import time
from typing import Any

import websockets

from container_manager import ContainerManager
from terminal_manager import TerminalManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("runner")

PLATFORM_URL = os.environ.get("PLATFORM_URL", "ws://localhost:8000/ws/runner")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
RUNNER_ID = os.environ.get("RUNNER_ID", "runner-local")       # 仅日志标识;身份由 token 决定
RUNNER_ROLE = os.environ.get("RUNNER_ROLE", "worker")
RUNNER_HOST = os.environ.get("RUNNER_HOST", "")
HEARTBEAT_INTERVAL = 30  # 秒(D13:30s 心跳;平台 60s 未收到判 offline)

manager = ContainerManager()
terminals = TerminalManager()

# 运行中的 repo 清单(停止容器时强制 push 需要;容器 id → repos)
running_repos: dict[str, list[dict]] = {}


def _pty_output_callback(ws: Any):
    """pty 输出回调(读线程上下文)→ 线程安全投递主事件循环 → 转发平台"""

    async def _send(session_id: str, data: str):
        await send(ws, {"type": "terminal_output", "session_id": session_id, "data": data})

    def callback(session_id: str, data: str):
        if _MAIN_LOOP is not None:
            asyncio.run_coroutine_threadsafe(_send(session_id, data), _MAIN_LOOP)

    return callback


_MAIN_LOOP: Any = None  # main() 里赋值(主事件循环,供 pty 线程投递)


def collect_machine_info() -> dict:
    """机器信息(注册上报;docker 版本取不到时留空)"""
    docker_version = ""
    try:
        import docker

        docker_version = docker.from_env().version()["Version"]
    except Exception:
        pass
    try:
        mem_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (AttributeError, ValueError, OSError):
        mem_gb = 0
    return {
        "os": py_platform.system().lower(),
        "arch": py_platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "mem_total_gb": mem_gb,
        "docker_version": docker_version,
    }


def local_container_states() -> list[dict]:
    """本地实际运行的容器列表(恢复对账用)"""
    try:
        containers = manager.client.containers.list(filters={"label": "qicheng.managed=true"})
        return [
            {"container_id": c.short_id, "status": "running" if c.status == "running" else "stopped"}
            for c in containers
        ]
    except Exception:
        logger.exception("读取本地容器列表失败(对账跳过)")
        return []


async def send(ws: Any, payload: dict) -> None:
    import json

    await ws.send(json.dumps(payload, ensure_ascii=False))


async def handle_message(ws: Any, msg: dict) -> None:
    """处理平台指令"""
    mtype = msg.get("type")

    if mtype == "start_container":
        task_id = msg.get("task_id", "")
        try:
            result = manager.start_container(
                task_id=task_id,
                image=msg.get("image", "platform/devbox:v1"),
                env=msg.get("env") or {},
                ports=msg.get("ports") or [5173, 8000],
                repos=msg.get("repos") or [],
                cpu_limit=msg.get("cpu_limit", "2c"),
                mem_limit=msg.get("mem_limit", "4g"),
                disk_limit=msg.get("disk_limit", "10g"),
            )
            running_repos[result["container_id"]] = msg.get("repos") or []
            await send(ws, {
                "type": "container_started",
                "task_id": task_id,
                "container_id": result["container_id"],
                "ports": result["ports"],
            })
        except Exception as e:
            logger.exception("start_container 失败 task=%s", task_id)
            await send(ws, {"type": "container_event", "event": "start_failed", "task_id": task_id, "error": str(e)})

    elif mtype == "stop_container":
        container_id = msg.get("container_id", "")
        repos = running_repos.pop(container_id, [])
        push_ok = manager.stop_container(container_id, force_push=True, repos=repos)
        if push_ok:
            await send(ws, {"type": "container_stopped", "container_id": container_id})
        else:
            # push 失败:容器保留 30 分钟,平台重试(分片异常场景)
            await send(ws, {"type": "container_event", "event": "push_failed_keepalive", "container_id": container_id})

    elif mtype == "exec":
        # R9 终端:docker exec 新 pty(session 复用 = attach)
        session_id = msg.get("session_id", "")
        created = terminals.create_pty(
            container_id=msg.get("container_id", ""),
            cmd=msg.get("cmd") or ["/bin/bash"],
            session_id=session_id,
            on_output=_pty_output_callback(ws),
        )
        await send(ws, {"type": "exec_started", "session_id": session_id, "created": created})

    elif mtype == "terminal_input":
        terminals.write_input(msg.get("session_id", ""), msg.get("data", ""))

    elif mtype == "terminal_resize":
        terminals.resize(msg.get("session_id", ""), int(msg.get("cols", 80)), int(msg.get("rows", 24)))

    elif mtype == "terminal_close":
        session_id = msg.get("session_id", "")
        terminals.kill(session_id)
        await send(ws, {"type": "exec_closed", "session_id": session_id})

    else:
        logger.warning("未知指令 type=%s", mtype)


async def heartbeat(ws: Any) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await send(ws, {"type": "heartbeat", "timestamp": time.time()})
        except Exception:
            return


async def event_listener(ws: Any) -> None:
    """Docker events → 回报平台(die 时 manager 内先自动重启 ≤3 次)"""
    def _iterate():
        try:
            yield from manager.iter_events()
        except Exception:
            # Docker daemon 挂了:上报平台,平台标记 offline 不再调度(R16)
            logger.exception("Docker events 监听异常")

    for event in _iterate():
        action = event.get("Action")
        attrs = (event.get("Actor") or {}).get("Attributes") or {}
        container_id = (attrs.get("name") or event.get("id") or "")[:12]
        exit_code = attrs.get("exitCode")
        if action == "die":
            outcome = manager.handle_event("die", event.get("id", ""), exit_code)
            if outcome == "restarted":
                await send(ws, {"type": "container_event", "event": "restarted", "container_id": container_id})
                continue
            await send(ws, {
                "type": "container_event",
                "event": "die",
                "container_id": container_id,
                "exit_code": exit_code,
            })
        else:
            await send(ws, {"type": "container_event", "event": action, "container_id": container_id})


async def _receive_loop(ws: Any) -> None:
    async for raw in ws:
        import json

        try:
            await handle_message(ws, json.loads(raw))
        except Exception:
            logger.exception("处理消息失败: %s", raw[:200])


async def session() -> None:
    """单次连接会话:register(token+machine_info) → sync 对账 → 并发(收消息/心跳/事件)"""
    url = f"{PLATFORM_URL}"
    async with websockets.connect(url) as ws:
        await send(ws, {
            "type": "register",
            "token": RUNNER_TOKEN,
            "machine_info": collect_machine_info(),
            "host": RUNNER_HOST,
        })
        import json

        ack = json.loads(await ws.recv())
        if ack.get("type") != "register_success":
            raise RuntimeError(f"注册被拒绝: {ack}")
        logger.info("注册成功 runner_id=%s", ack.get("runner_id"))

        # 恢复对账:上报本地实际容器(R16)
        states = local_container_states()
        if states:
            await send(ws, {"type": "sync", "containers": states})

        receive_task = asyncio.create_task(_receive_loop(ws))
        beat_task = asyncio.create_task(heartbeat(ws))
        event_task = asyncio.create_task(event_listener(ws))
        done, pending = await asyncio.wait(
            {receive_task, beat_task, event_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()


async def main() -> None:
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    backoff = 1
    while True:
        try:
            logger.info("连接平台 %s", PLATFORM_URL)
            await session()
            backoff = 1
        except Exception as e:
            logger.warning("连接断开: %s(%ds 后重连)", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
