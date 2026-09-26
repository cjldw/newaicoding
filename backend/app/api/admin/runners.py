"""Runner 管理路由 - R16(超管)+ R31(本机快速创建/生命周期)"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.auth import require_superadmin
from app.core.response import BizError, ErrCode, success
from app.database import get_db, async_session_factory
from app.models.runner import Runner
from app.models.terminal import TerminalSession
from app.models.user import User
from app.schemas.runner import CreateRunnerRequest, RunnerItem
from app.services import audit_service, local_runner_service, runner_service
from app.services.audit_service import audit_write  # R25 审计接入(模式 C:API 层,operator 在此)

import logging
from datetime import datetime, timezone

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
        "is_local": bool(runner.is_local),  # R31
        "tags": list(runner.tags or []),  # R32:恒数组,NULL 存量折 []
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
        tags=req.tags,
    )
    # R25 审计:runner.create(token 明文不落审计)
    await audit_write(
        db, current_user, "runner.create",
        target_type="runner", target_id=runner.runner_id,
        detail={"name": runner.name, "role": runner.role},
    )
    return success(
        data={"runner_id": runner.runner_id, "name": runner.name,
              "tags": list(runner.tags or []), "token": token},
        message="创建成功,请保存 token(仅显示一次)",
    )


# -------------------------------------------------------------------
# R31 本机快速创建与生命周期(全部超管;token 明文只进子进程 env,响应/审计无值)
# -------------------------------------------------------------------
class CreateLocalRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    max_containers: int = Field(default=10, ge=1, le=100)
    # R32:任务类型标签(恒 worker 角色;空/缺省=通用兜底)
    tags: Optional[list[str]] = None


@router.post("/local")
async def create_local_runner(
    req: CreateLocalRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    本机快速创建(含启动):校验(上限16003→环境16002→名称16005)
    → 落库(is_local=1, offline)→ spawn 子进程 → 等注册 ≤10s。
    注册超时不回滚(200 status=offline,可停止/重启/删除排障)。
    """
    import uuid as _uuid

    from app.core.security import hash_password
    from app.services.runner_service import _generate_token

    # 顺序:先查库上限(16003),再环境校验(16002,不落库不 spawn)
    await local_runner_service.check_local_limit(db)
    await local_runner_service.preflight()

    runner_id = str(_uuid.uuid4())
    name = (req.name or "").strip() or f"local-{runner_id[:8]}"
    await local_runner_service.check_name_free(db, name)

    token_plain = _generate_token()
    # R32:tags 校验(local 恒 worker;非法值 16008 在落库前拒绝)
    local_tags = runner_service.validate_tags(req.tags, "worker")
    runner = Runner(
        runner_id=runner_id,
        name=name,
        role="worker",
        token_hash=hash_password(token_plain),
        max_containers=req.max_containers,
        tags=local_tags or None,
        is_local=1,
        status="offline",
        created_by=current_user.user_id,
    )
    db.add(runner)
    await db.flush()
    # R31 实现留痕:spawn 前显式提交——子进程 ~1s 内即 register,handle_register 走独立
    # 会话,必须能看到已提交的 token hash;否则首连被拒(token 无效),白耗退避窗口
    await db.commit()

    launch = await local_runner_service.spawn_local(runner, token_plain)
    status = await local_runner_service.wait_online(db, runner_id)
    if status == "online":
        runner.status = "online"
        await db.flush()

    await audit_write(
        db, current_user, "runner.create_local",
        target_type="runner", target_id=runner_id,
        detail={"name": name, "role": "worker", "launch_env_keys": launch["env_keys"]},
    )
    msg = "创建成功" if status == "online" else "Runner 已启动但未完成注册,可在列表查看状态或重试启动"
    return success(data={
        "runner_id": runner_id, "name": name, "status": status,
        "tags": list(local_tags),  # R32
        "token_hidden": True, "launch_command": launch,
    }, message=msg)


# -------------------------------------------------------------------
# R32:PATCH /api/admin/runners/{runner_id} - 全字段编辑
# -------------------------------------------------------------------
class UpdateRunnerRequest(BaseModel):
    """R32 编辑请求体(全可选,未传=不改动;role/token/is_local 不可编辑)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    max_containers: Optional[int] = Field(default=None, ge=1, le=100)
    tags: Optional[list[str]] = None
    public_ip: Optional[str] = Field(default=None, max_length=64)


@router.patch("/{runner_id}")
async def update_runner(
    runner_id: str,
    req: UpdateRunnerRequest,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    R32:Runner 全字段编辑。
    - 校验失败(16005 名称/16008 标签/2007 deploy 公网 IP)直接抛,前端弹窗不关
    - disabled 行允许编辑(禁用只挡调度,元数据无碍)
    - 单行 UPDATE 原子;调度实时查库,新 tags 下次调度即生效
    """
    # 仅透传请求体显式出现的字段(exclude_unset:未传=不改动)
    payload = req.model_dump(exclude_unset=True)
    runner, before = await runner_service.update_runner(db, runner_id, **payload)

    # 改动字段名(与 before 快照比对;tags 显式清空也算改动)
    changed: list[str] = []
    for k, v in payload.items():
        if k == "tags":
            if list(v or []) != before.get("tags", []):
                changed.append(k)
        elif v is not None and v != before.get(k):
            changed.append(k)

    # R25 审计(模式 C):runner.update,detail 只记改动字段名与 tags 前后(无敏感值)
    # no-op(PATCH 与现状全同)不落审计,避免 changed=[] 空事件污染审计轨(code-review #4)
    if changed:
        await audit_write(
            db, current_user, "runner.update",
            target_type="runner", target_id=runner.runner_id,
            detail={
                "changed": changed,
                "before_tags": before.get("tags", []),
                "after_tags": list(runner.tags or []),
            },
        )
    return success(data=_to_item(runner), message="Runner 已更新")


@router.post("/{runner_id}/start")
async def start_local_runner(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    启动离线本机 runner。online/进行中幂等 200"已在运行";disabled→16006;非本机→404。
    决策留痕:token 不可逆(仅存 hash),启动时**内部重新生成** token 注入子进程
    (明文仍不可见,符合 Q57);离线无活连接,重置旧 token 无副作用。
    """
    runner = await runner_service.get_runner_or_404(db, runner_id)
    if not runner.is_local:
        raise BizError(404, "仅本机快速创建的 Runner 支持启动", status_code=404)
    if runner.status == "disabled":
        raise BizError(ErrCode.RUNNER_NOT_LOCAL, "已禁用的 Runner 不可启动,请删除后重建")
    if runner.status == "online":
        return success(data={"runner_id": runner_id, "status": "online"}, message="Runner 已在运行")

    if not local_runner_service.try_acquire(runner_id):
        return success(data={"runner_id": runner_id, "status": runner.status}, message="Runner 已在运行")
    try:
        from app.core.security import hash_password
        from app.services.runner_service import _generate_token

        await local_runner_service.preflight()
        token_plain = _generate_token()
        runner.token_hash = hash_password(token_plain)
        await db.flush()
        await db.commit()  # spawn 前提交(同 create_local 留痕:子进程注册需见已提交 hash)
        await local_runner_service.spawn_local(runner, token_plain)
        status = await local_runner_service.wait_online(db, runner_id)
        runner.status = status
        await db.flush()
        await audit_write(
            db, current_user, "runner.start",
            target_type="runner", target_id=runner_id,
            detail={"name": runner.name},
        )
    finally:
        local_runner_service.release(runner_id)
    return success(data={"runner_id": runner_id, "status": status}, message="Runner 已启动")


@router.post("/{runner_id}/stop")
async def stop_local_runner(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    停止本机 runner(指令式)。非本机→16006;offline 幂等;
    online 无 WS 连接且无句柄→16007(平台重启后孤儿,手动处理)。
    """
    runner = await runner_service.get_runner_or_404(db, runner_id)
    if not runner.is_local:
        raise BizError(ErrCode.RUNNER_NOT_LOCAL, "远程 Runner 请在其宿主机上手动停止")

    await local_runner_service.shutdown_local(runner)
    already_stopped = runner.status == "offline"
    runner.status = "offline"
    await db.flush()
    await audit_write(
        db, current_user, "runner.stop",
        target_type="runner", target_id=runner_id,
        detail={"name": runner.name},
    )
    msg = "Runner 已处于停止状态" if already_stopped else "Runner 已停止"
    return success(data={"runner_id": runner_id, "status": "offline"}, message=msg)


@router.post("/{runner_id}/restart")
async def restart_local_runner(
    runner_id: str,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """重启本机 runner = 停止 + 重新 spawn(token 内部重新生成,同 start 留痕)。"""
    runner = await runner_service.get_runner_or_404(db, runner_id)
    if not runner.is_local:
        raise BizError(404, "仅本机快速创建的 Runner 支持重启", status_code=404)
    if runner.status == "disabled":
        raise BizError(ErrCode.RUNNER_NOT_LOCAL, "已禁用的 Runner 不可重启,请删除后重建")

    await local_runner_service.shutdown_local(runner)
    # 停成功再起:复用 start 的 spawn 流程
    from app.core.security import hash_password
    from app.services.runner_service import _generate_token

    await local_runner_service.preflight()
    token_plain = _generate_token()
    runner.token_hash = hash_password(token_plain)
    await db.flush()
    await db.commit()  # spawn 前提交(同 create_local 留痕)
    await local_runner_service.spawn_local(runner, token_plain)
    status = await local_runner_service.wait_online(db, runner_id)
    runner.status = status
    await db.flush()
    await audit_write(
        db, current_user, "runner.restart",
        target_type="runner", target_id=runner_id,
        detail={"name": runner.name},
    )
    return success(data={"runner_id": runner_id, "status": status}, message="Runner 已重启")


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
    """
    删除 Runner(R31 分支):
    - 远程(token 型)runner:原语义不变,有进行中任务容器 → 16001;
    - 本机(is_local)runner:代停流程——先停全部容器(强制 push 链)→ 停进程 → 删记录;
      任一容器停失败 → 16004,记录保留(重试幂等)。
    """
    runner = await runner_service.get_runner_or_404(db, runner_id)
    if runner.is_local:
        n = await local_runner_service.stop_all_containers_and_wait(db, runner)
        await local_runner_service.shutdown_local(runner)
        await local_runner_service.remove_local_container(runner_id)  # R31.F3:容器形态删除收尾(不存在则忽略)
        await db.delete(runner)
        await db.flush()
        await audit_write(
            db, current_user, "runner.delete",
            target_type="runner", target_id=runner_id,
            detail={"代停容器数": n},
        )
        return success(message="Runner 已删除")

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
    force: bool = False,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    打开 Runner 容器内 shell(超管;R26):
    校验顺序(分片硬规格):404 → 6001 online → 6002 无活跃 shell 会话 → 6003 self_container_id
    → 建 TerminalSession(task_id=__runner_shell__ 标记)→ 下发既有 exec 消息(container_id=Runner 自身短 id)。
    R26.F2(BUG-047):?force=true 时跳过 6002 拒绝——先复用 terminal.py 关闭链路
    (通知 Runner terminal_close kill pty + 置 closed_at)清掉该 Runner 全部活跃会话再放行,
    供前端「强制关闭并新建」按钮使用;不带 force 行为不变(向后兼容)。
    """
    # 1. 存在(404)
    runner = await runner_service.get_runner_or_404(db, runner_id)

    # 2. online(6001)
    if runner.status != "online":
        raise BizError(ErrCode.RUNNER_NOT_ONLINE, "Runner 不在线")

    # 3. 并发上限 1(6002):该 Runner 存在未关闭的 shell 会话 → 拒绝
    #    (判定用台账表而非内存注册表:REST 创建即写行;关闭链路置 closed_at 后放行)
    #    R26.F2(BUG-047):force=true → 不拒绝,改为逐一强制关闭活跃会话:
    #    语义与 DELETE /api/terminal-sessions/{sid} 完全一致(通知 Runner terminal_close
    #    kill pty;连接不在时跳过 + 台账置 closed_at),旧会话的浏览器 WS 由 closed_at 判死
    existing_rows = (await db.execute(
        select(TerminalSession).where(
            TerminalSession.runner_id == runner_id,
            TerminalSession.task_id == RUNNER_SHELL_TASK_TAG,
            TerminalSession.closed_at.is_(None),
        )
    )).scalars().all()
    if existing_rows:
        if not force:
            raise BizError(ErrCode.RUNNER_SESSION_EXISTS, "该 Runner 已有终端会话,请先关闭")
        old_conn = runner_service.runner_registry.get(runner_id)
        for old_session in existing_rows:
            if old_conn is not None and old_conn.websocket is not None:
                await runner_service.send_to_runner(old_conn, {
                    "type": "terminal_close",
                    "session_id": old_session.session_id,
                })
            old_session.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()

    # 4. Runner 自报了自身容器 id(按上报形态细分:R26.F1/BUG-041 文案细分;R31.F1/BUG-043 空串降级宿主 shell)
    machine = runner.machine_info or {}
    if "self_container_id" not in machine:
        # 旧版 Runner 镜像:register 载荷无此键(R26 前版本)→ 升级镜像
        raise BizError(ErrCode.RUNNER_TOO_OLD, "Runner 版本过旧,请升级 Runner 镜像后使用终端")
    self_container_id = machine.get("self_container_id")
    is_host_shell = False
    if not self_container_id:
        # 新版上报空串:进程未运行在容器中(R31 本机裸跑等,HOSTNAME 缺失)→ 降级宿主 shell:
        # runner 侧按 "__host__" 哨兵走 subprocess(cmd.exe/bash);超管专用入口 + terminal_open 审计,
        # 与 R31 平台在本机 spawn 进程权责一致
        self_container_id = "__host__"
        is_host_shell = True

    # 5. 内存连接须在(库 online 但 WS 已断 → 同 6001 口径)
    runner_conn = runner_service.runner_registry.get(runner_id)
    if runner_conn is None or runner_conn.websocket is None:
        raise BizError(ErrCode.RUNNER_NOT_ONLINE, "Runner 不在线")

    # 6. 建会话台账(container_id=Runner 自身短 id;宿主会话="__host__" 哨兵,R31.F1)
    shell_name = ("/bin/bash" if not is_host_shell
                  else ("cmd.exe" if "win" in str(machine.get("os", "")).lower() else "bash"))
    session = TerminalSession(
        task_id=RUNNER_SHELL_TASK_TAG,
        container_id=self_container_id,
        runner_id=runner_id,
        shell=shell_name,
        created_by=current_user.user_id,
    )
    db.add(session)
    await db.flush()

    # 7. 下发既有 exec 消息(协议零新增 type;runner 侧 create_pty container_id 参数传入)
    #    R31.F3(BUG-049):cwd=/app(Runner 容器镜像 WORKDIR)——任务终端的
    #    /workspace/main 约定在 Runner 自身容器里不存在;runner 侧消息透传 cwd
    await runner_service.send_to_runner(runner_conn, {
        "type": "exec",
        "container_id": self_container_id,
        "cmd": ["/bin/bash"],
        "cwd": "/app",
        "pty": True,
        "session_id": session.session_id,
    })

    # 8. 审计:runner.terminal_open(operator=超管;spawn 独立会话)
    audit_service.spawn_audit_write(
        async_session_factory,
        {"user_id": current_user.user_id, "role": current_user.role},
        action_type="runner.terminal_open",
        target_type="runner", target_id=runner_id,
        detail={"runner_name": runner.name,
                "session_kind": "runner_host" if is_host_shell else "runner_shell"},
    )

    logger.info("Runner shell 会话创建 session=%s runner=%s by=%s", session.session_id, runner_id, current_user.user_id)
    return success(data={
        "session_id": session.session_id,
        "ws_url": f"/ws/terminal/{session.session_id}",
    })
