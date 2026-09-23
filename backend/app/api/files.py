"""文件路由 - R11(项目模式只读浏览 / 任务模式容器文件编辑 / 变更清单 / watcher 频道)"""

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import error, success
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services import avatar_service, file_service, project_member_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["文件"])
# BUG-UI-065:WS 独立无前缀 router
ws_router = APIRouter(tags=["文件"])

# 项目 → 项目对象解析(共用小工具)
async def _project_or_404(db: AsyncSession, project_id: str) -> Project:
    from app.services.project_service import get_project_or_404

    return await get_project_or_404(db, project_id)


# ---------------------------------------------------------------------------
# 项目模式(只读;GitLab API)
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/files")
async def project_files(
    project_id: str,
    branch: str = Query(default="master"),
    path: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目模式文件树(GitLab API;项目成员只读)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    items = await file_service.project_file_tree(db, project, branch, path)
    return success(data={"items": items})


@router.get("/projects/{project_id}/files/content")
async def project_file_content(
    project_id: str,
    branch: str = Query(default="master"),
    path: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目模式文件内容(只读)"""
    project = await _project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    data = await file_service.project_file_content(db, project, branch, path)
    return success(data=data)


# ---------------------------------------------------------------------------
# 任务模式(容器文件;viewer 只读,editor+ 可写)
# ---------------------------------------------------------------------------
@router.get("/tasks/{task_id}/files")
async def task_files(
    task_id: str,
    path: str = Query(default="/workspace/main"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务模式文件树(容器目录列表)"""
    items = await file_service.task_file_list(db, task_id, path)
    return success(data={"items": items})


@router.get("/tasks/{task_id}/files/content")
async def task_file_content(
    task_id: str,
    path: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务模式读文件"""
    data = await file_service.task_read_file(db, task_id, path)
    return success(data=data)


class WriteFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(default="")


class FileOperationRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=16)  # create/delete/rename/revert
    path: str = Field(min_length=1, max_length=500)
    new_path: str = Field(default=None, max_length=500)


@router.put("/tasks/{task_id}/files/content")
async def task_write_file(
    task_id: str,
    req: WriteFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """任务模式写文件(editor 以上;500ms 防抖由前端承担)"""
    project = await file_service.get_project_by_task(db, task_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await file_service.task_write_file(db, task_id, req.path, req.content)
    return success(message="保存成功")


@router.post("/tasks/{task_id}/files/operations")
async def task_file_operation(
    task_id: str,
    req: FileOperationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """文件操作 create/delete/rename/revert(editor 以上;revert=回滚该文件)"""
    project = await file_service.get_project_by_task(db, task_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await file_service.task_file_operation(db, task_id, req.operation, req.path, req.new_path)
    return success(message="操作成功")


@router.get("/tasks/{task_id}/files/diff")
async def task_file_diff(
    task_id: str,
    repo_path: str = Query(default="/workspace/main"),
    base_branch: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """逐文件 unified diff(任务工作台 Diff 视图)"""
    data = await file_service.task_git_diff(db, task_id, repo_path, base_branch)
    return success(data={"files": data})


@router.get("/tasks/{task_id}/files/changes")
async def task_file_changes(
    task_id: str,
    base_branch: str = Query(default="master"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Q27 变更清单:相对 base_branch 全部差异,按仓库分组(M/A/D/R + 行数)"""
    data = await file_service.task_git_changes(db, task_id, base_branch)
    return success(data=data)


# ---------------------------------------------------------------------------
# R28:头像文件公开访问(无需登录)
# ---------------------------------------------------------------------------
@router.get("/files/avatars/{filename}")
async def serve_avatar_file(filename: str):
    """
    头像文件公开访问(R28 验收 5:无需登录)。
    - 文件名 uuid4 随机生成,不可枚举
    - 严格白名单校验(uuid4 + jpg/jpeg/png/webp),路径遍历不可达
    - 文件已删除时返回 404(前端加载失败回退默认头像)
    """
    path = avatar_service.resolve_avatar_file(filename)
    if path is None or not path.is_file():
        return JSONResponse(status_code=404, content=error(404, "头像文件不存在"))
    media_type = avatar_service.MEDIA_TYPES.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


# ---------------------------------------------------------------------------
# WS:文件 watcher 频道 /ws/tasks/{task_id}/files
# ---------------------------------------------------------------------------
from fastapi import Query as _Query  # noqa: E402


@ws_router.websocket("/ws/tasks/{task_id}/files")
async def task_files_ws(
    websocket: WebSocket,
    task_id: str,
    token: str = _Query(default=""),
):
    """watcher 推送:Runner file_changed/file_deleted → 前端(平台侧注册表转发)"""
    import asyncio as _asyncio

    from app.api.terminal import _ws_current_user
    from app.database import async_session_factory
    from app.services.file_service import file_watcher_registry

    await websocket.accept()
    async with async_session_factory() as db:
        user = await _ws_current_user(db, token)
    if user is None:
        await websocket.close(code=4401)
        return

    conn = file_watcher_registry.connect(task_id, websocket)
    logger.info("文件 watcher 接入 task=%s user=%s", task_id, user.user_id)
    try:
        while True:
            # 仅保活;数据由 watcher 侧推送
            await _asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        file_watcher_registry.disconnect(task_id, conn)
