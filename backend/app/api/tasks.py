"""任务路由 - R4(生命周期/对话/附件/事件流)"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task, TaskMessage, TaskUploadedFile
from app.models.user import User
from app.services import (
    file_service,
    file_upload_service,
    project_member_service,
    task_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["任务"])
# BUG-UI-065:WS 独立无前缀 router(同 terminal.py)
ws_router = APIRouter(tags=["任务"])


# ---------------------------------------------------------------------------
# 项目级任务列表(R26:项目详情页任务 tab)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目下的任务列表(项目成员;按需求聚合)"""
    # 校验项目成员权限
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    await project_member_service.require_project_role(db, project, current_user, "viewer")

    # 查询项目下所有任务
    rows = (await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc(), Task.id.desc())
    )).scalars().all()
    # BUG-063:批量查询容器状态(防 N+1),构建 task_id → 最新容器状态 map
    task_ids = [t.task_id for t in rows]
    container_map = await task_service.batch_latest_container_status(db, task_ids)
    items = []
    for t in rows:
        brief = task_service.task_brief(t, container_status=container_map.get(t.task_id))
        brief["created_by"] = await task_service._creator_brief(db, t.created_by)
        # 补充需求标题(用于分组显示)
        req = (await db.execute(
            select(Requirement).where(Requirement.req_id == t.req_id)
        )).scalars().first()
        if req:
            brief["req_title"] = req.title
        items.append(brief)
    return success(data={"items": items})


# ---------------------------------------------------------------------------
# 任务列表 / 创建
# ---------------------------------------------------------------------------
@router.get("/requirements/{req_id}/tasks")
async def list_tasks(
    req_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """需求下的任务列表(项目成员)"""
    rows = (await db.execute(
        select(Task).where(Task.req_id == req_id).order_by(Task.created_at.asc(), Task.id.asc())
    )).scalars().all()
    # BUG-063:批量查询容器状态(防 N+1)
    task_ids = [t.task_id for t in rows]
    container_map = await task_service.batch_latest_container_status(db, task_ids)
    items = []
    for t in rows:
        brief = task_service.task_brief(t, container_status=container_map.get(t.task_id))
        brief["created_by"] = await task_service._creator_brief(db, t.created_by)
        items.append(brief)
    return success(data={"items": items})


class CreateTaskRequest(BaseModel):
    type: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=128)
    # R1.F3:description 放宽为可选(快速创建 test/release 无描述输入框;
    # 未传时服务端按类型落默认文案,避免恒发空串必 422)
    description: str = Field(default=None, max_length=2000)
    base_branch: str = Field(default=None, max_length=64)
    work_branch: str = Field(default=None, max_length=64)
    # R7 发布任务扩展字段(创建后并入 extended_attributes)
    deploy_port: int = Field(default=None)
    deploy_host: str = Field(default=None, max_length=253)
    deploy_script: str = Field(default=None)


@router.post("/requirements/{req_id}/tasks")
async def create_task(
    req_id: str,
    req: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建任务(owner/editor,需绑定 token;校验需求状态/并发)"""
    requirement = (await db.execute(
        select(Requirement).where(Requirement.req_id == req_id)
    )).scalars().first()
    if requirement is None:
        raise BizError(404, "需求不存在", status_code=404)
    project = (await db.execute(
        select(Project).where(Project.project_id == requirement.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")

    # test 类型走专用创建(dev-done 前置 + test 仓库清单 + 报告路径;R6)
    # release 类型走专用创建(test passed 前置 + 端口/域名唯一 + 部署数限额;R7)
    # R1.F3:description 兜底(快速创建 test/release 无描述输入框;按类型落默认文案)
    type_label = {"dev": "开发", "test": "测试", "release": "发布"}.get(req.type, "任务")
    description = (req.description or "").strip() or f"{type_label}需求:{req.title}"
    hint = None
    if req.type == "release":
        task, hint = await task_service.create_release_task(
            db, requirement, project, current_user,
            title=req.title, description=description,
            deploy_port=req.deploy_port, deploy_host=req.deploy_host,
            deploy_script=req.deploy_script,
        )
    elif req.type == "test":
        task, hint = await task_service.create_test_task(
            db, requirement, project, current_user,
            title=req.title, description=description,
            based_on_dev_tasks=[],
        )
    else:
        task = await task_service.create_task(
            db, requirement, project, current_user,
            type=req.type, title=req.title, description=description,
            base_branch=req.base_branch, work_branch=req.work_branch,
        )
    # 创建即尝试拉起(无可用 Runner → 保持 pending 排队,8003 由前端轮询提示)
    from app.core.response import BizError as _BizError

    try:
        await task_service.start_task(db, task, project, requirement)
    except _BizError as e:
        if e.code != 8003:
            raise
        logger.info("无可用 Runner,任务排队 task=%s", task.task_id)

    # R7:发布任务创建即执行发布(merge/脚本/健康检查/路由注册)
    if req.type == "release":
        await task_service.run_release(db, task, project, requirement)

    return success(
        data={"task_id": task.task_id, **({"hint": hint} if hint else {})},
        message="任务已创建",
    )


# ---------------------------------------------------------------------------
# R7:发布执行 / 下线 / 端口检测
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/run-release")
async def run_release(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发布执行(merge/脚本/健康检查/路由注册);由创建流程调用,亦可手动重跑"""
    task = await task_service.get_task_or_404(db, task_id)
    if task.type != "release":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "仅发布任务可执行发布")
    requirement = (await db.execute(
        select(Requirement).where(Requirement.req_id == task.req_id)
    )).scalars().first()
    project = (await db.execute(
        select(Project).where(Project.project_id == task.project_id)
    )).scalars().first()
    await task_service.run_release(db, task, project, requirement)
    ext = task.extended_attributes or {}
    return success(data={
        "deploy_phase": ext.get("deploy_phase"),
        "deploy_url": "http://{}:{}".format(ext.get("deploy_host"), ext.get("deploy_port")),
    })


@router.post("/tasks/{task_id}/offline")
async def offline_deploy(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下线:摘除路由 + 销毁容器(URL 不可访问)"""
    task = await task_service.get_task_or_404(db, task_id)
    if task.type != "release":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "仅发布任务可下线")
    await task_service.offline_deploy(db, task)
    # R25 审计:release.offline(service 签名无 operator → 模式 C API 层)
    from app.services.audit_service import audit_write

    await audit_write(
        db, current_user, "release.offline",
        project_id=task.project_id, target_type="task", target_id=task_id,
    )
    return success(message="已下线")


@router.get("/tasks/check-port")
async def check_port(
    port: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """部署端口冲突实时检测(前端失焦轮询;创建时后端仍强校验 7001)"""
    from sqlalchemy import func as _func

    dup = (await db.execute(
        sqlalchemy.select(_func.count(Task.id)).where(
            Task.type == "release",
            sqlalchemy.func.json_unquote(
                sqlalchemy.func.json_extract(Task.extended_attributes, "$.deploy_port")
            ) == str(port),
            Task.status.notin_(["cancelled", "failed", "timeout"]),
        )
    )).scalar() or 0
    in_range = 10000 <= port <= 10099
    return success(data={"occupied": dup > 0 or not in_range})


# ---------------------------------------------------------------------------
# 任务详情 / 停止 / 重试 / 完成
# ---------------------------------------------------------------------------
@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务详情(项目成员)"""
    task = await task_service.get_task_or_404(db, task_id)
    return success(data=await _task_detail_data(db, task))


async def _task_detail_data(db: AsyncSession, task: Task) -> dict:
    """任务详情响应体(GET 详情 / PATCH 更新共用;R2.F2 抽取)"""
    ext = task.extended_attributes or {}
    # BUG-063:查最新容器状态(单任务,直接取最大 id 行)
    from app.models.container import Container
    container_result = await db.execute(
        select(Container.status)
        .where(Container.task_id == task.task_id)
        .order_by(Container.id.desc())
        .limit(1)
    )
    container_status = container_result.scalar_one_or_none()
    return {
        "task_id": task.task_id,
        # R4.F4:任务工作台面包屑需要 完整上级链(项目 / {项目名} / {需求} / 任务),补两个归属字段
        "project_id": task.project_id,
        "req_id": task.req_id,
        "type": task.type,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "display_status": task_service.derive_display_status(task.status, container_status),
        "base_branch": task.base_branch,
        "work_branch": task.work_branch,
        # R2.F2:发布维部署字段(编辑弹窗回填;非 release 行为空)
        "deploy_host": ext.get("deploy_host"),
        "deploy_port": ext.get("deploy_port"),
        "deploy_script": ext.get("deploy_script"),
        "container_id": task.container_id,
        "runner_id": task.runner_id,
        "created_by": await task_service._creator_brief(db, task.created_by),
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "total_tokens_in": task.total_tokens_in,
        "total_tokens_out": task.total_tokens_out,
        "error_message": task.error_message,
        "last_commit_sha": task.last_commit_sha,
    }


class UpdateTaskRequest(BaseModel):
    """R2.F2 任务字段编辑:缺省 = 不动(无"缺省置 NULL"语义);type/req_id/status 不在 schema,天然不可改"""
    title: str = Field(default=None, min_length=1, max_length=128)
    description: str = Field(default=None, max_length=2000)
    base_branch: str = Field(default=None, max_length=64)
    work_branch: str = Field(default=None, max_length=64)
    # R7 发布任务扩展字段(存 extended_attributes;deploy_port 复用全平台唯一校验)
    deploy_host: str = Field(default=None, max_length=253)
    deploy_port: int = Field(default=None)
    deploy_script: str = Field(default=None)


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    req: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑任务字段(owner/editor;仅 pending 可编辑,任务已开始字段变动影响执行语义)"""
    task = await task_service.get_task_or_404(db, task_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == task.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")

    if task.status != "pending":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "任务已开始,不可编辑", status_code=400)

    # release 维 deploy_port 变更:复用创建/check-port 的校验口径(范围 + 全平台唯一,排除自身)
    if task.type == "release" and req.deploy_port is not None \
            and req.deploy_port != (task.extended_attributes or {}).get("deploy_port"):
        from sqlalchemy import func as _func

        lo, hi = task_service.DEPLOY_PORT_RANGE
        if not (lo <= req.deploy_port <= hi):
            raise BizError(ErrCode.DEPLOY_PORT_CONFLICT, "端口已被占用", status_code=400)
        dup = (await db.execute(
            select(Task.task_id).where(
                Task.task_id != task.task_id,
                Task.type == "release",
                Task.status.notin_(["cancelled", "failed", "timeout"]),
                _func.json_unquote(
                    _func.json_extract(Task.extended_attributes, "$.deploy_port")
                ) == str(req.deploy_port),
            ).limit(1)
        )).scalar()
        if dup:
            raise BizError(ErrCode.DEPLOY_PORT_CONFLICT, "端口已被占用", status_code=400)

    if req.title is not None:
        task.title = req.title
    if req.description is not None:
        task.description = req.description
    # dev 维分支字段仅 dev 类型接受(其它类型静默忽略,与未知字段同口径)
    if task.type == "dev":
        if req.base_branch is not None:
            task.base_branch = req.base_branch
        if req.work_branch is not None:
            task.work_branch = req.work_branch
    if req.deploy_host is not None or req.deploy_port is not None or req.deploy_script is not None:
        ext = dict(task.extended_attributes or {})
        if req.deploy_host is not None:
            ext["deploy_host"] = req.deploy_host
        if req.deploy_port is not None:
            ext["deploy_port"] = req.deploy_port
        if req.deploy_script is not None:
            ext["deploy_script"] = req.deploy_script
        task.extended_attributes = ext  # 新 dict 对象,确保触发 UPDATE
    await db.flush()
    return success(data=await _task_detail_data(db, task), message="任务已更新")


# ---------------------------------------------------------------------------
# DELETE /api/tasks/{task_id} - 删除任务(R4.F2)
# ---------------------------------------------------------------------------
@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除任务(owner/editor;严档:仅 pending 且无容器/消息行可删;release 已部署或有活跃路由须先下线)"""
    from app.models.container import Container
    from app.models.route import Route
    from app.services.audit_service import audit_write

    task = await task_service.get_task_or_404(db, task_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == task.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")

    # release 特判:「发布完成」= status='done' 且 extended_attributes.deploy_phase='deployed'
    # (Task.status 枚举无 deployed 值,不得按状态值判断),或仍有活跃 Route(在线服务)→ 先下线再删
    if task.type == "release":
        deployed = task.status == "done" \
            and (task.extended_attributes or {}).get("deploy_phase") == "deployed"
        active_route = (await db.execute(
            select(Route.id).where(Route.task_id == task.task_id, Route.status == "active").limit(1)
        )).scalar()
        if deployed or active_route is not None:
            raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "发布已完成,请先下线部署", status_code=400)

    # 严档守卫:仅 pending 可删;running/passed/done 等已开始任务已产生运行/交付数据,一律拒绝
    if task.status != "pending":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "任务已开始,不可删除", status_code=400)

    # pending 但已有容器台账 / 对话消息行 → 已产生数据,同样拒绝(无 DB FK,exists 联查)
    container_row = (await db.execute(
        select(Container.id).where(Container.task_id == task.task_id).limit(1)
    )).scalar()
    message_row = (await db.execute(
        select(TaskMessage.id).where(TaskMessage.task_id == task.task_id).limit(1)
    )).scalar()
    if container_row is not None or message_row is not None:
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "任务已开始,已产生数据,不可删除", status_code=400)

    # 级联(仅可删分支):task_messages / task_uploaded_files 无 DB FK、无 ORM cascade → 显式删;
    # Route 残留(活跃已被上方守卫拦截)一并摘除
    await db.execute(delete(TaskMessage).where(TaskMessage.task_id == task.task_id))
    await db.execute(delete(TaskUploadedFile).where(TaskUploadedFile.task_id == task.task_id))
    await db.execute(delete(Route).where(Route.task_id == task.task_id))
    await db.delete(task)
    await db.flush()
    # R25 审计:task.delete(模式 C API 层)
    await audit_write(
        db, current_user, "task.delete",
        project_id=task.project_id, target_type="task", target_id=task_id,
    )
    return success(message="任务已删除")


class _SimpleOp(BaseModel):
    pass


@router.post("/tasks/{task_id}/stop")
async def stop_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """停止任务(owner/editor;容器销毁)"""
    task = await task_service.get_task_or_404(db, task_id)
    await task_service.finish_task(db, task, current_user, status="cancelled")
    return success(message="任务已停止")


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重试任务(failed/cancelled/timeout → pending)"""
    task = await task_service.get_task_or_404(db, task_id)
    await task_service.retry_task(db, task)
    # R25 审计:task.retry(service 签名无 operator → 模式 C API 层)
    from app.services.audit_service import audit_write

    await audit_write(
        db, current_user, "task.retry",
        project_id=task.project_id, target_type="task", target_id=task_id,
    )
    return success(message="任务已重试")


@router.post("/tasks/{task_id}/finish")
async def finish_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """完成任务:全仓库 commit+push(创建者 token)→ 容器销毁 → done"""
    task = await task_service.get_task_or_404(db, task_id)
    await task_service.finish_task(db, task, current_user, status="done")
    return success(message="任务已完成")


# ---------------------------------------------------------------------------
# R5:测试驳回回开发
# ---------------------------------------------------------------------------
class RejectToDevRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)


@router.post("/tasks/{test_task_id}/reject-to-dev")
async def reject_to_dev(
    test_task_id: str,
    req: RejectToDevRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """测试驳回创建修复 dev 任务(fix_context 自动携带失败用例与报告路径)"""
    test_task = await task_service.get_task_or_404(db, test_task_id)
    if test_task.type != "test":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "仅测试任务可驳回回开发")
    project = (await db.execute(
        select(Project).where(Project.project_id == test_task.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")

    task = await task_service.reject_to_dev(
        db, test_task, current_user, title=req.title, description=req.description,
    )
    # 创建即尝试拉起(排队语义同 R4)
    from app.core.response import BizError as _BizError

    try:
        requirement = (await db.execute(
            select(Requirement).where(Requirement.req_id == task.req_id)
        )).scalars().first()
        if requirement is not None:
            await task_service.start_task(db, task, project, requirement)
    except _BizError as e:
        if e.code != 8003:
            raise
    return success(data={"task_id": task.task_id}, message="已创建修复任务")


# ---------------------------------------------------------------------------
# R6:测试任务(用例确认 / 接受失败)
# ---------------------------------------------------------------------------
class ConfirmCasesRequest(BaseModel):
    test_cases: list[dict] = Field(min_length=1)


class AcceptFailureRequest(BaseModel):
    reason: str = Field(min_length=1)


@router.post("/tasks/{task_id}/confirm-cases")
async def confirm_cases(
    task_id: str,
    req: ConfirmCasesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认用例(可增删改)→ 开始执行(cases_review/pending → running)"""
    task = await task_service.get_task_or_404(db, task_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == task.project_id)
        )).scalars().first(), current_user, "editor",
    )
    await task_service.confirm_cases(db, task, current_user, req.test_cases)
    return success(message="用例已确认,开始执行")


@router.post("/tasks/{task_id}/accept-failure")
async def accept_failure(
    task_id: str,
    req: AcceptFailureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """接受失败(豁免):status=passed(带豁免标记)"""
    task = await task_service.get_task_or_404(db, task_id)
    await project_member_service.require_project_role(
        db, (await db.execute(
            select(Project).where(Project.project_id == task.project_id)
        )).scalars().first(), current_user, "editor",
    )
    await task_service.accept_failure(db, task, current_user, req.reason)
    return success(message="已接受失败,任务标记为通过")


# ---------------------------------------------------------------------------
# 对话
# ---------------------------------------------------------------------------
@router.get("/tasks/{task_id}/messages")
async def list_messages(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务对话历史"""
    rows = (await db.execute(
        select(TaskMessage).where(TaskMessage.task_id == task_id)
        .order_by(TaskMessage.created_at.asc(), TaskMessage.id.asc())
    )).scalars().all()
    items = [
        {
            "message_id": m.message_id,
            "role": m.role,
            "content": m.content,
            "file_refs": m.file_refs,
            "tool_calls": m.tool_calls,
            "tokens_in": m.tokens_in,
            "tokens_out": m.tokens_out,
            "created_at": m.created_at,
        }
        for m in rows
    ]
    # R3.F5(BUG-076):容器启动代数 — containers 表该 task_id 的行数(行数=创建过几个实例)
    # 无容器行 → 0;前端据此判定容器是否换新,决定是否重发 /rd-prd
    from sqlalchemy import func as sa_func
    container_gen = (await db.execute(
        select(sa_func.count()).select_from(Container).where(Container.task_id == task_id)
    )).scalar() or 0
    return success(data={"items": items, "container_generation": container_gen})


class SendMessageRequest(BaseModel):
    # R5.F5(BUG-076):content 用 field_validator 显式校验 max_length,
    # 错误信息含 'max_length' 便于前端/测试定位(Field.max_length 的错误文案不含该词)
    content: str = Field(min_length=1)
    # R34.F2:会话级模型配置(对话框切换;None=走项目默认回退链)
    config_id: str | None = None

    @field_validator("content")
    @classmethod
    def check_content_length(cls, v: str) -> str:
        """R5.F5(BUG-076):显式 max_length 校验,错误信息含 'max_length' 便于前端/测试定位"""
        if len(v) > 200_000:
            raise ValueError(f"content 超过 max_length 限制(最多 200000 字符,当前 {len(v)})")
        return v


@router.post("/tasks/{task_id}/messages")
async def send_message(
    task_id: str,
    req: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送消息(@filename 引用;R32.F3 流式执行:增量经 /ws/tasks/:id/events 实时下发)"""
    task = await task_service.get_task_or_404(db, task_id)
    data = await task_service.send_message_stream(
        db, task, current_user, req.content, config_id=req.config_id,
    )
    return success(data=data)


@router.post("/tasks/{task_id}/messages/cancel")
async def cancel_message(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消在途 AI 对话(R34.F1 真取消):按任务反查在途流式请求 → 下发 runner
    exec_tool_cancel(容器内 pkill claude)+ 本地结算;终态广播 chat_done
    ok:false(error=cancelled)。权限 owner/editor(viewer 403);无在途对话幂等"""
    logger.info("取消对话接口入口 task=%s by=%s", task_id, current_user.user_id)
    task = await task_service.get_task_or_404(db, task_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == task.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")
    data = await task_service.cancel_message_stream(db, task)
    return success(
        data=data,
        message="已请求取消" if data.get("cancelled") else "当前无进行中的对话",
    )


# ---------------------------------------------------------------------------
# R34.F3:AI 权限确认应答
# ---------------------------------------------------------------------------
class ToolConfirmRequest(BaseModel):
    """确认应答:confirm_id 一次性;choice 两档(规格拍板,不做「始终允许」)"""
    confirm_id: str = Field(min_length=1)
    choice: Literal["allow", "deny"]


@router.post("/tasks/{task_id}/confirm")
async def confirm_tool_use(
    task_id: str,
    req: ToolConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """应答 AI 权限确认(R34.F3):挂起 Future set_result 放行执行 + 应答下行 Runner
    桥接。鉴权=任务成员(与 messages/cancel 同口径 owner/editor,viewer/非成员 403);
    confirm_id 不存在/已应答 → 4001(HTTP 200 + 业务码,与 R28 头像 4001 同口径)"""
    logger.info("确认应答入口 task=%s confirm=%s choice=%s by=%s",
                task_id, req.confirm_id, req.choice, current_user.user_id)
    task = await task_service.get_task_or_404(db, task_id)
    project = (await db.execute(
        select(Project).where(Project.project_id == task.project_id)
    )).scalars().first()
    await project_member_service.require_project_role(db, project, current_user, "editor")

    if not task_service.resolve_confirm(req.confirm_id, req.choice):
        raise BizError(4001, "确认请求不存在或已应答")
    # 应答下行 Runner 桥接(尽力而为:通道缺失/Runner 离线不回错,超时兜底在桥接层)
    await task_service.deliver_confirm_choice(req.confirm_id, req.choice)
    return success(data={"ok": True})


# ---------------------------------------------------------------------------
# 附件上传 / 列表 / 下载 / 删除
# ---------------------------------------------------------------------------
@router.post("/tasks/{task_id}/files/upload")
async def upload_task_file(
    task_id: str,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传附件到容器 /tmp/uploads/{task_id}/(限额 4004/4006;单次 10 个由前端批量口径)"""
    task = await task_service.get_task_or_404(db, task_id)
    content = await file.read()
    data = await file_upload_service.save_upload(
        db, task, current_user.user_id,
        filename=file.filename or "file", content=content,
        mime_type=file.content_type or "application/octet-stream",
    )
    return success(data=data, message="上传成功")


@router.get("/tasks/{task_id}/files/uploads")
async def list_task_files(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已上传文件列表(@ 自动补全数据源)"""
    rows = (await db.execute(
        select(TaskUploadedFile).where(TaskUploadedFile.task_id == task_id)
        .order_by(TaskUploadedFile.uploaded_at.asc(), TaskUploadedFile.id.asc())
    )).scalars().all()
    items = [
        {
            "file_id": f.file_id,
            "filename": f.filename,
            "stored_filename": f.stored_filename,
            "size": f.size,
            "uploaded_by": await task_service._creator_brief(db, f.uploaded_by),
            "uploaded_at": f.uploaded_at,
        }
        for f in rows
    ]
    return success(data={"items": items})


@router.get("/tasks/{task_id}/files/uploads/{file_id}")
async def download_task_file(
    task_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下载附件(从容器读取文件流)"""
    row = (await db.execute(
        select(TaskUploadedFile).where(
            TaskUploadedFile.file_id == file_id, TaskUploadedFile.task_id == task_id
        )
    )).scalars().first()
    if row is None:
        raise BizError(404, "文件不存在", status_code=404)
    content = await file_service.task_read_file_bytes(db, task_id, row.container_path)
    return Response(
        content=content,
        media_type=row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{row.stored_filename}"'},
    )


@router.delete("/tasks/{task_id}/files/uploads/{file_id}")
async def delete_task_file(
    task_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除附件记录(容器文件随任务销毁)"""
    row = (await db.execute(
        select(TaskUploadedFile).where(
            TaskUploadedFile.file_id == file_id, TaskUploadedFile.task_id == task_id
        )
    )).scalars().first()
    if row is None:
        raise BizError(404, "文件不存在", status_code=404)
    await db.delete(row)
    await db.flush()
    return success(message="已删除")


# ---------------------------------------------------------------------------
# WS:任务事件流 /ws/tasks/{task_id}/events
# ---------------------------------------------------------------------------
@ws_router.websocket("/ws/tasks/{task_id}/events")
async def task_events_ws(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(default=""),
):
    """活动流推送:tool_call / status_changed"""
    import asyncio as _asyncio

    from app.api.terminal import _ws_current_user
    from app.database import async_session_factory
    from app.services.task_service import task_event_registry

    await websocket.accept()
    async with async_session_factory() as db:
        user = await _ws_current_user(db, token)
    if user is None:
        await websocket.close(code=4401)
        return

    conn = task_event_registry.connect(task_id, websocket)
    try:
        while True:
            await _asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        task_event_registry.disconnect(task_id, conn)
