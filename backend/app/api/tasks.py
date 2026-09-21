"""任务路由 - R4(生命周期/对话/附件/事件流)"""

import logging

from fastapi import APIRouter, Depends, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
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
    items = []
    for t in rows:
        brief = task_service.task_brief(t)
        brief["created_by"] = await task_service._creator_brief(db, t.created_by)
        items.append(brief)
    return success(data={"items": items})


class CreateTaskRequest(BaseModel):
    type: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    base_branch: str = Field(default=None, max_length=64)
    work_branch: str = Field(default=None, max_length=64)


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

    task = await task_service.create_task(
        db, requirement, project, current_user,
        type=req.type, title=req.title, description=req.description,
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

    return success(data={"task_id": task.task_id}, message="任务已创建")


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
    data = {
        "task_id": task.task_id,
        "type": task.type,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "base_branch": task.base_branch,
        "work_branch": task.work_branch,
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
    return success(data=data)


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
    return success(data={"items": items})


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


@router.post("/tasks/{task_id}/messages")
async def send_message(
    task_id: str,
    req: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发送消息(@filename 引用;Claude CLI 兜底执行)"""
    task = await task_service.get_task_or_404(db, task_id)
    data = await task_service.send_message(db, task, current_user, req.content)
    return success(data=data)


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
@router.websocket("/ws/tasks/{task_id}/events")
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
