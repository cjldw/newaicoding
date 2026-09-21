"""文件服务 - R11(项目模式 GitLab API / 任务模式经 Runner 容器文件操作)"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.services import runner_service
from app.services.platform_settings_service import get_gitlab_bot_config
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 2 * 1024 * 1024  # 大文件 >2MB 只读/拒绝写入


# ---------------------------------------------------------------------------
# 任务 → 项目解析 + watcher 连接注册表
# ---------------------------------------------------------------------------
async def get_project_by_task(db: AsyncSession, task_id: str) -> Project:
    """经运行容器反查任务所属项目(R4 任务表落地前的定位方式)"""
    container = await _get_running_container(db, task_id)
    result = await db.execute(select(Project).where(Project.project_id == container.project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)
    return project


class FileWatcherRegistry:
    """task_id → 前端 watcher WS 连接集(内存)"""

    def __init__(self) -> None:
        self._conns: dict[str, set] = {}

    def connect(self, task_id: str, websocket) -> object:
        conn = {"ws": websocket, "task_id": task_id}
        self._conns.setdefault(task_id, set()).add(conn)
        return conn

    def disconnect(self, task_id: str, conn) -> None:
        conns = self._conns.get(task_id)
        if conns is not None:
            conns.discard(conn)
            if not conns:
                self._conns.pop(task_id, None)

    async def broadcast(self, task_id: str, payload: dict) -> int:
        conns = list(self._conns.get(task_id, set()))
        sent = 0
        for conn in conns:
            try:
                await conn["ws"].send_json(payload)
                sent += 1
            except Exception:
                self.disconnect(task_id, conn)
        return sent


file_watcher_registry = FileWatcherRegistry()


# ---------------------------------------------------------------------------
# Runner 定位
# ---------------------------------------------------------------------------
async def _get_running_container(db: AsyncSession, task_id: str) -> Container:
    result = await db.execute(
        select(Container).where(
            Container.task_id == task_id, Container.status == "running"
        ).order_by(Container.id.desc()).limit(1)
    )
    container = result.scalar_one_or_none()
    if container is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务无运行中的容器")
    conn = runner_registry.get(container.runner_id)
    if conn is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "Runner offline,文件服务暂不可用")
    return container


async def _request_container(db: AsyncSession, container: Container, message: dict) -> dict:
    """向 Runner 发文件指令并等待结果(超时/失败 → 9001)"""
    conn = runner_registry.get(container.runner_id)
    if conn is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "Runner offline,文件服务暂不可用")
    try:
        result = await runner_service.request_runner(conn, message, timeout=15.0)
    except TimeoutError:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "Runner 响应超时")
    if not result.get("ok"):
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, result.get("error") or "Runner 文件操作失败")
    return result.get("data") or {}


# ---------------------------------------------------------------------------
# 项目模式(GitLab API,bot token;只读)
# ---------------------------------------------------------------------------
async def _gitlab_ctx(db: AsyncSession, project: Project) -> tuple[str, str, ProjectRepo]:
    """(gitlab_url, bot_token, main repo);未配置 → 2001"""
    gitlab_url, bot_token, _ = await get_gitlab_bot_config(db)
    result = await db.execute(
        select(ProjectRepo).where(
            ProjectRepo.project_id == project.project_id, ProjectRepo.role == "main"
        )
    )
    main_repo = result.scalar_one_or_none()
    if main_repo is None:
        raise BizError(404, "项目未绑定主仓库", status_code=404)
    return gitlab_url, bot_token, main_repo


async def project_file_tree(db: AsyncSession, project: Project, branch: str, path: str) -> list[dict]:
    """GitLab repository/tree → 文件树"""
    from app.services import gitlab_service

    gitlab_url, bot_token, main_repo = await _gitlab_ctx(db, project)
    items = await gitlab_service.bot_get_tree(bot_token, gitlab_url, main_repo.gitlab_repo_id, branch, path)
    return [
        {
            "path": it.get("path", ""),
            "type": it.get("type", "blob"),
            "size": it.get("size", 0) or 0,
        }
        for it in items
    ]


async def project_file_content(db: AsyncSession, project: Project, branch: str, path: str) -> dict:
    """GitLab 文件内容(base64 → utf-8;二进制/超大拒绝)"""
    from app.services import gitlab_service

    gitlab_url, bot_token, main_repo = await _gitlab_ctx(db, project)
    data = await gitlab_service.bot_get_file(bot_token, gitlab_url, main_repo.gitlab_repo_id, branch, path)
    content = data.get("content", "")
    size = data.get("size", 0)
    if size and size > MAX_FILE_BYTES:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "文件超过 2MB,仅支持只读预览小文件")
    import base64

    try:
        text = base64.b64decode(content).decode("utf-8")
    except Exception:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "二进制文件不支持预览")
    return {"path": path, "content": text, "encoding": "utf-8"}


# ---------------------------------------------------------------------------
# 任务模式(容器文件,经 Runner)
# ---------------------------------------------------------------------------
async def task_file_list(db: AsyncSession, task_id: str, path: str) -> list[dict]:
    container = await _get_running_container(db, task_id)
    data = await _request_container(db, container, {
        "type": "file_list", "container_id": container.container_id, "path": path,
    })
    return data.get("items", [])


async def task_read_file(db: AsyncSession, task_id: str, path: str) -> dict:
    container = await _get_running_container(db, task_id)
    data = await _request_container(db, container, {
        "type": "read_file", "container_id": container.container_id, "path": path,
    })
    return {"path": path, "content": data.get("content", ""), "encoding": "utf-8"}


async def task_write_file(db: AsyncSession, task_id: str, path: str, content: str) -> None:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "文件超过 2MB,不支持在线编辑")
    container = await _get_running_container(db, task_id)
    await _request_container(db, container, {
        "type": "write_file", "container_id": container.container_id,
        "path": path, "content": content,
    })
    logger.info("文件保存 task=%s path=%s", task_id, path)


async def task_file_operation(db: AsyncSession, task_id: str, operation: str,
                              path: str, new_path: Optional[str] = None) -> None:
    """create/delete/rename/revert(revert = git checkout base_branch -- path,R4 精确化)"""
    container = await _get_running_container(db, task_id)
    if operation == "rename" and not new_path:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "重命名缺少 new_path")
    await _request_container(db, container, {
        "type": "file_op", "container_id": container.container_id,
        "operation": operation, "path": path, "new_path": new_path,
    })
    logger.info("文件操作 task=%s op=%s path=%s", task_id, operation, path)


async def task_git_diff(db: AsyncSession, task_id: str, repo_path: str = "/workspace/main",
                        base_branch: str = "") -> list[dict]:
    """逐文件 unified diff(任务工作台 Diff 视图)"""
    container = await _get_running_container(db, task_id)
    data = await _request_container(db, container, {
        "type": "git_diff", "container_id": container.container_id,
        "repo_path": repo_path, "base_branch": base_branch,
    })
    return data.get("files", [])


async def task_git_changes(db: AsyncSession, task_id: str, base_branch: str = "master") -> dict:
    """
    Q27 变更清单:每个挂载仓库执行 `git diff --numstat --name-status {base}`
    (工作树 vs base,含已 commit + 未 commit;git 口径不区分 AI/人)。
    按仓库分组返回,total 汇总。
    """
    container = await _get_running_container(db, task_id)

    # 该任务的仓库挂载点(R8 启动指令 repos[].path;台账从 project_repos + 约定 /workspace 推导)
    result = await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == container.project_id)
    )
    repos = result.scalars().all()
    repo_mounts = [(r.repo_id, r.role, f"/workspace/{r.role}" if r.role != "main" else "/workspace/main")
                   for r in repos]

    grouped: list[dict] = []
    total = 0
    for repo_id, role, mount in repo_mounts:
        try:
            data = await _request_container(db, container, {
                "type": "git_changes", "container_id": container.container_id,
                "repo_path": mount, "base_branch": base_branch,
            })
        except BizError:
            continue  # 仓库目录不存在(如未 clone)跳过
        files = data.get("files", [])
        total += len(files)
        grouped.append({"repo_id": repo_id, "repo_role": role, "files": files})

    return {"total": total, "repos": grouped}
