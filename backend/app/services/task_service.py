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
from app.services import claude_service, container_service, mcp_service, runner_service, skill_service
from app.services.audit_service import audit_write, spawn_audit_write  # R25 审计接入
from app.database import async_session_factory
from app.services.auth_service import AUDIT_PLACEHOLDER_USER_ID as AUDIT_SYSTEM_USER_ID
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
    R3.F1(BUG-035)修复:原实现只生成 task_id 直接拉容器,**从不落 tasks 行**——
    前端跳转 /tasks/{id} 404、BUG-030 容器回填落空、四维列表不可见。
    现对齐 create_task+start_task 口径:先落 Task 行(pending),调度成功后置 running。
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
        # R8.F4(BUG-036):平台自定义变量铺底,系统键后置覆盖(保存校验已拒冲突,双保险)
        **(await get_setting(db, "custom_env_vars") or {}),
        "GITLAB_TOKEN": bot_token,
        "GITLAB_INSTANCE_URL": gitlab_url,
        # 容器内回环 host 改写:127.0.0.1 在容器内指向容器自身(BUG-034)
        "LLM_BASE_URL": llm_service.container_base_url(llm_config["base_url"]),
        "LLM_API_KEY": llm_config["api_key"],
        "LLM_MODEL": llm_config["model"],
        # R8.F4:LLM_URL 别名(容器内脚本按此取名)
        "LLM_URL": llm_service.container_base_url(llm_config["base_url"]),
        "ANTHROPIC_BASE_URL": llm_service.container_base_url(llm_config["base_url"]),
        "ANTHROPIC_API_KEY": llm_config["api_key"],
        # claude CLI 不读 LLM_MODEL,读 ANTHROPIC_MODEL(缺失时请求内置默认
        # claude-opus-5-5,网关无此渠道 → 503;E2E 实证)
        "ANTHROPIC_MODEL": llm_config["model"],
        "TASK_ID": task_id,
        "PROJECT_ID": project.project_id,
        "REQ_ID": requirement.req_id,
        "PRD_FILE_PATH": build_prd_path(requirement.title, task_id),
    }

    # R3.F1(BUG-035):先落 Task 行(pending),再调度容器——
    # 容器调度失败(8003 等)时事务回滚,任务行不落库,与 create_task+start_task 失败语义一致
    task = Task(
        task_id=task_id,
        req_id=requirement.req_id,
        project_id=project.project_id,
        type="requirement",
        title=f"需求打磨:{requirement.title}",
        description=requirement.description or requirement.title,
        base_branch=requirement.req_branch,
        work_branch=requirement.req_branch,
        status="pending",
        created_by=operator.user_id,
    )
    db.add(task)
    await db.flush()

    await container_service.schedule_and_start(
        db,
        project_id=project.project_id,
        task_id=task_id,
        owner_user_id=requirement.created_by,
        env=env,
        repos=repos,
        # R32:打磨任务固定 requirement 专属匹配(未打 requirement 标的通用 Runner 兜底可接)
        task_tag="requirement",
    )
    # 调度成功即运行(打磨容器与 start_task 同口径置 running)
    task.status = "running"
    task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    logger.info("打磨任务已创建并调度 task=%s req=%s", task_id, requirement.req_id)
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

    # 回环:原测试任务记录驳回产生的 dev 任务 id(R6)
    ext = dict(test_task.extended_attributes or {})
    ext["rejected_to_dev_task_id"] = task.task_id
    test_task.extended_attributes = ext  # 新 dict 对象,确保触发 UPDATE

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
        # R8.F4(BUG-036):平台自定义变量铺底,系统键后置覆盖(保存校验已拒冲突,双保险)
        **(await get_setting(db, "custom_env_vars") or {}),
        "GITLAB_TOKEN": bot_token,
        "GITLAB_INSTANCE_URL": gitlab_url,
        # 容器内回环 host 改写:127.0.0.1 在容器内指向容器自身(BUG-034)
        "LLM_BASE_URL": llm_service.container_base_url(llm_config["base_url"]),
        "LLM_API_KEY": llm_config["api_key"],
        "LLM_MODEL": llm_config["model"],
        # R8.F4:LLM_URL 别名(容器内脚本按此取名)
        "LLM_URL": llm_service.container_base_url(llm_config["base_url"]),
        "ANTHROPIC_BASE_URL": llm_service.container_base_url(llm_config["base_url"]),
        "ANTHROPIC_API_KEY": llm_config["api_key"],
        # claude CLI 不读 LLM_MODEL,读 ANTHROPIC_MODEL(缺失时请求内置默认
        # claude-opus-5-5,网关无此渠道 → 503;E2E 实证)
        "ANTHROPIC_MODEL": llm_config["model"],
        "TASK_ID": task.task_id,
        "PROJECT_ID": project.project_id,
        "REQ_ID": requirement.req_id,
    }

    # R7:发布任务固定在 deploy Runner(R16 role=deploy)
    required_role = "deploy" if task.type == "release" else "worker"
    # R32:任务类型标签透传调度(requirement/dev/test 参与专属匹配;release 不参与 tag)
    # 枚举单源:复用 runner_service.ALLOWED_TASK_TAGS,防止两处硬编码漂移(code-review #1)
    task_tag = task.type if task.type in runner_service.ALLOWED_TASK_TAGS else None
    await container_service.schedule_and_start(
        db,
        project_id=project.project_id,
        task_id=task.task_id,
        owner_user_id=requirement.created_by,
        env=env,
        repos=repos,
        required_role=required_role,
        task_tag=task_tag,
    )

    # R6:test 任务容器拉起后先进"用例审阅"(AI 生成用例 → 用户确认后才 running)
    task.status = "cases_review" if task.type == "test" else "running"
    task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": task.status})
    logger.info("任务容器已调度 task=%s status=%s", task.task_id, task.status)


# ---------------------------------------------------------------------------
# R32.F1:任务容器 claude 资产注入(Skills + MCP)
# ---------------------------------------------------------------------------
async def inject_task_claude_assets(db: AsyncSession, task: Task, container: Container) -> None:
    """
    容器就绪(container_started)后,把项目已安装 Skills 与 MCP 配置写入容器:
    - Skills → /root/.claude/skills/{name}.md(claude CLI 进程级加载,对话/终端同享)
    - MCP    → /root/.claude.json 的 mcpServers 段(脱敏库取解密配置)
    经 Runner exec_tool=claude_inject 下发,Runner 侧线程池执行(与 claude_prompt 同路,
    不堵事件循环);无技能且无 MCP 配置时零下发。
    """
    runner_conn = runner_registry.get(container.runner_id)
    if runner_conn is None:
        return

    skills = await skill_service.list_project_skill_contents(db, task.project_id)
    # mcp_service 需要 Project 实体;task.project 未必预加载(懒加载在 async 下会炸)
    project = (
        await db.execute(select(Project).where(Project.project_id == task.project_id).limit(1))
    ).scalar_one_or_none()
    mcp_cfg = await mcp_service.get_decrypted_config(db, project) if project is not None else None
    mcp_servers = (mcp_cfg or {}).get("mcpServers") or {}
    if not skills and not mcp_servers:
        return

    await runner_service.request_runner(
        runner_conn,
        {
            "type": "exec_tool",
            "container_id": container.container_id,
            "tool": "claude_inject",
            "args": {"skills": skills, "mcp_config": {"mcpServers": mcp_servers} if mcp_servers else {}},
        },
        timeout=30.0,
    )
    logger.info("claude 资产已注入 task=%s skills=%d mcp=%d", task.task_id, len(skills), len(mcp_servers))


# ---------------------------------------------------------------------------
# 对话
# ---------------------------------------------------------------------------
async def ensure_claude_session(db: AsyncSession, task: Task) -> tuple[str, bool]:
    """
    R9.F1:确保任务级 claude CLI 会话 ID 存在(懒生成,对话与终端共用)。
    返回 (session_id, created_now):
    - created_now=True: 本次新生成(首次使用 --session-id)
    - created_now=False: 已有值,后续用 --resume 续接
    """
    if task.claude_session_id:
        return task.claude_session_id, False
    new_sid = str(uuid.uuid4())
    task.claude_session_id = new_sid
    await db.flush()
    return new_sid, True


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

    # 定位运行容器与 Runner 连接 —— 先校验后落库:原序先 flush user 消息再校验,
    # 校验失败 BizError 连带回滚,消息"发了却不存在"(BUG-032;rd-plan 旧分析 P0)
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

    user_msg = TaskMessage(
        task_id=task.task_id, role="user", content=content, file_refs=file_refs or None,
    )
    db.add(user_msg)
    await db.flush()

    started = time.monotonic()
    # R9.F1:确保任务级 claude 会话 ID,对话与终端共用同一会话
    sid, created_now = await ensure_claude_session(db, task)
    try:
        response = await claude_service.run_prompt(
            runner_conn, container.container_id, enhanced_prompt,
            session_id=sid, resume=not created_now,
        )
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


def _stream_event_to_chat(evt: dict) -> dict | None:
    """
    R32.F3:claude stream-json 事件 → 前端 chat 增量。
    assistant 事件:逐 content block 文本增量(与终端流式视觉一致);
    其余类型(system/init、user 工具结果等)忽略。result 不上泵(终态 finalize 承载)。
    """
    if evt.get("type") == "assistant":
        msg = evt.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return {"type": "chat_delta", "text": block["text"]}
    if evt.get("type") == "raw":
        return {"type": "chat_delta", "text": evt.get("text", "")}
    return None


async def send_message_stream(db: AsyncSession, task: Task, operator: User, content: str) -> dict:
    """
    R32.F3:流式发送消息 —— 同步段(校验+user 落库)同 send_message;
    AI 执行段走 claude_prompt_stream,assistant 文本增量经 task_event_registry
    实时广播({"type":"chat_delta"}),终态落库后广播 {"type":"chat_done"}。
    返回值同 send_message(POST 立即返回,不等 AI 跑完)。
    """
    from app.services import file_upload_service

    enhanced_prompt, file_refs = await file_upload_service.resolve_file_refs(db, task.task_id, content)

    has_prior_user = (await db.execute(
        select(func.count(TaskMessage.id)).where(
            TaskMessage.task_id == task.task_id, TaskMessage.role == "user"
        )
    )).scalar() or 0
    fix_block = _fix_context_block(task) if has_prior_user == 0 else ""
    if fix_block:
        enhanced_prompt = fix_block + enhanced_prompt

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

    user_msg = TaskMessage(
        task_id=task.task_id, role="user", content=content, file_refs=file_refs or None,
    )
    db.add(user_msg)
    await db.flush()

    started = time.monotonic()
    sid, created_now = await ensure_claude_session(db, task)
    try:
        stream_iter, finalize = await claude_service.run_prompt_stream(
            runner_conn, container.container_id, enhanced_prompt, task.task_id,
            session_id=sid, resume=not created_now,
        )
    except (RuntimeError, TimeoutError) as e:
        err = TaskMessage(task_id=task.task_id, role="assistant", content=f"执行失败:{e}")
        db.add(err)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "tool_call", "name": "claude", "error": str(e)})
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, f"AI 执行失败:{e}")

    try:
        async for evt in stream_iter:
            delta = _stream_event_to_chat(evt)
            if delta is not None:
                await task_event_registry.broadcast(task.task_id, delta)
        response = await finalize()
    except RuntimeError as e:
        err = TaskMessage(task_id=task.task_id, role="assistant", content=f"执行失败:{e}")
        db.add(err)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "chat_done", "ok": False, "error": str(e)})
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

    await task_event_registry.broadcast(task.task_id, {"type": "chat_done", "ok": True, "duration_ms": duration_ms})
    await task_event_registry.broadcast(task.task_id, {
        "type": "tool_call", "name": "claude_prompt", "duration_ms": duration_ms,
        "result": response["result"][:500],
    })
    logger.info("任务消息完成(流式) task=%s tokens=%d/%d", task.task_id, response["tokens_in"], response["tokens_out"])
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
    # R25 审计:task.done / task.cancelled(其他状态值不映射审计,防枚举外泄)
    _AUDIT_TASK_FINISH = {"done": "task.done", "cancelled": "task.cancelled"}
    action = _AUDIT_TASK_FINISH.get(status)
    if action is not None:
        await audit_write(
            db, operator, action,
            project_id=task.project_id, target_type="task", target_id=task.task_id,
        )


async def retry_task(db: AsyncSession, task: Task) -> None:
    """
    重试任务:failed/cancelled/timeout → pending → 立即重新拉起(R35.F3 补语义)。
    原实现只置 pending 无人拉起(僵尸);现 retry 后直接走 start_task 容器链
    (test 型自然落 cases_review;release 型走原调度)。拉不起(8003 无 Runner)维持 pending 排队。
    """
    if task.status not in ("failed", "cancelled", "timeout"):
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "当前状态不可重试")
    task.status = "pending"
    task.error_message = None
    task.finished_at = None
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "pending"})

    # R35.F3:立即重新拉起(原死代码语义补齐);无可用 Runner 时 start_task 抛 8003,
    # 此处吞回 pending 排队语义(与创建路径一致:pending 等重试/调度)
    requirement = (
        await db.execute(select(Requirement).where(Requirement.req_id == task.req_id).limit(1))
    ).scalar_one_or_none()
    project = (
        await db.execute(select(Project).where(Project.project_id == task.project_id).limit(1))
    ).scalar_one_or_none()
    if requirement is None or project is None:
        logger.warning("retry 拉起缺归属数据 task=%s(维持 pending)", task.task_id)
        return
    try:
        await start_task(db, task, project, requirement)
    except BizError as e:
        if e.code == ErrCode.NO_RUNNER_AVAILABLE:
            logger.info("retry 拉起无可用 Runner,任务回 pending 排队 task=%s", task.task_id)
        else:
            raise


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
        # R25 审计:系统事件(占位全零 user_id + role=system,detail 带 reason;不记 ip)
        spawn_audit_write(
            async_session_factory,
            {"user_id": AUDIT_SYSTEM_USER_ID, "role": "system"},
            "task.timeout_sweep",
            detail={"reason": "task_timeout_sweep", "count": count},
        )
        logger.info("任务超时清理 %d 个", count)
    return count


# ---------------------------------------------------------------------------
# R6:测试任务(type=test)
# ---------------------------------------------------------------------------
def build_report_path(title: str, task_id: str, date: Optional[datetime] = None) -> str:
    """Q26:docs/{YYYYMMDD}_{descSlug}_{taskShortId}/report.md(cases.json 同目录)"""
    slug = re.sub(r"[^\w一-鿿-]+", "-", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:32] or "需求"
    date = date or datetime.now()
    return f"docs/{date.strftime('%Y%m%d')}_{slug}_{task_id[:8]}/report.md"


async def create_test_task(
    db: AsyncSession, requirement: Requirement, project: Project, operator: User,
    title: str, description: str, based_on_dev_tasks: list[str],
) -> tuple[Task, Optional[str]]:
    """
    创建测试任务:
    - 前置:需求下至少一个 dev 任务 done(4001)
    - test 仓库缺失允许创建(返回提示语,UI 提示"建议绑定独立测试仓库")
    - 生成 report_file_path(Q26;cases.json 同目录)→ status=pending(创建即拉起走 start_task)
    """
    done_dev = (await db.execute(
        select(func.count(Task.id)).where(
            Task.req_id == requirement.req_id,
            Task.type == "dev",
            Task.status == "done",
        )
    )).scalar() or 0
    if done_dev == 0:
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "需求状态不允许创建该类型任务")

    from app.models.project import ProjectRepo

    test_repos = (await db.execute(
        select(ProjectRepo).where(
            ProjectRepo.project_id == project.project_id, ProjectRepo.role == "test"
        )
    )).scalars().all()
    test_repo_ids = [r.repo_id for r in test_repos]

    # 先生成对外 id(Task 默认值在 flush 时才生效,report 路径需提前引用)
    task_id = str(uuid.uuid4())
    task = Task(
        task_id=task_id,
        req_id=requirement.req_id,
        project_id=project.project_id,
        type="test",
        title=title,
        description=description,
        base_branch=requirement.req_branch,
        work_branch=requirement.req_branch,
        status="pending",
        created_by=operator.user_id,
        extended_attributes={
            "based_on_dev_tasks": based_on_dev_tasks,
            "test_cases": [],
            "report_file_path": build_report_path(requirement.title, task_id),
            "test_repo_ids": test_repo_ids,
        },
    )
    db.add(task)
    await db.flush()

    hint = None if test_repo_ids else "建议绑定独立测试仓库"
    logger.info("测试任务已创建 task=%s test_repos=%d hint=%s", task.task_id, len(test_repo_ids), hint)
    return task, hint


async def confirm_cases(db: AsyncSession, task: Task, operator: User, test_cases: list[dict]) -> None:
    """用户确认用例(可增删改)→ cases_review → running(开始执行)"""
    if task.status not in ("pending", "cases_review"):
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "当前状态不可确认用例")
    ext = dict(task.extended_attributes or {})
    ext["test_cases"] = test_cases
    task.extended_attributes = ext  # 新 dict 对象,确保触发 UPDATE
    task.status = "running"
    if not task.started_at:
        task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "running"})
    logger.info("用例确认并开始执行 task=%s cases=%d", task.task_id, len(test_cases))


async def accept_failure(db: AsyncSession, task: Task, operator: User, reason: str) -> None:
    """接受失败(豁免):status=passed,豁免理由与标记入 extended_attributes"""
    if task.type != "test":
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "仅测试任务可接受失败")
    ext = dict(task.extended_attributes or {})
    ext["exempt_failure"] = {"reason": reason, "by": operator.user_id,
                             "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}
    task.extended_attributes = ext  # 新 dict 对象,确保触发 UPDATE
    task.status = "passed"
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "passed"})
    logger.info("测试失败豁免 task=%s by=%s", task.task_id, operator.user_id)


# ---------------------------------------------------------------------------
# R7:发布任务(type=release)
# ---------------------------------------------------------------------------
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))+$")
DEPLOY_PORT_RANGE = (10000, 10099)
MAX_CONCURRENT_DEPLOYS = 5       # 单项目同时部署数 ≤ 5


async def create_release_task(
    db: AsyncSession, requirement: Requirement, project: Project, operator: User,
    title: str, description: str,
    deploy_port: int, deploy_host: Optional[str] = None, deploy_script: Optional[str] = None,
) -> tuple[Task, Optional[str]]:
    """
    创建发布任务(R7):
    - 前置:需求下至少一个 test 任务 passed(4001)
    - deploy_port:10000-10099 且全平台唯一(7001)
    - deploy_host:合法主机名 + 全平台唯一(7003);默认 {slug}.{deploy_base_domain}(Q28 实时读)
    - 单项目同时部署数 ≤5(7002)
    返回 (task, dns_hint)——自定义域名未解析不阻塞创建。
    """
    passed_test = (await db.execute(
        select(func.count(Task.id)).where(
            Task.req_id == requirement.req_id,
            Task.type == "test",
            Task.status == "passed",
        )
    )).scalar() or 0
    if passed_test == 0:
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "需求状态不允许创建该类型任务")

    if not (DEPLOY_PORT_RANGE[0] <= deploy_port <= DEPLOY_PORT_RANGE[1]):
        raise BizError(ErrCode.DEPLOY_PORT_CONFLICT, "端口已被占用")

    from app.services.platform_settings_service import get_setting

    base_domain = await get_setting(db, "deploy_base_domain") or "coding-console.zhanqitv.com.cn"
    host = (deploy_host or f"{project.slug}.{base_domain}").strip().lower()
    if not _HOSTNAME_RE.match(host):
        raise BizError(ErrCode.DEPLOY_HOST_INVALID, "域名格式不合法(不含协议与路径)")

    dup_host = (await db.execute(
        select(Task.task_id).where(
            Task.type == "release",
            Task.status.notin_(["cancelled", "failed"]),
            func.json_unquote(func.json_extract(Task.extended_attributes, "$.deploy_host")) == host,
        ).limit(1)
    )).scalar()
    if dup_host:
        raise BizError(ErrCode.DEPLOY_HOST_INVALID, "该域名已被其他部署占用")

    dup_port = (await db.execute(
        select(Task.task_id).where(
            Task.type == "release",
            Task.status.notin_(["cancelled", "failed", "timeout"]),
            func.json_unquote(func.json_extract(Task.extended_attributes, "$.deploy_port")) == str(deploy_port),
        ).limit(1)
    )).scalar()
    if dup_port:
        raise BizError(ErrCode.DEPLOY_PORT_CONFLICT, "端口已被占用")

    deploys = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project.project_id,
            Task.type == "release",
            Task.status.notin_(["cancelled", "failed", "timeout"]),
            func.json_unquote(func.json_extract(Task.extended_attributes, "$.deploy_phase")).in_(["deploying", "deployed"]),
        )
    )).scalar() or 0
    if deploys >= MAX_CONCURRENT_DEPLOYS:
        raise BizError(ErrCode.DEPLOY_LIMIT_EXCEEDED, "项目同时部署数已达上限(5个)")

    dns_hint = "请先将域名 A 记录解析到网关" if deploy_host else None

    task = Task(
        req_id=requirement.req_id,
        project_id=project.project_id,
        type="release",
        title=title,
        description=description,
        base_branch="master",
        work_branch="master",
        status="pending",
        created_by=operator.user_id,
        extended_attributes={
            "target_env": "subdomain",
            "deploy_host": host,
            "deploy_port": deploy_port,
            "deploy_script": deploy_script or "",
            "deploy_log_path": build_report_path(requirement.title, str(uuid.uuid4())).replace("report.md", "deploy-log.txt"),
            "deploy_phase": "deploying",
        },
    )
    db.add(task)
    await db.flush()
    logger.info("发布任务已创建 task=%s host=%s port=%s hint=%s", task.task_id, host, deploy_port, dns_hint)
    return task, dns_hint


async def run_release(db: AsyncSession, task: Task, project: Project, requirement: Requirement) -> None:
    """
    发布执行(容器内,经 Runner):
    1. merge req_branch → master
    2. 执行部署脚本(默认:在容器内启动服务)
    3. 健康检查 localhost:{deploy_port}
    4. 注册网关路由(host={deploy_host}:{deploy_port},公开)→ deploy_phase=deployed
    失败 → deploy_phase=failed + task failed。
    """
    container = (await db.execute(
        select(Container).where(
            # creating 亦视为可发布:容器已调度(start_container 已下发),
            # container_started 回报仅补记端口映射
            Container.task_id == task.task_id, Container.status.in_(["running", "creating"])
        ).order_by(Container.id.desc()).limit(1)
    )).scalars().first()
    runner_conn = runner_registry.get(container.runner_id) if container else None
    if container is None or runner_conn is None:
        ext = dict(task.extended_attributes or {})
        ext["deploy_phase"] = "failed"
        task.extended_attributes = ext
        task.status = "failed"
        task.error_message = "Runner offline,无法执行发布"
        await db.flush()
        return

    ext = dict(task.extended_attributes or {})
    deploy_port = int(ext.get("deploy_port", 0))
    script = ext.get("deploy_script") or f"echo 'no deploy script; service expected on port {deploy_port}'"

    try:
        await runner_service.request_runner(runner_conn, {
            "type": "git_merge",
            "container_id": container.container_id,
            "repo_path": "/workspace/main",
            "source_branch": requirement.req_branch,
            "target_branch": "master",
        }, timeout=120.0)

        result = await runner_service.request_runner(runner_conn, {
            "type": "deploy_run",
            "container_id": container.container_id,
            "script": script,
            "health_port": deploy_port,
            "health_path": "/",
        }, timeout=300.0)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "部署脚本执行失败")

        from app.services import route_service

        host_with_port = "{}:{}".format(ext.get("deploy_host"), deploy_port)
        mapped = container.runner_host_port_8000 or container.runner_host_port_5173 or 0
        conn_info = runner_registry.get(container.runner_id)
        upstream = "http://{}:{}".format(conn_info.host if conn_info else "", mapped)
        await route_service.register_deploy_route(
            db,
            project_id=task.project_id, task_id=task.task_id,
            container_id=container.container_id, runner_id=container.runner_id,
            deploy_host=ext.get("deploy_host"), deploy_port=deploy_port,
            upstream=upstream,
        )

        ext = dict(task.extended_attributes or {})
        ext["deploy_phase"] = "deployed"
        task.extended_attributes = ext
        task.status = "done"  # 发布任务执行完成;容器保留(R7 例外)
        await db.flush()
        await _maybe_complete_requirement(db, requirement)
        # R25 审计:release.deployed(操作者=任务创建者,查库取角色)
        _creator = (await db.execute(
            select(User).where(User.user_id == task.created_by)
        )).scalars().first()
        if _creator is not None:
            await audit_write(
                db, _creator, "release.deployed",
                project_id=task.project_id, target_type="task", target_id=task.task_id,
                detail={"deploy_host": ext.get("deploy_host")},
            )
        await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "deployed"})
        logger.info("发布完成 task=%s host=%s", task.task_id, ext.get("deploy_host"))
    except Exception as e:
        ext = dict(task.extended_attributes or {})
        ext["deploy_phase"] = "failed"
        ext["deploy_error"] = str(e)[:500]
        task.extended_attributes = ext
        task.status = "failed"
        task.error_message = "发布失败:{}".format(e)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "status_changed", "status": "failed"})
        logger.warning("发布失败 task=%s: %s", task.task_id, e)


async def _maybe_complete_requirement(db: AsyncSession, requirement: Requirement) -> None:
    """需求下所有发布任务 deployed(无 failed/pending)→ 需求 done(R7 状态推进)"""
    if requirement.status not in ("approved", "in_progress"):
        return
    total = (await db.execute(
        select(func.count(Task.id)).where(Task.req_id == requirement.req_id, Task.type == "release")
    )).scalar() or 0
    finished = 0
    for t in (await db.execute(
        select(Task).where(Task.req_id == requirement.req_id, Task.type == "release")
    )).scalars().all():
        phase = (t.extended_attributes or {}).get("deploy_phase")
        if t.status == "done" and phase == "deployed":
            finished += 1
    if total > 0 and finished == total:
        requirement.status = "done"
        await db.flush()
        logger.info("需求全部部署完成 → done req=%s", requirement.req_id)
        # R14:自动归档(done → archived;时间线/总结/知识条目 draft)
        project_row = (await db.execute(
            select(Project).where(Project.project_id == requirement.project_id)
        )).scalars().first()
        if project_row is not None:
            from app.services import archive_service

            await archive_service.archive_requirement(db, requirement, project_row)


async def offline_deploy(db: AsyncSession, task: Task) -> None:
    """下线:摘除路由 + 销毁容器 + deploy_phase=undeployed"""
    from app.services import route_service

    ext = task.extended_attributes or {}
    host_with_port = "{}:{}".format(ext.get("deploy_host"), ext.get("deploy_port"))
    await route_service.set_route_status(db, host_with_port, "inactive")
    await route_service.set_route_status(db, ext.get("deploy_host") or "", "inactive")

    ext = dict(ext)
    ext["deploy_phase"] = "undeployed"
    task.extended_attributes = ext

    container = (await db.execute(
        select(Container).where(
            Container.task_id == task.task_id, Container.status.in_(["running", "creating"])
        ).order_by(Container.id.desc()).limit(1)
    )).scalars().first()
    if container is not None:
        await container_service.request_stop(db, container)
    await db.flush()
    logger.info("部署已下线 task=%s", task.task_id)
