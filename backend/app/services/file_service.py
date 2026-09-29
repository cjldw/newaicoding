"""文件服务 - R11(项目模式 GitLab API / 任务模式经 Runner 容器文件操作)"""

import base64
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.task import Task
from app.services import runner_service
from app.services.audit_service import audit_write
from app.services.platform_settings_service import get_gitlab_bot_config, get_setting
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
async def resolve_task_base_branch(db: AsyncSession, container: Container, task_id: str,
                                  explicit: Optional[str]) -> str:
    """BUG-074:Diff/变更基线解析——显式参 > task.base_branch(非自指) > 项目默认分支。

    存量任务创建时 base_branch 被写成 work_branch 自指(git diff 自己 = 恒空
    「没有对比效果」),这类任务回退项目默认分支(需求分支从 default_branch
    切出,diff 它 = 本任务全部改动,含已 commit + 未 commit)。
    """
    if explicit:
        return explicit
    result = await db.execute(select(Task).where(Task.task_id == task_id))
    task = result.scalar_one_or_none()
    if task is not None and task.base_branch and task.base_branch != task.work_branch:
        return task.base_branch
    proj = await db.execute(select(Project).where(Project.project_id == container.project_id))
    project = proj.scalar_one_or_none()
    if project is not None and project.default_branch:
        return project.default_branch
    return "master"


async def task_file_list(db: AsyncSession, task_id: str, path: str) -> list[dict]:
    container = await _get_running_container(db, task_id)
    data = await _request_container(db, container, {
        "type": "file_list", "container_id": container.container_id, "path": path,
    })
    items = data.get("items", [])
    # 防御归一化:旧 runner 镜像可能返回 type="tree",统一归一为 "dir"(前端 FileItem 契约)
    for item in items:
        if item.get("type") == "tree":
            item["type"] = "dir"
    return items


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


# ---------------------------------------------------------------------------
# 字节流变体(R4 任务附件上传/下载;base64 通道,不受 2MB 编辑限制)
# ---------------------------------------------------------------------------
async def task_write_file_bytes(db: AsyncSession, task_id: str, path: str, content: bytes) -> None:
    """容器写任意字节文件(base64 通道)"""
    import base64

    container = await _get_running_container(db, task_id)
    b64 = base64.b64encode(content).decode("ascii")
    await _request_container(db, container, {
        "type": "write_file_b64", "container_id": container.container_id,
        "path": path, "content_b64": b64,
    })


async def task_read_file_bytes(db: AsyncSession, task_id: str, path: str) -> bytes:
    """容器读任意字节文件(base64 通道)"""
    import base64

    container = await _get_running_container(db, task_id)
    data = await _request_container(db, container, {
        "type": "read_file_b64", "container_id": container.container_id, "path": path,
    })
    return base64.b64decode(data.get("content_b64", ""))


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
                        base_branch: str = "", scope: str = "all") -> list[dict]:
    """逐文件 unified diff(任务工作台 Diff 视图;BUG-074:基线经 resolve_task_base_branch 解析)

    R38:scope=head → base 固定 "HEAD"(跳过 resolve_task_base_branch,不查任务/项目);
        scope=all/缺省 → 现状 R4.F7 解析链。
    """
    container = await _get_running_container(db, task_id)
    if scope == "head":
        base = "HEAD"
    else:
        base = await resolve_task_base_branch(db, container, task_id, base_branch or None)
    logger.info("task_git_diff task=%s scope=%s base=%s", task_id, scope, base)
    data = await _request_container(db, container, {
        "type": "git_diff", "container_id": container.container_id,
        "repo_path": repo_path, "base_branch": base,
    })
    return data.get("files", [])


async def task_git_changes(db: AsyncSession, task_id: str, base_branch: str = "master",
                           scope: str = "all") -> dict:
    """
    Q27 变更清单:每个挂载仓库执行 `git diff --numstat --name-status {base}`
    (工作树 vs base,含已 commit + 未 commit;git 口径不区分 AI/人)。
    按仓库分组返回,total 汇总。

    R38:scope=head → base 固定 "HEAD"(跳过 resolve_task_base_branch,不查任务/项目);
        scope=all/缺省 → 现状 R4.F7 解析链。
    """
    container = await _get_running_container(db, task_id)
    if scope == "head":
        base = "HEAD"
    else:
        # BUG-074:基线解析(原默认硬编码 "master",不看任务/项目实际基线)
        base = await resolve_task_base_branch(db, container, task_id, base_branch or None)
    logger.info("task_git_changes task=%s scope=%s base=%s", task_id, scope, base)

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
                "repo_path": mount, "base_branch": base,
            })
        except BizError:
            continue  # 仓库目录不存在(如未 clone)跳过
        files = data.get("files", [])
        total += len(files)
        grouped.append({"repo_id": repo_id, "repo_role": role, "files": files})

    return {"total": total, "repos": grouped}


# ---------------------------------------------------------------------------
# R39:任务 git commit / push(经 Runner;身份回退链)
# ---------------------------------------------------------------------------
async def _resolve_commit_identity(operator, gitlab_token: str, gitlab_url: str) -> dict:
    """
    R39 身份解析链(实时取,不落库):
      name:  /user name → gitlab_username → 手机号
      email: /user email → {gitlab_username}@zhanqi.com → {手机号}@zhanqi.com
    /user 调用失败(网络/1012)→ 直接走回退链不阻塞。
    返回 {name, email, gitlab_username}。
    """
    from app.services import gitlab_service

    profile: dict = {}
    if gitlab_token:
        try:
            profile = await gitlab_service.get_user_profile(gitlab_token, api_base=gitlab_url)
        except Exception as e:
            logger.warning("R39 get_user_profile 失败(走回退链): %s", e)

    gitlab_username = (profile.get("username") or "") or (getattr(operator, "gitlab_username", "") or "")
    phone = getattr(operator, "phone", "") or ""

    # name 回退链
    name = profile.get("name") or gitlab_username or phone
    # email 回退链
    email = profile.get("email") or ""
    if not email:
        if gitlab_username:
            email = f"{gitlab_username}@zhanqi.com"
        elif phone:
            email = f"{phone}@zhanqi.com"

    return {"name": name, "email": email, "gitlab_username": gitlab_username}


def _task_repo_mounts(project_id: str, repos: list) -> list[tuple[str, str, str]]:
    """
    仓库挂载清单(与 task_git_changes / 收尾链同口径):
    返回 [(repo_id, role, mount_path), ...]
    """
    result = []
    for r in repos:
        mount = "/workspace/main" if r.role == "main" else f"/workspace/{r.role}"
        result.append((r.repo_id, r.role, mount))
    return result


async def task_git_commit(db: AsyncSession, task_id: str, message: str, operator) -> dict:
    """
    R39:任务 git commit(全部挂载仓库,逐仓库执行)。
    返回 {message, commit, author_name, author_email}。
    无变更 → BizError(2015);单仓库失败即中断(已成功仓库不回滚,错误文案列出已提交仓库)。
    """
    container = await _get_running_container(db, task_id)

    # 任务 + 仓库清单
    task_row = (await db.execute(select(Task).where(Task.task_id == task_id))).scalar_one_or_none()
    if task_row is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务不存在")
    repos = (await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == container.project_id)
    )).scalars().all()
    if not repos:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务无挂载仓库")

    # 操作者 GitLab token(解密失败/未绑定 → 1012)
    if not operator.gitlab_token_encrypted:
        raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "请到个人设置绑定 GitLab token")
    from app.core.encryption import decrypt_token
    try:
        gitlab_token = decrypt_token(operator.gitlab_token_encrypted)
    except Exception:
        raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "GitLab token 解密失败,请重新绑定")

    gitlab_url = (await get_setting(db, "gitlab_url")) or ""

    # 身份解析
    identity = await _resolve_commit_identity(operator, gitlab_token, gitlab_url)

    # 默认 message
    if not message:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        short_id = (task_row.task_id or "")[:7]
        message = f"AI 任务变更 {short_id} {now_str}"

    # 逐仓库 commit
    repo_mounts = _task_repo_mounts(container.project_id, repos)
    committed_repos: list[str] = []
    main_commit = ""
    for repo_id, role, mount in repo_mounts:
        msg_b64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
        try:
            data = await _request_container(db, container, {
                "type": "git_commit",
                "container_id": container.container_id,
                "repo_path": mount,
                "message_b64": msg_b64,
                "author_name_b64": base64.b64encode(identity["name"].strip().encode("utf-8")).decode("ascii"),
                "author_email_b64": base64.b64encode(identity["email"].strip().encode("utf-8")).decode("ascii"),
            })
        except BizError as e:
            # 单仓库失败 → 中断;已成功仓库不回滚(git 语义)
            committed_info = f"(已提交仓库:{','.join(committed_repos)})" if committed_repos else ""
            raise BizError(e.code, f"仓库 {mount} 提交失败:{e.message}{committed_info}")

        commit_val = (data or {}).get("commit", "")
        if commit_val == "none":
            # 无变更 → 2015(只在主仓库/首个仓库触发;后续仓库若也无变更同样 2015)
            raise BizError(ErrCode.GIT_NO_CHANGES, "无变更可提交")
        if commit_val:
            if role == "main" or not main_commit:
                main_commit = commit_val
        committed_repos.append(mount)

    # 审计(操作人/任务/仓库/结果;不记 token)
    await audit_write(
        db, operator, "git.commit",
        project_id=container.project_id,
        target_type="task", target_id=task_id,
        detail={"repos": committed_repos, "commit": main_commit,
                "author_name": identity["name"], "author_email": identity["email"]},
    )

    return {
        "message": "提交成功",
        "commit": main_commit,
        "author_name": identity["name"],
        "author_email": identity["email"],
    }


async def task_git_push(db: AsyncSession, task_id: str, operator) -> dict:
    """
    R39:任务 git push(全部挂载仓库,逐仓库 push work_branch)。
    返回 {message, branch}。
    远端拒绝(非 fast-forward 等)→ 2014 + 上游输出截断 ≤300 字符。
    """
    container = await _get_running_container(db, task_id)

    task_row = (await db.execute(select(Task).where(Task.task_id == task_id))).scalar_one_or_none()
    if task_row is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务不存在")
    branch = task_row.work_branch

    repos = (await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == container.project_id)
    )).scalars().all()
    if not repos:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务无挂载仓库")

    # 操作者 GitLab token
    if not operator.gitlab_token_encrypted:
        raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "请到个人设置绑定 GitLab token")
    from app.core.encryption import decrypt_token
    try:
        gitlab_token = decrypt_token(operator.gitlab_token_encrypted)
    except Exception:
        raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "GitLab token 解密失败,请重新绑定")

    repo_mounts = _task_repo_mounts(container.project_id, repos)
    pushed_repos: list[str] = []
    for repo_id, role, mount in repo_mounts:
        try:
            data = await _request_container(db, container, {
                "type": "git_push",
                "container_id": container.container_id,
                "repo_path": mount,
                "branch": branch,
                "token": gitlab_token,
            })
        except BizError as e:
            # 1013 scope 不足 / 2014 远端拒绝(非 fast-forward 等)
            # runner 侧会将上游输出截断 ≤300 字符放在 error 字段
            if e.code in (ErrCode.GITLAB_SCOPE_INSUFFICIENT, ErrCode.GITLAB_UNREACHABLE):
                raise
            # 其他 runner 错误 → 2014 类(GitLab 操作失败)
            upstream = (e.message or "")[:300]
            raise BizError(ErrCode.GITLAB_UNREACHABLE, f"GitLab 操作失败:{upstream}")
        pushed_repos.append(mount)

    # 审计
    await audit_write(
        db, operator, "git.push",
        project_id=container.project_id,
        target_type="task", target_id=task_id,
        detail={"repos": pushed_repos, "branch": branch},
    )

    return {"message": "推送成功", "branch": branch}
