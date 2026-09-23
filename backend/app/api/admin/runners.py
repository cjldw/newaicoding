"""Runner 管理路由 - R16(超管)"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import BizError, ErrCode, success
from app.database import get_db, async_session_factory
from app.models.runner import Runner
from app.models.terminal import TerminalSession
from app.models.user import User
from app.schemas.runner import CreateRunnerRequest, RunnerItem
from app.services import audit_service, runner_service
from app.services.audit_service import audit_write  # R25 审计接入(模式 C:API 层,operator 在此)

import logging

logger = logging.getLogger(__name__)

# R26:Runner shell 会话在 terminal_sessions.task_id 的标记值(避免 task_id 可空迁移)
RUNNER_SHELL_TASK_TAG = "__runner_shell__"

router = APIRouter(prefix="/api/admin/runners", tags=["平台管理"])


def _to_item(runner: Runner) -> dict:
    return {
        "runner_id": runner.runner_id,
        "name": runner.name,
        "role": runner.role,
        "status": runner.status,
        "last_heartbeat_at": runner.last_heartbeat_at,
        "machine_info": runner.machine_info,
        "current_containers": runner.current_containers,
        "max_containers": runner.max_containers,
        "public_ip": runner.public_ip,
        "created_at": runner.created_at,
    }


# -------------------------------------------------------------------
# GET /api/admin/runners - Runner 列表
# -------------------------------------------------------------------
@router.get("")
async def list_runners(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管:Runner 列表(含状态/负载/机器信息)"""
    result = await db.execute(select(Runner).order_by(Runner.created_at.asc(), Runner.id.asc()))
    items = [_to_item(r) for r in result.scalars().all()]
    return success(data={"items": items})


# -------------------------------------------------------------------
# POST /api/admin/runners - 创建 Runner(生成 token,仅显示一次)
# -------------------------------------------------------------------
@router.post("")
async def create_runner(
    req: CreateRunnerRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管创建 Runner;token 仅本次响应可见(平台只存 bcrypt hash)"""
    runner, token = await runner_service.create_runner(
        db, current_user.user_id,
        name=req.name, role=req.role,
        max_containers=req.max_containers, public_ip=req.public_ip,
    )
    # R25 审计:runner.create(token 明文不落审计)
    await audit_write(
        db, current_user, "runner.create",
        target_type="runner", target_id=runner.runner_id,
        detail={"name": runner.name, "role": runner.role},
    )
    return success(
        data={"runner_id": runner.runner_id, "name": runner.name, "token": token},
        message="创建成功,请保存 token(仅显示一次)",
    )


# -------------------------------------------------------------------
# POST /api/admin/runners/{runner_id}/reset-token - 重置 token
# -------------------------------------------------------------------
@router.post("/{runner_id}/reset-token")
async def reset_runner_token(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """重置 token:旧 token 失效,Runner 需用新 token 重启"""
    token = await runner_service.reset_token(db, runner_id)
    # R25 审计:runner.reset_token
    await audit_write(
        db, current_user, "runner.reset_token",
        target_type="runner", target_id=runner_id,
    )
    return success(data={"token": token}, message="token 已重置,旧 token 已失效")


# -------------------------------------------------------------------
# POST /api/admin/runners/{runner_id}/disable - 禁用 Runner
# -------------------------------------------------------------------
@router.post("/{runner_id}/disable")
async def disable_runner(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """禁用 Runner:不再调度新任务(其上容器继续跑)"""
    await runner_service.disable_runner(db, runner_id)
    # R25 审计:runner.disable
    await audit_write(
        db, current_user, "runner.disable",
        target_type="runner", target_id=runner_id,
    )
    return success(message="Runner 已禁用")


# -------------------------------------------------------------------
# DELETE /api/admin/runners/{runner_id} - 删除 Runner
# -------------------------------------------------------------------
@router.delete("/{runner_id}")
async def delete_runner(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """删除 Runner;有运行中容器 → 16001"""
    await runner_service.delete_runner(db, runner_id)
    # R25 审计:runner.delete
    await audit_write(
        db, current_user, "runner.delete",
        target_type="runner", target_id=runner_id,
    )
    return success(message="Runner 已删除")


# -------------------------------------------------------------------
# POST /api/admin/runners/{runner_id}/shell-sessions - 打开 Runner 宿主 shell(R26)
# -------------------------------------------------------------------
@router.post("/{runner_id}/shell-sessions")
async def create_runner_shell_session(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    打开 Runner 容器内 shell(超管;R26):
    校验顺序(分片硬规格):404 → 6001 online → 6002 无活跃 shell 会话 → 6003 self_container_id
    → 建 TerminalSession(task_id=__runner_shell__ 标记)→ 下发既有 exec 消息(container_id=Runner 自身短 id)。
    """
    # 1. 存在(404)
    runner = await runner_service.get_runner_or_404(db, runner_id)

    # 2. online(6001)
    if runner.status != "online":
        raise BizError(ErrCode.RUNNER_NOT_ONLINE, "Runner 不在线")

    # 3. 并发上限 1(6002):该 Runner 存在未关闭的 shell 会话 → 拒绝
    #    (判定用台账表而非内存注册表:REST 创建即写行;关闭链路置 closed_at 后放行)
    existing = (await db.execute(
        select(TerminalSession).where(
            TerminalSession.runner_id == runner_id,
            TerminalSession.task_id == RUNNER_SHELL_TASK_TAG,
            TerminalSession.closed_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        raise BizError(ErrCode.RUNNER_SESSION_EXISTS, "该 Runner 已有终端会话,请先关闭")

    # 4. Runner 自报了自身容器 id(6003;旧版 Runner machine_info 无此键)
    self_container_id = (runner.machine_info or {}).get("self_container_id")
    if not self_container_id:
        raise BizError(ErrCode.RUNNER_TOO_OLD, "Runner 版本过旧,请升级 Runner 镜像后使用终端")

    # 5. 内存连接须在(库 online 但 WS 已断 → 同 6001 口径)
    runner_conn = runner_service.runner_registry.get(runner_id)
    if runner_conn is None or runner_conn.websocket is None:
        raise BizError(ErrCode.RUNNER_NOT_ONLINE, "Runner 不在线")

    # 6. 建会话台账(container_id=Runner 自身短 id;docker exec_create 接受短 id)
    session = TerminalSession(
        task_id=RUNNER_SHELL_TASK_TAG,
        container_id=self_container_id,
        runner_id=runner_id,
        shell="/bin/bash",
        created_by=current_user.user_id,
    )
    db.add(session)
    await db.flush()

    # 7. 下发既有 exec 消息(协议零新增 type;runner 侧 create_pty container_id 参数传入)
    await runner_service.send_to_runner(runner_conn, {
        "type": "exec",
        "container_id": self_container_id,
        "cmd": ["/bin/bash"],
        "pty": True,
        "session_id": session.session_id,
    })

    # 8. 审计:runner.terminal_open(operator=超管;spawn 独立会话)
    audit_service.spawn_audit_write(
        async_session_factory,
        {"user_id": current_user.user_id, "role": current_user.role},
        action_type="runner.terminal_open",
        target_type="runner", target_id=runner_id,
        detail={"runner_name": runner.name},
    )

    logger.info("Runner shell 会话创建 session=%s runner=%s by=%s", session.session_id, runner_id, current_user.user_id)
    return success(data={
        "session_id": session.session_id,
        "ws_url": f"/ws/terminal/{session.session_id}",
    })
