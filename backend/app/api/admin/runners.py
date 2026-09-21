"""Runner 管理路由 - R16(超管)"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import success
from app.database import get_db
from app.models.runner import Runner
from app.models.user import User
from app.schemas.runner import CreateRunnerRequest, RunnerItem
from app.services import runner_service

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
    return success(message="Runner 已删除")
