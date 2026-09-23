"""终端路由 - R9(会话 REST + WebSocket 频道 /ws/terminal/{session_id})

REST:
- POST /api/tasks/{task_id}/terminal-sessions:创建会话(owner/editor;容器须 running)
- DELETE /api/terminal-sessions/{session_id}:关闭会话(创建者)

WS:
- /ws/terminal/{session_id}?token=<access_token>(浏览器 WS 无法带 header)
  前端 → 平台:input / resize
  平台 → 前端:output / ai_output
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.core.security import decode_token
from app.database import get_db
from app.models.container import Container
from app.models.project import Project
from app.models.terminal import TerminalSession
from app.models.user import User
from app.services import project_member_service, runner_service, terminal_service
from app.services.runner_service import runner_registry
from app.services.terminal_service import (
    TerminalConnection,
    forward_input_to_runner,
    forward_output_to_frontend,
    forward_resize_to_runner,
    terminal_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["终端"])
# BUG-UI-065:WS 不吃 /api 前缀(前端/代理统一走 /ws/*;原挂在 /api 下导致握手 403)
ws_router = APIRouter(tags=["终端"])


# ---------------------------------------------------------------------------
# REST:创建 / 关闭会话
# ---------------------------------------------------------------------------
class CreateTerminalSessionRequest(BaseModel):
    shell: str = Field(default="/bin/bash", max_length=64)


async def _get_running_container(db: AsyncSession, task_id: str) -> Container:
    """任务对应的 running 容器(R4 任务表落地前的容器侧校验)"""
    result = await db.execute(
        select(Container).where(
            Container.task_id == task_id,
            Container.status == "running",
        ).order_by(Container.id.desc()).limit(1)
    )
    container = result.scalar_one_or_none()
    if container is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "终端不可用:任务无运行中的容器")
    return container


@router.post("/tasks/{task_id}/terminal-sessions")
async def create_terminal_session(
    task_id: str,
    req: CreateTerminalSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建终端会话(owner/editor;平台向 Runner 下发 exec pty 指令)"""
    # 1. 容器须 running
    container = await _get_running_container(db, task_id)

    # 2. 项目成员 editor 以上(viewer 不可用终端)
    project = await db.execute(
        select(Project).where(Project.project_id == container.project_id)
    )
    project_obj = project.scalar_one_or_none()
    if project_obj is None:
        raise BizError(404, "项目不存在", status_code=404)
    await project_member_service.require_project_role(db, project_obj, current_user, "editor")

    # 3. Runner 必须在线(否则终端不可用)
    if runner_registry.get(container.runner_id) is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "终端不可用:Runner offline")

    # 4. 建会话台账 + 下发 exec 指令
    session = TerminalSession(
        task_id=task_id,
        container_id=container.container_id,
        runner_id=container.runner_id,
        shell=req.shell,
        created_by=current_user.user_id,
    )
    db.add(session)
    await db.flush()

    runner_conn = runner_registry.get(container.runner_id)
    await runner_service.send_to_runner(runner_conn, {
        "type": "exec",
        "container_id": container.container_id,
        "cmd": [req.shell],
        "pty": True,
        "session_id": session.session_id,
    })

    logger.info("终端会话创建 session=%s task=%s by=%s", session.session_id, task_id, current_user.user_id)
    return success(data={
        "session_id": session.session_id,
        "ws_url": f"/ws/terminal/{session.session_id}",
    })


@router.delete("/terminal-sessions/{session_id}")
async def close_terminal_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """关闭会话(创建者;kill pty)"""
    result = await db.execute(
        select(TerminalSession).where(TerminalSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise BizError(ErrCode.TERMINAL_NOT_FOUND, "会话不存在")
    if session.created_by != current_user.user_id and current_user.role != "superadmin":
        raise BizError(ErrCode.TERMINAL_NOT_FOUND, "无权关闭该会话", status_code=403)

    # 通知 Runner kill pty(连接不在时跳过:pty 随 Runner 断线自理)
    runner_conn = runner_registry.get(session.runner_id)
    if runner_conn is not None and runner_conn.websocket is not None:
        await runner_service.send_to_runner(runner_conn, {
            "type": "terminal_close",
            "session_id": session_id,
        })

    session.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    return success(message="已关闭")


# ---------------------------------------------------------------------------
# WS:终端频道(浏览器 WS 无法带 header,token 走 query)
# ---------------------------------------------------------------------------
async def _ws_current_user(db: AsyncSession, token: str) -> User | None:
    from app.models.user import User as UserModel
    import jwt as pyjwt

    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    result = await db.execute(
        select(UserModel).where(UserModel.user_id == payload.get("sub", ""))
    )
    user = result.scalar_one_or_none()
    if user is None or user.token_version != payload.get("token_version") or user.status == "disabled":
        return None
    return user


@ws_router.websocket("/ws/terminal/{session_id}")
async def terminal_ws(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
):
    import asyncio as _asyncio

    from app.database import async_session_factory

    await websocket.accept()

    # ---- 鉴权 + 会话校验 ----
    async with async_session_factory() as db:
        user = await _ws_current_user(db, token)
        session_row = (await db.execute(
            select(TerminalSession).where(TerminalSession.session_id == session_id)
        )).scalar_one_or_none()
    if user is None or session_row is None:
        await websocket.close(code=4401)
        return
    if session_row.created_by != user.user_id and user.role != "superadmin":
        await websocket.close(code=4403)
        return

    conn = TerminalConnection(
        session_id=session_id,
        task_id=session_row.task_id,
        runner_id=session_row.runner_id,
        user_id=user.user_id,
        websocket=websocket,
    )
    terminal_registry.put(conn)  # 覆盖旧连接 = 断线重连 attach 语义
    logger.info("终端 WS 接入 session=%s user=%s", session_id, user.user_id)

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "input":
                await forward_input_to_runner(session_id, msg.get("data", ""))
            elif mtype == "resize":
                await forward_resize_to_runner(session_id, int(msg.get("cols", 80)), int(msg.get("rows", 24)))
            else:
                logger.debug("终端未知消息 type=%s", mtype)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("终端 WS 异常 session=%s: %s", session_id, e)
    finally:
        terminal_registry.pop(session_id)


# ---------------------------------------------------------------------------
# Runner → 平台终端输出(Runner WS 端点调用;供消息循环分发)
# ---------------------------------------------------------------------------
async def handle_runner_terminal_output(session_id: str, data: str) -> None:
    await forward_output_to_frontend(session_id, data, kind="output")
