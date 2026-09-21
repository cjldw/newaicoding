"""Runner WebSocket 端点 - R16(/ws/runner)

鉴权:连接开放后首条 register 携带一次性 token,平台 bcrypt 比对 runners.token_hash
(R8 的共享 RUNNER_TOKEN 已废弃);disabled/无匹配 → 关闭连接。

消息流:register(token, machine_info) → register_success(runner_id)
后续:heartbeat(timestamp,±30s 容忍/>5min 拒绝) / sync(容器列表对账) /
container_started / container_stopped / container_event /
docker_daemon_unavailable(Runner 标 offline)。
"""

import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import async_session_factory
from app.services import container_service, runner_service
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/runner")
async def runner_ws(websocket: WebSocket):
    await websocket.accept()

    # ---- 首条 register(token + machine_info) ----
    try:
        first = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if first.get("type") != "register":
        await websocket.close(code=4002)
        return

    async with async_session_factory() as db:
        runner = await runner_service.handle_register(
            db, first.get("token", ""), first.get("machine_info")
        )
        await db.commit()

    if runner is None:
        await websocket.send_json({"type": "register_failed", "error": "token 无效或 Runner 已禁用"})
        await websocket.close(code=4001)
        return

    conn = runner_registry.register(
        runner_id=runner.runner_id,
        role=runner.role,
        websocket=websocket,
        host=first.get("host") or (websocket.client.host if websocket.client else ""),
    )
    conn.last_heartbeat_ts = time.time()
    await websocket.send_json({"type": "register_success", "runner_id": runner.runner_id})

    # ---- 消息循环 ----
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            if mtype == "heartbeat":
                async with async_session_factory() as db:
                    fresh = await runner_service.get_runner_or_404(db, runner.runner_id)
                    ok = await runner_service.handle_heartbeat(db, fresh, msg.get("timestamp"))
                    await db.commit()
                conn.last_heartbeat_ts = time.time()
                if not ok:
                    await websocket.close(code=4006)  # 时钟漂移 > 5min
                    break

            elif mtype == "sync":
                # Runner 恢复后对账(以 Runner 上报为准)
                async with async_session_factory() as db:
                    fresh = await runner_service.get_runner_or_404(db, runner.runner_id)
                    await runner_service.handle_sync(db, fresh, msg.get("containers") or [])
                    await db.commit()

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
                # docker_daemon_unavailable → Runner 置 offline(不再调度)
                if msg.get("event") == "docker_daemon_unavailable":
                    async with async_session_factory() as db:
                        fresh = await runner_service.get_runner_or_404(db, runner.runner_id)
                        fresh.status = "offline"
                        await db.commit()
                    runner_registry.unregister(runner.runner_id)
                    logger.warning("Runner docker daemon 不可用 → offline runner=%s", runner.runner_id)
                    continue
                async with async_session_factory() as db:
                    await container_service.handle_container_event(
                        db,
                        event=msg.get("event", ""),
                        docker_container_id=msg.get("container_id", ""),
                        exit_code=msg.get("exit_code"),
                    )
                    await db.commit()

            elif mtype == "terminal_output":
                # Runner pty 输出 → 前端终端(R9)
                from app.services.terminal_service import forward_output_to_frontend

                await forward_output_to_frontend(msg.get("session_id", ""), msg.get("data", ""))

            elif mtype == "exec_started":
                # pty 创建确认(R9;前端建连即 attach,无需额外动作)
                logger.info("Runner pty 已创建 session=%s", msg.get("session_id"))

            elif mtype == "exec_closed":
                # pty 关闭:通知前端会话结束
                from app.services.terminal_service import forward_output_to_frontend

                await forward_output_to_frontend(
                    msg.get("session_id", ""), "\r\n[进程已退出]\r\n", kind="output"
                )

            elif mtype == "port_listening":
                # R10:端口监听 → 注册/激活预览路由
                from app.services import preview_service

                async with async_session_factory() as db:
                    await preview_service.handle_port_listening(
                        db, msg.get("container_id", ""), int(msg.get("port", 0))
                    )
                    await db.commit()

            elif mtype == "port_closed":
                # R10:端口关闭 → 路由 inactive
                from app.services import preview_service

                async with async_session_factory() as db:
                    await preview_service.handle_port_closed(
                        db, msg.get("container_id", ""), int(msg.get("port", 0))
                    )
                    await db.commit()

            else:
                logger.warning("Runner 未知消息类型 runner=%s type=%s", runner.runner_id, mtype)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("Runner 连接异常 runner=%s: %s", runner.runner_id, e)
    finally:
        runner_registry.unregister(runner.runner_id)
