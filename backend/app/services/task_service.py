"""任务服务 - R4(任务生命周期 + 对话 + 事件流)

任务类型:requirement(打磨)/ dev / test / release。
- 创建:需求状态校验(4001)→ 创建者 GitLab token 校验(4002)→ 并发 ≤3(4003)
  → 调度拉起容器(R8)→ pending→running
- 对话:@file 引用解析注入(<100KB 内容/≥100KB 路径)→ Claude CLI 兜底执行(R13 配置)
  → task_messages 台账 + 活动流事件
- 结束:全仓库 commit+push(创建者 token)→ done → 容器销毁(销毁前强制 push 在 Runner)
- 事件:WS /ws/tasks/{tid}/events(tool_call/status_changed)
"""

import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task, TaskMessage, TaskUploadedFile
from app.models.user import User
from app.services import claude_service, container_service, runner_service
from app.services.runner_service import runner_registry

logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNNING = 3        # 单项目并发 running 任务 ≤ 3
TASK_TIMEOUT_MINUTES = 60         # 单任务最长 60 分钟(超时兜底)
COMMIT_AUTHOR_FALLBACK = ("ai", "ai@qicheng.local")

# 允许的任务类型 → 需求状态前置
_TYPE_REQ_STATUS = {
    "dev": {"approved"},
    "test": {"approved", "in_progress"},
    "release": {"approved", "in_progress"},
}


# ---------------------------------------------------------------------------
# 打磨任务(R3;Q26 PRD 路径生成)
# ---------------------------------------------------------------------------
def build_prd_path(title: str, task_id: str, date: Optional[datetime] = None) -> str:
    """
    Q26:docs/{YYYYMMDD}_{descSlug}_{taskShortId}/PRD.md
    YYYYMMDD=任务创建日期;descSlug=标题 slug(保留中文,空格/特殊字符转 -,≤32);
    taskShortId=任务 uuid 前 8 位。
    """
    slug = re.sub(r"[^\w一-鿿-]+", "-", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:32] or "需求"
    date = date or datetime.now()
    return f"docs/{date.strftime('%Y%m%d')}_{slug}_{task_id[:8]}/PRD.md"


async def create_polish_task(db: AsyncSession, project: Project, requirement: Requirement,
                             operator: User) -> str:
    """
    创建并启动打磨任务(type=requirement):
    - 模型配置校验(R13;未配置 13005)
    - 组装 env(模型/GitLab token/任务上下文)与 repos 挂载(req_branch)
    - 调度拉起容器(R8)
    """
    from app.services import llm_service
    from app.services.platform_settings_service import get_setting

    llm_config = await llm_service.resolve_config(db, project.project_id)
    gitlab_url = await get_setting(db, "gitlab_url") or ""
    bot_token = (await get_setting(db, "gitlab_bot_token")) or ""

    task_id = str(uuid.uuid4())

    from app.models.project import ProjectRepo

    repos = []
    for repo in (await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == project.project_id)
    )).scalars().all():
        mount = "/workspace/main" if repo.role == "main" else f"/workspace/{repo.role}"
        repos.append({"url": repo.gitlab_repo_url, "path": mount, "branch": requirement.req_branch})

    env = {
        "GITLAB_TOKEN": bot_token,
        "GITLAB_INSTANCE_URL": gitlab_url,
        "LLM_BASE_URL": llm_config["base_url"],
        "LLM_API_KEY": llm_config["api_key"],
        "LLM_MODEL": llm_config["model"],
        "ANTHROPIC_BASE_URL": llm_config["base_url"],
        "ANTHROPIC_API_KEY": llm_config["api_key"],
        "TASK_ID": task_id,
        "PROJECT_ID": project.project_id,
        "REQ_ID": requirement.req_id,
        "PRD_FILE_PATH": build_prd_path(requirement.title, task_id),
    }

    await container_service.schedule_and_start(
        db,
        project_id=project.project_id,
        task_id=task_id,
        owner_user_id=requirement.created_by,
        env=env,
        repos=repos,
    )
    return task_id


# ---------------------------------------------------------------------------
# R5:测试驳回回开发
# ---------------------------------------------------------------------------
async def reject_to_dev(db: AsyncSession, test_task: Task, operator: User,
                        title: str, description: str) -> Task:
    """
    测试驳回创建修复 dev 任务:
    - 读测试任务 extended_attributes(test_cases 失败用例 / report_file_path 测试报告路径)
    - 新 dev 任务 extended_attributes 填 related_test_task_id + fix_context
    - 首条用户消息发送时 prompt 自动携带 fix_context(send_message 注入)
    """
    ext = test_task.extended_attributes or {}
    test_cases = ext.get("test_cases") or []
    report_path = ext.get("report_file_path") or ""

    lines = []
    if test_cases:
        lines.append("失败用例:")
        if isinstance(test_cases, list):
            for i, case in enumerate(test_cases, 1):
                name = case.get("name") if isinstance(case, dict) else str(case)
                result = case.get("result", "") if isinstance(case, dict) else ""
                lines.append(f"{i}. {name}{(':' + result) if result else ''}")
        else:
            lines.append(str(test_cases))
    if report_path:
        lines.append(f"测试报告: {report_path}")
    fix_context = "\n".join(lines)

    requirement = (await db.execute(
        select(Requirement).where(Requirement.req_id == test_task.req_id)
    )).scalars().first()
    if requirement is None:
        raise BizError(404, "原需求不存在", status_code=404)
    project = (await db.execute(
        select(Project).where(Project.project_id == test_task.project_id)
    )).scalars().first()
    if project is None:
        raise BizError(404, "项目不存在", status_code=404)

    task = Task(
        req_id=test_task.req_id,
        project_id=test_task.project_id,
        type="dev",
        title=title,
        description=description,
        base_branch=test_task.base_branch,
        work_branch=test_task.work_branch,
        status="pending",
        created_by=operator.user_id,
        extended_attributes={
            "related_test_task_id": test_task.task_id,
            "fix_context": fix_context,
        },
    )
    db.add(task)
    await db.flush()
    logger.info("测试驳回回开发 test=%s → dev=%s by=%s", test_task.task_id, task.task_id, operator.user_id)
    return task


def _fix_context_block(task: Task) -> str:
    """首条消息注入的修复上下文块(dev + 有 fix_context 时)"""
    if task.type != "dev":
        return ""
    ext = task.extended_attributes or {}
    fix = ext.get("fix_context")
    if not fix:
        return ""
    return f"【修复上下文】请优先修复以下测试失败问题:\n{fix}\n---\n"


# ---------------------------------------------------------------------------
# 事件流注册表(WS /ws/tasks/{tid}/events)
# ---------------------------------------------------------------------------
class TaskEventRegistry:
    """task_id → 前端事件 WS 连接集(内存)"""

    def __init__(self) -> None:
        self._conns: dict[str, set] = {}

    def connect(self, task_id: str, websocket):
        conn = {"ws": websocket, "task_id": task_id}
        self._conns.setdefault(task_id, set()).add(conn)
        return conn

    def disconnect(self, task_id: str, conn) -> None:
        conns = self._conns.get(task_id)
        if conns is not None:
            conns.discard(conn)

    async def broadcast(self, task_id: str, payload: dict) -> int:
        sent = 0
        for conn in list(self._conns.get(task_id, set())):
            try:
                await conn["ws"].send_json(payload)
                sent += 1
            except Exception:
                self.disconnect(task_id, conn)
        return sent


task_event_registry = TaskEventRegistry()


async def emit_event(db: AsyncSession, task_id: str, payload: dict) -> None:
    """广播任务事件(活动流);持久化由调用方按需写 task_messages"""
    await task_event_registry.broadcast(task_id, payload)


# ---------------------------------------------------------------------------
# 查询/定位
# ---------------------------------------------------------------------------
async def get_task_or_404(db: AsyncSession, task_id: str) -> Task:
    result = await db.execute(select(Task).where(Task.task_id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise BizError(404, "任务不存在", status_code=404)
    return task


async def _creator_brief(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == user_id))
    u = result.scalar_one_or_none()
    return {
        "user_id": user_id,
        "username": (u.gitlab_username or "") if u else "",
        "nickname": u.nickname if u else None,
    }


def task_brief(task: Task) -> dict:
    return {
        "task_id": task.task_id,
        "type": task.type,
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


# ---------------------------------------------------------------------------
# 创建任务
# ---------------------------------------------------------------------------
async def create_task(
    db: AsyncSession, requirement: Requirement, project: Project, operator: User,
    type: str, title: str, description: str,
    base_branch: Optional[str] = None, work_branch: Optional[str] = None,
) -> Task:
    """
    创建任务(不拉容器,先落 pending;容器由 start 阶段拉起,支持排队):
    1. 需求状态前置(4001):dev 要求 approved;test/release 要求 approved/in_progress
    2. 创建者 GitLab token(4002)
    3. 单项目并发 running ≤3(4003)
    """
    logger.info("创建任务 req=%s type=%s by=%s", requirement.req_id, type, operator.user_id)

    # 4001 需求状态前置(requirement 类型不经此入口,走 start_polish)
    allowed = _TYPE_REQ_STATUS.get(type)
    if allowed is None or requirement.status not in allowed:
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "需求状态不允许创建该类型任务")

    # 4002 创建者 GitLab token
    if not operator.gitlab_token_encrypted:
        raise BizError(ErrCode.TASK_NO_GITLAB_TOKEN, "请到个人设置绑定 GitLab token")

    # 4003 单项目并发 running ≤3
    cnt = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project.project_id,
            Task.status == "running",
        )
    )
    if (cnt.scalar() or 0) >= MAX_CONCURRENT_RUNNING:
        raise BizError(ErrCode.TASK_CONCURRENT_LIMIT, "项目并发任务数已达上限(3个)")

    task = Task(
        req_id=requirement.req_id,
        project_id=project.project_id,
        type=type,
        title=title,
        description=description,
        base_branch=base_branch or requirement.req_branch,
        work_branch=work_branch or base_branch or requirement.req_branch,
        status="pending",
        created_by=operator.user_id,
    )
    db.add(task)
    await db.flush()
    logger.info("任务已创建 task=%s type=%s", task.task_id, type)
    return task


async def start_task(db: AsyncSession, task: Task, project: Project, requirement: Requirement) -> None:
    """
    拉起任务容器(pending → running):
    组装 env(R13 模型配置 + GitLab token + 任务上下文)与 repos 挂载,
    经 container_service 调度;无可用 Runner 抛 8003(前端显示等待)。
    """
    if task.status != "pending":
        return

    from app.services import llm_service

    llm_config = await llm_service.resolve_config(db, project.project_id)

    from app.models.project import ProjectRepo
    from app.services.platform_settings_service import get_setting

    gitlab_url = await get_setting(db, "gitlab_url") or ""
    bot_token = (await get_setting(db, "gitlab_bot_token")) or ""

    repos = []
    for repo in (await db.execute(
        select(ProjectRepo).where(ProjectRepo.project_id == project.project_id)
    )).scalars().all():
        mount = "/workspace/main" if repo.role == "main" else f"/workspace/{repo.role}"
        repos.append({"url": repo.gitlab_repo_url, "path": mount, "branch": task.work_branch})

    env = {
        "GITLAB_TOKEN": bot_token,
        "GITLAB_INSTANCE_URL": gitlab_url,
        "LLM_BASE_URL": llm_config["base_url"],
        "LLM_API_KEY": llm_config["api_key"],
        "LLM_MODEL": llm_config["model"],
        "ANTHROPIC_BASE_URL": llm_config["base_url"],
        "ANTHROPIC_API_KEY": llm_config["api_key"],
        "TASK_ID": task.task_id,
        "PROJECT_ID": project.project_id,
        "REQ_ID": requirement.req_id,
    }

    await container_service.schedule_and_start(
        db,
        project_id=project.project_id,
        task_id=task.task_id,
        owner_user_id=requirement.created_by,
        env=env,
        repos=repos,
    )

    task.status = "running"
    task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "running"})
    logger.info("任务容器已调度 task=%s", task.task_id)


# ---------------------------------------------------------------------------
# 对话
# ---------------------------------------------------------------------------
async def send_message(db: AsyncSession, task: Task, operator: User, content: str) -> dict:
    """
    发送消息:保存 user 消息(@file 注入)→ Claude CLI 兜底执行 → 保存 assistant
    消息 → 广播活动流。返回 user message_id。
    """
    from app.services import file_upload_service

    # @file 引用解析与注入
    enhanced_prompt, file_refs = await file_upload_service.resolve_file_refs(db, task.task_id, content)

    # R5:修复任务首条消息自动携带 fix_context
    has_prior_user = (await db.execute(
        select(func.count(TaskMessage.id)).where(
            TaskMessage.task_id == task.task_id, TaskMessage.role == "user"
        )
    )).scalar() or 0
    fix_block = _fix_context_block(task) if has_prior_user == 0 else ""
    if fix_block:
        enhanced_prompt = fix_block + enhanced_prompt

    user_msg = TaskMessage(
        task_id=task.task_id, role="user", content=content, file_refs=file_refs or None,
    )
    db.add(user_msg)
    await db.flush()

    # 定位运行容器与 Runner 连接
    container = (await db.execute(
        select(Container).where(
            Container.task_id == task.task_id, Container.status == "running"
        ).order_by(Container.id.desc()).limit(1)
    )).scalars().first()
    if container is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务容器不在运行,无法执行 AI 会话")
    runner_conn = runner_registry.get(container.runner_id)
    if runner_conn is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "Runner offline,AI 会话暂不可用")

    started = time.monotonic()
    try:
        response = await claude_service.run_prompt(runner_conn, container.container_id, enhanced_prompt)
    except RuntimeError as e:
        # 执行失败:assistant 错误消息 + 事件
        err = TaskMessage(task_id=task.task_id, role="assistant", content=f"执行失败:{e}")
        db.add(err)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "tool_call", "name": "claude", "error": str(e)})
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, f"AI 执行失败:{e}")

    duration_ms = int((time.monotonic() - started) * 1000)

    ai_msg = TaskMessage(
        task_id=task.task_id, role="assistant", content=response["result"],
        tokens_in=response["tokens_in"], tokens_out=response["tokens_out"],
    )
    db.add(ai_msg)

    task.total_tokens_in += response["tokens_in"]
    task.total_tokens_out += response["tokens_out"]
    await db.flush()

    await task_event_registry.broadcast(task.task_id, {
        "type": "tool_call", "name": "claude_prompt", "duration_ms": duration_ms,
        "result": response["result"][:500],
    })
    logger.info("任务消息完成 task=%s tokens=%d/%d", task.task_id, response["tokens_in"], response["tokens_out"])
    return {"message_id": user_msg.message_id}


# ---------------------------------------------------------------------------
# 结束:完成 / 停止 / 重试 / 超时
# ---------------------------------------------------------------------------
async def finish_task(db: AsyncSession, task: Task, operator: User, status: str = "done") -> None:
    """
    完成任务:所有仓库 git add -A + commit([ai:type] title)+ push(创建者 token)
    → status=done → 容器销毁(销毁前强制 push 由 Runner 兜底)。
    """
    container = (await db.execute(
        select(Container).where(
            Container.task_id == task.task_id, Container.status == "running"
        ).order_by(Container.id.desc()).limit(1)
    )).scalars().first()

    if container is not None:
        runner_conn = runner_registry.get(container.runner_id)
        creator = (await db.execute(
            select(User).where(User.user_id == task.created_by)
        )).scalars().first()
        creator_token = ""
        if creator is not None and creator.gitlab_token_encrypted:
            from app.core.encryption import decrypt_token

            creator_token = decrypt_token(creator.gitlab_token_encrypted)

        if runner_conn is not None and creator_token:
            from app.models.project import ProjectRepo

            repos = (await db.execute(
                select(ProjectRepo).where(ProjectRepo.project_id == task.project_id)
            )).scalars().all()
            for repo in repos:
                mount = "/workspace/main" if repo.role == "main" else f"/workspace/{repo.role}"
                try:
                    await runner_service.request_runner(runner_conn, {
                        "type": "git_commit",
                        "container_id": container.container_id,
                        "repo_path": mount,
                        "add_path": ".",
                        "message": f"[ai:{task.type}] {task.title}",
                        "branch": task.work_branch,
                        "token": creator_token,
                    }, timeout=60.0)
                except Exception as e:
                    logger.warning("仓库 commit/push 失败 task=%s repo=%s: %s", task.task_id, mount, e)

        # 销毁容器(停止指令;Runner 销毁前强制 push 未 push commit)
        await container_service.request_stop(db, container)

    task.status = status
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if status == "cancelled":
        task.error_message = "用户手动停止"
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": status})
    logger.info("任务结束 task=%s status=%s", task.task_id, status)


async def retry_task(db: AsyncSession, task: Task) -> None:
    """重试任务:failed/cancelled/timeout → pending(等待重新拉起)"""
    if task.status not in ("failed", "cancelled", "timeout"):
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "当前状态不可重试")
    task.status = "pending"
    task.error_message = None
    task.finished_at = None
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "pending"})


async def sweep_timeouts(db: AsyncSession) -> int:
    """超时兜底:running 超 60 分钟 → timeout(销毁由 stop 指令)"""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=TASK_TIMEOUT_MINUTES)
    result = await db.execute(
        select(Task).where(Task.status == "running", Task.started_at.isnot(None), Task.started_at < threshold)
    )
    count = 0
    for task in result.scalars():
        task.status = "timeout"
        task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        task.error_message = "任务超时(60 分钟)"
        container = (await db.execute(
            select(Container).where(
                Container.task_id == task.task_id, Container.status == "running"
            ).limit(1)
        )).scalars().first()
        if container is not None:
            await container_service.request_stop(db, container)
        count += 1
    if count:
        await db.flush()
        logger.info("任务超时清理 %d 个", count)
    return count
