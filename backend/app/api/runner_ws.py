"""Runner WebSocket 端点 - R8(/ws/runner)

鉴权(R8 最小版):连接时 query/header 携带共享 token(settings.RUNNER_TOKEN);
R16 升级为 per-runner 注册 token 与 runners 表。

消息流:首条必须 register {runner_id, role?};后续 heartbeat /
container_started / container_stopped / container_event。
"""

import logging
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import async_session_factory
from app.services import container_service
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/runner")
async def runner_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    # ---- 鉴权(共享密钥;失败直接关闭) ----
    if token != settings.RUNNER_TOKEN:
        logger.warning("Runner 鉴权失败 token=%s…", token[:6])
        await websocket.close(code=4001)
        return

    await websocket.accept()

    # ---- 首条 register ----
    try:
        first = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if first.get("type") != "register" or not first.get("runner_id"):
        await websocket.close(code=4002)
        return

    host = first.get("host") or (websocket.client.host if websocket.client else "")
    conn = runner_registry.register(
        runner_id=first["runner_id"],
        role=first.get("role", "general"),
        websocket=websocket,
        host=host,
    )
    conn.last_heartbeat_ts = time.time()
    await websocket.send_json({"type": "register_ack", "ok": True})

    # ---- 消息循环 ----
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "heartbeat":
                conn.last_heartbeat_ts = time.time()

            elif mtype == "container_started":
                async with async_session_factory() as db:
                    await container_service.handle_container_started(
                        db,
                        task_id=msg.get("task_id", ""),
                        docker_container_id=msg.get("container_id", ""),
                        ports=msg.get("ports") or {},
                    )
                    await db.commit()

            elif mtype == "container_stopped":
                async with async_session_factory() as db:
                    await container_service.handle_container_stopped(
                        db, msg.get("container_id", "")
                    )
                    await db.commit()

            elif mtype == "container_event":
                async with async_session_factory() as db:
                    await container_service.handle_container_event(
                        db,
                        event=msg.get("event", ""),
                        docker_container_id=msg.get("container_id", ""),
                        exit_code=msg.get("exit_code"),
                    )
                    await db.commit()

            else:
                logger.warning("Runner 未知消息类型 runner=%s type=%s", conn.runner_id, mtype)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("Runner 连接异常 runner=%s: %s", conn.runner_id, e)
    finally:
        runner_registry.unregister(conn.runner_id)
