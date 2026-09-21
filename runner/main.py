"""Runner 主进程 - R8(WebSocket 客户端,连接平台;D13/R8 协议)

启动:
    PLATFORM_URL=wss://platform.example.com/ws/runner \
    RUNNER_TOKEN=xxx \
    RUNNER_ID=runner-01 \
    RUNNER_ROLE=general \
    RUNNER_HOST=1.2.3.4 \
    python3 main.py

职责:
- 连接平台 → register → 30s 心跳
- 收 start_container / stop_container 指令 → ContainerManager 执行 → 回报
- 监听 Docker events → 回报 container_event(崩溃自动重启 ≤3 次在 manager 内)
- 断线自动重连(指数退避)
"""

import asyncio
import logging
import os
from typing import Any

import websockets

from container_manager import ContainerManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("runner")

PLATFORM_URL = os.environ.get("PLATFORM_URL", "ws://localhost:8000/ws/runner")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
RUNNER_ID = os.environ.get("RUNNER_ID", "runner-local")
RUNNER_ROLE = os.environ.get("RUNNER_ROLE", "general")
RUNNER_HOST = os.environ.get("RUNNER_HOST", "")
HEARTBEAT_INTERVAL = 30  # 秒(D13:30s 心跳;平台 60s 未收到判 offline)

manager = ContainerManager()

# 运行中的 repo 清单(停止容器时强制 push 需要;容器 id → repos)
running_repos: dict[str, list[dict]] = {}


async def send(ws: Any, payload: dict) -> None:
    await ws.send(json_dumps(payload))


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


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

    else:
        logger.warning("未知指令 type=%s", mtype)


async def heartbeat(ws: Any) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await send(ws, {"type": "heartbeat", "runner_id": RUNNER_ID})
        except Exception:
            return


async def event_listener(ws: Any) -> None:
    """Docker events → 回报平台(die 时 manager 内先自动重启 ≤3 次)"""
    def _iterate():
        try:
            yield from manager.iter_events()
        except Exception:
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


async def session() -> None:
    """单次连接会话:register → 并发(收消息 / 心跳 / 事件监听)"""
    url = f"{PLATFORM_URL}?token={RUNNER_TOKEN}"
    async with websockets.connect(url) as ws:
        await send(ws, {
            "type": "register",
            "runner_id": RUNNER_ID,
            "role": RUNNER_ROLE,
            "host": RUNNER_HOST,
        })
        ack = await ws.recv()
        logger.info("平台注册确认: %s", ack)

        receive_task = asyncio.create_task(_receive_loop(ws))
        beat_task = asyncio.create_task(heartbeat(ws))
        event_task = asyncio.create_task(event_listener(ws))
        done, pending = await asyncio.wait(
            {receive_task, beat_task, event_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()


async def _receive_loop(ws: Any) -> None:
    async for raw in ws:
        import json

        try:
            await handle_message(ws, json.loads(raw))
        except Exception:
            logger.exception("处理消息失败: %s", raw[:200])


async def main() -> None:
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
