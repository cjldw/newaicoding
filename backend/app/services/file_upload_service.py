"""任务文件上传服务 - R4(限额校验/同名重命名/容器落盘/@引用解析)"""

import logging
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.task import Task, TaskUploadedFile
from app.services import file_service

logger = logging.getLogger(__name__)

SINGLE_FILE_LIMIT = 50 * 1024 * 1024        # 单文件 ≤ 50MB
SINGLE_BATCH_LIMIT = 10                      # 单次 ≤ 10 个
TOTAL_TASK_LIMIT = 200 * 1024 * 1024        # 单任务累计 ≤ 200MB
INJECT_THRESHOLD = 100 * 1024                # @引用:<100KB 注入内容,≥100KB 只给路径


async def _task_total_size(db: AsyncSession, task_id: str) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(TaskUploadedFile.size), 0)).where(
            TaskUploadedFile.task_id == task_id
        )
    )
    return int(result.scalar() or 0)


def _unique_stored_filename(existing: set[str], filename: str) -> str:
    """同名自动重命名 file.txt → file-1.txt → file-2.txt"""
    if filename not in existing:
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 1
    while f"{stem}-{i}{suffix}" in existing:
        i += 1
    return f"{stem}-{i}{suffix}"


async def save_upload(
    db: AsyncSession, task: Task, operator_user_id: str,
    filename: str, content: bytes, mime_type: str = "application/octet-stream",
) -> dict:
    """
    保存上传文件:
    1. 限额校验(4004/4005 由 API 层批量口径调用;此处 4004/4006)
    2. 同名重命名 → 写容器 /tmp/uploads/{task_id}/
    3. 写 task_uploaded_files 台账
    """
    if len(content) > SINGLE_FILE_LIMIT:
        raise BizError(ErrCode.TASK_FILE_TOO_LARGE, "文件大小超过 50MB")

    total = await _task_total_size(db, task.task_id)
    if total + len(content) > TOTAL_TASK_LIMIT:
        raise BizError(ErrCode.TASK_UPLOAD_TOTAL_LIMIT, "单任务累计上传超过 200MB")

    existing = set(
        (await db.execute(
            select(TaskUploadedFile.stored_filename).where(TaskUploadedFile.task_id == task.task_id)
        )).scalars().all()
    )
    safe_name = Path(filename).name  # 防路径穿越
    stored = _unique_stored_filename(existing, safe_name)
    container_path = f"/tmp/uploads/{task.task_id}/{stored}"

    # 写入容器(经 Runner;复用 R11 write_file 通道)
    await file_service.task_write_file_bytes(db, task.task_id, container_path, content)

    row = TaskUploadedFile(
        task_id=task.task_id,
        filename=safe_name,
        stored_filename=stored,
        size=len(content),
        mime_type=mime_type[:64] or "application/octet-stream",
        container_path=container_path,
        uploaded_by=operator_user_id,
    )
    db.add(row)
    await db.flush()
    logger.info("任务文件上传 task=%s file=%s size=%d", task.task_id, stored, len(content))
    return {
        "file_id": row.file_id,
        "filename": row.filename,
        "stored_filename": row.stored_filename,
        "size": row.size,
        "container_path": row.container_path,
    }


async def resolve_file_refs(db: AsyncSession, task_id: str, content: str) -> tuple[str, list[dict]]:
    """
    解析 @filename 引用:
    - <100KB:读取内容注入 prompt(File: ... 块)
    - ≥100KB:只注入路径
    返回 (增强后的 prompt, file_refs)。
    """
    refs: list[dict] = []
    mentioned = re.findall(r"@([^\s@,。;:)》]+)", content)
    if not mentioned:
        return content, refs

    rows = (await db.execute(
        select(TaskUploadedFile).where(TaskUploadedFile.task_id == task_id)
    )).scalars().all()
    by_name = {r.filename: r for r in rows}
    by_stored = {r.stored_filename: r for r in rows}

    prompt_blocks: list[str] = []
    for name in mentioned:
        row = by_name.get(name) or by_stored.get(name)
        if row is None:
            continue
        injected = row.size < INJECT_THRESHOLD
        if injected:
            try:
                file_content = await file_service.task_read_file_bytes(db, task_id, row.container_path)
            except Exception:
                logger.warning("引用文件读取失败 task=%s file=%s", task_id, row.filename)
                injected = False
                file_content = ""
        if injected:
            prompt_blocks.append(f"File: {row.filename}\n```\n{file_content}\n```")
        else:
            prompt_blocks.append(
                f"File: {row.filename} (size: {row.size} bytes)\nPath: {row.container_path}"
            )
        refs.append({
            "file_id": row.file_id,
            "filename": row.filename,
            "container_path": row.container_path,
            "injected": injected,
        })

    if not prompt_blocks:
        return content, refs

    enhanced = content + "\n\n---\n" + "\n\n---\n".join(prompt_blocks) + "\n---"
    return enhanced, refs
