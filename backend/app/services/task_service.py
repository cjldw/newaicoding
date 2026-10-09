"""任务服务 - R4(任务生命周期 + 对话 + 事件流)

任务类型:requirement(打磨)/ dev / test / release。
- 创建:需求状态校验(4001)→ 创建者 GitLab token 校验(4002)→ 并发 ≤3(4003)
  → 调度拉起容器(R8)→ pending→running
- 对话:@file 引用解析注入(<100KB 内容/≥100KB 路径)→ Claude CLI 兜底执行(R13 配置)
  → task_messages 台账 + 活动流事件
- 结束:全仓库 commit+push(创建者 token)→ done → 容器销毁(销毁前强制 push 在 Runner)
- 事件:WS /ws/tasks/{tid}/events(tool_call/status_changed)
"""

import asyncio
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
_BG_PRD_SYNCS: set = set()        # R37.F10(BUG-085):在途后台 PRD 回传引用(仅防 GC)

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
    """task_id → 前端事件 WS 连接表(内存;BUG-057:存 websocket 本体,dict 入 set 会 TypeError)"""

    def __init__(self) -> None:
        self._conns: dict[str, list] = {}

    def connect(self, task_id: str, websocket):
        conns = self._conns.setdefault(task_id, [])
        conns.append(websocket)
        return websocket

    def disconnect(self, task_id: str, conn) -> None:
        conns = self._conns.get(task_id)
        if conns is not None:
            try:
                conns.remove(conn)
            except ValueError:
                pass

    async def broadcast(self, task_id: str, payload: dict) -> int:
        sent = 0
        conns = list(self._conns.get(task_id, []))
        for ws in conns:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                self.disconnect(task_id, ws)
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


def derive_display_status(task_status: str, container_status: str | None) -> str:
    """BUG-063:派生展示状态(不修改 task.status 本身,仅用于 API 输出)

    规则:
      - task.status != "running" → 原值透传
      - running + 无容器/creating → "starting"
      - running + container running → "running"
      - running + container failed → "failed"
      - running + 其他(destroyed/stopped 等) → 兜底 "running"(不卡 starting)
    """
    if task_status != "running":
        return task_status
    if container_status is None or container_status == "creating":
        return "starting"
    if container_status == "running":
        return "running"
    if container_status == "failed":
        return "failed"
    # 其他状态(destroyed/stopped 等)→ 兜底 running,避免卡死在 starting
    return "running"


def task_brief(task: Task, container_status: str | None = None) -> dict:
    return {
        "task_id": task.task_id,
        "type": task.type,
        "title": task.title,
        "status": task.status,
        "display_status": derive_display_status(task.status, container_status),
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


async def batch_latest_container_status(db: AsyncSession, task_ids: list[str]) -> dict[str, str]:
    """BUG-063:批量查询每个 task_id 的最新容器状态(防 N+1)

    同一 task_id 可能有多条容器记录(重建场景),取 id 最大的一条作为最新状态。
    返回: {task_id: status}
    """
    from app.models.container import Container
    if not task_ids:
        return {}
    # 按 task_id 分组取最大 id 对应的 status
    result = await db.execute(
        select(Container.task_id, Container.status)
        .where(Container.task_id.in_(task_ids))
        .order_by(Container.id.asc())  # 小→大,后覆盖前 = 最终保留最大 id
    )
    mapping: dict[str, str] = {}
    for row in result.all():
        mapping[row[0]] = row[1]  # 后出现的覆盖前面的,最终留下最大 id 的 status
    return mapping


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
        # BUG-074:基线=项目默认分支(需求分支从它切出),diff 它 = 本任务全部改动;
        # 原 `or requirement.req_branch` 自指(work==base)→ git diff 恒空「没有对比效果」
        base_branch=base_branch or project.default_branch,
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


async def _resolve_task_model(db: AsyncSession, task: Task, config_id: Optional[str]) -> Optional[str]:
    """
    R34.F2:会话级模型解析(对话框切换)。
    - config_id 存在但归属其他项目 → 越权拒绝(1901;resolve_config 只按 config_id
      全局查、不校验归属,归属校验在此补齐,防跨项目盗用配置)
    - 其余(含 config_id 失效)→ resolve_config 三级回退链(项目 default → 平台默认)
    返回 model 名(经 --model 下发,覆盖容器创建时固化的 ANTHROPIC_MODEL)。
    """
    from app.models.model_config import ModelConfig
    from app.services import llm_service

    if config_id is not None:
        row = (await db.execute(
            select(ModelConfig).where(ModelConfig.config_id == config_id)
        )).scalars().first()
        if row is not None and row.project_id != task.project_id:
            logger.warning(
                "跨项目模型配置被拒绝 task=%s config=%s belong=%s expect=%s",
                task.task_id, config_id, row.project_id, task.project_id,
            )
            raise BizError(ErrCode.NO_PROJECT_PERMISSION, "模型配置不属于该项目,禁止使用")

    llm_config = await llm_service.resolve_config(db, task.project_id, config_id)
    return llm_config["model"]


async def send_message(db: AsyncSession, task: Task, operator: User, content: str,
                       config_id: Optional[str] = None) -> dict:
    """
    发送消息:保存 user 消息(@file 注入)→ Claude CLI 兜底执行 → 保存 assistant
    消息 → 广播活动流。返回 user message_id。
    R34.F2:config_id 会话级模型切换(越权校验 + 回退链见 _resolve_task_model)。
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

    # R34.F2:越权校验 + 模型解析(先校验后落库,同 BUG-032 口径)
    model = await _resolve_task_model(db, task, config_id)

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
            session_id=sid, resume=not created_now, model=model,
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
    BUG-058:--include-partial-messages 下 stream_event/content_block_delta/text_delta
    为 token 级增量(逐字流式的真正来源);assistant 整块路径保留作回退。
    其余类型(system/init、user 工具结果等)忽略。result 不上泵(终态 finalize 承载)。
    R34.F3(BUG-UI-091):permission/control 事件透传 —— control_request
    {subtype:"can_use_tool"} → chat_confirm_request 增量(prompt 人类可读,
    含工具名与关键参数);其余 control 子事件不过度捕获(维持忽略)。
    """
    if evt.get("type") == "stream_event":
        event = evt.get("event") or {}
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            text = delta.get("text")
            if text:
                return {"type": "chat_delta", "text": text}
        return None
    if evt.get("type") == "control_request":
        request = evt.get("request") or {}
        if request.get("subtype") == "can_use_tool":
            return {
                "type": "chat_confirm_request",
                "prompt": build_confirm_prompt(request.get("tool_name", ""), request.get("input") or {}),
                "options": ["allow", "deny"],
            }
        return None
    if evt.get("type") == "assistant":
        msg = evt.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return {"type": "chat_delta", "text": block["text"]}
    if evt.get("type") == "raw":
        return {"type": "chat_delta", "text": evt.get("text", "")}
    return None


# BUG-059(R32.F7):chat_delta 打字机平滑参数——上游网关非流式时增量瞬达(实测 126 帧
# 挤在 0.14s),视觉等同同步整段输出;按最小帧间隔铺开形成逐字流式。
# 真流式网关时增量到达间隔大于下限,零额外延迟直通(自适应)。
CHAT_DELTA_SLICE = 16           # 单帧最大字符数(大块增量拆分)
CHAT_DELTA_MIN_INTERVAL = 0.03  # 相邻帧最小间隔(秒)


async def _broadcast_delta_smooth(task_id: str, text: str, state: dict) -> None:
    """
    把 chat_delta 平滑为打字机节奏后广播。
    - text 大于 SLICE → 拆帧;瞬达(相邻增量间隔 < MIN_INTERVAL)→ sleep 补齐节奏
    - state 跨调用携带 {"last": 上帧时刻}(同一轮对话共享)
    """
    import asyncio

    loop = asyncio.get_running_loop()
    if state.get("last") is None:
        state["last"] = loop.time()
    for i in range(0, len(text), CHAT_DELTA_SLICE):
        piece = text[i:i + CHAT_DELTA_SLICE]
        delay = (state["last"] + CHAT_DELTA_MIN_INTERVAL) - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        await task_event_registry.broadcast(task_id, {"type": "chat_delta", "text": piece})
        state["last"] = loop.time()


async def send_message_stream(db: AsyncSession, task: Task, operator: User, content: str,
                              config_id: Optional[str] = None) -> dict:
    """
    R32.F3:流式发送消息 —— 同步段(校验+user 落库)同 send_message;
    AI 执行段走 claude_prompt_stream,assistant 文本增量经 task_event_registry
    实时广播({"type":"chat_delta"}),终态落库后广播 {"type":"chat_done"}。
    返回值同 send_message(POST 立即返回,不等 AI 跑完)。
    R34.F2:config_id 会话级模型切换(越权校验 + 回退链见 _resolve_task_model)。
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

    # R34.F2:越权校验 + 模型解析(先校验后落库,同 BUG-032 口径)
    model = await _resolve_task_model(db, task, config_id)

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
            session_id=sid, resume=not created_now, model=model,
        )
    except (RuntimeError, TimeoutError) as e:
        err = TaskMessage(task_id=task.task_id, role="assistant", content=f"执行失败:{e}")
        db.add(err)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "tool_call", "name": "claude", "error": str(e)})
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, f"AI 执行失败:{e}")

    try:
        delta_state: dict = {}  # R32.F7:打字机平滑节奏状态(同一轮对话共享)
        # R5.F4 BUG-074:去重标志——CLI --include-partial-messages 下每个 content block
        # 结束会发一次 assistant 整块事件,与已广播的 text_delta 内容重复。
        # 见过 text_delta 后跳过 assistant 整块路径;老 CLI 无 partial 事件时标志保持
        # False,assistant 路径正常广播(兜底不回归)
        seen_stream_delta = False
        async for evt in stream_iter:
            # R5.F4:assistant 整块路径仅在未见 text_delta 时走(兜底)
            if seen_stream_delta and evt.get("type") == "assistant":
                continue
            delta = _stream_event_to_chat(evt)
            if delta is None:
                continue
            if delta.get("type") == "chat_confirm_request":
                # R34.F3:确认请求(流内 control 路径)→ 登记挂起 + 执行协程在此挂起等待
                # 应答/5min 超时 deny;下行通道指向本容器 Runner(应答经 REST 下行放行)
                cid = await register_confirm_request(task.task_id, delta)
                _confirm_channels[cid] = {"runner_id": container.runner_id, "req_id": "", "task_id": task.task_id}
                choice = await wait_confirm(cid)
                logger.info("确认已收口(流内路径) task=%s confirm=%s choice=%s", task.task_id, cid, choice)
                continue
            # R5.F4:text_delta 广播后标志置位,后续 assistant 整块跳过
            if evt.get("type") == "stream_event":
                event = evt.get("event") or {}
                delta_inner = event.get("delta") or {}
                if event.get("type") == "content_block_delta" and delta_inner.get("type") == "text_delta":
                    seen_stream_delta = True
            await _broadcast_delta_smooth(task.task_id, delta["text"], delta_state)
        response = await finalize()
    except claude_service.AICancelled:
        # R34.F1:用户真取消(messages/cancel → runner pkill claude → 终态
        # error="cancelled")—— 不写「执行失败」台账、不按失败回 POST;
        # 广播 chat_done ok:false 供前端收尾「已停止」反馈条
        await task_event_registry.broadcast(task.task_id, {"type": "chat_done", "ok": False, "error": "cancelled"})
        logger.info("任务对话已被用户取消 task=%s", task.task_id)
        return {"message_id": user_msg.message_id, "cancelled": True}
    except RuntimeError as e:
        err = TaskMessage(task_id=task.task_id, role="assistant", content=f"执行失败:{e}")
        db.add(err)
        await db.flush()
        await task_event_registry.broadcast(task.task_id, {"type": "chat_done", "ok": False, "error": str(e)})
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, f"AI 执行失败:{e}")
    finally:
        # R34.F3:对话收尾清理挂起确认(正常完成无挂起=零广播;取消/异常路径兜底 deny 收口,
        # 与 cancel_message_stream 的 stop 优先收口重入安全:二次调用 no-op)
        try:
            await cleanup_task_confirms(task.task_id)
        except Exception:
            logger.exception("对话收尾清理挂起确认失败 task=%s", task.task_id)
        # R37.F10(BUG-085):打磨任务每轮 AI 回复后后台回传 PRD 入库(prd_content
        # 副本),容器超时/异常销毁也不再丢稿。自开 session(fire-and-forget),
        # 持引用防 GC;同步幂等,finish 时 finish_task 会再走一次。
        # 整段异常安全:收尾钩子绝不打断对话主链路
        if task.type == "requirement":
            try:
                from app.services import requirement_service as _req_service

                _bg = asyncio.create_task(_req_service._sync_prd_background(task.task_id))
                _BG_PRD_SYNCS.add(_bg)
                _bg.add_done_callback(_BG_PRD_SYNCS.discard)
            except Exception:
                logger.warning("PRD 后台回传调度失败(不阻塞对话收尾) task=%s", task.task_id)

    duration_ms = int((time.monotonic() - started) * 1000)

    # BUG-069(F2):落库前 content 空 → 用 runner 累积文本兜底;仍空 → 占位文案
    # 根因:CLI 不发 result 事件时,runner 原兜底取 lines[-1] 解析垃圾(空/残缺);
    # F1 已让 runner 返回 accumulated_text,此处作为后端第二道防线
    ai_content = response.get("result") or ""
    if not ai_content:
        accumulated = response.get("accumulated_text") or ""
        if accumulated:
            ai_content = accumulated
        else:
            ai_content = "[AI 回复执行中断,未获取到回复内容,请重试]"
            logger.warning(
                "任务消息 AI 回复空(占位兜底) task=%s tokens_in=%d tokens_out=%d lines=%d stderr=%s",
                task.task_id, response.get('tokens_in', 0), response.get('tokens_out', 0),
                response.get('lines', 0), (response.get('stderr_tail') or '')[:200],
            )

    # R5.F3 三修(BUG-072):runner 判定 resume 毒化会话(error-result)已在其侧降级
    # 重跑自救,但库里残留的 claude_session_id 仍指向不存在的会话——不置空则每条
    # 消息都先撞一次 resume 失败再降级(双倍耗时)。此处置空,下条消息走 --session-id 首用
    if response.get("resume_error") and getattr(task, "claude_session_id", None):
        task.claude_session_id = None
        logger.warning("resume 会话不存在已重置 claude_session_id task=%s", task.task_id)

    ai_msg = TaskMessage(
        task_id=task.task_id, role="assistant", content=ai_content,
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

    # R2:PRD 回传(容器 → 平台副本) — docs/20260929_打磨PRD持久化/DEVPLAN/R2.md
    # fire-and-forget:不阻塞 SSE 收尾,自开 session 独立落库
    if task.type == "requirement":
        from app.services.requirement_service import _sync_prd_background
        asyncio.create_task(_sync_prd_background(task.task_id))

    return {"message_id": user_msg.message_id}


async def cancel_message_stream(db: AsyncSession, task: Task) -> dict:
    """
    R34.F1:取消在途 AI 对话(真取消):
    按 task_id 反查 _stream_requests 在途 req_id → 经 Runner 下发 exec_tool_cancel
    + 本地结算 done(ok=False)→ send_message_stream 捕获 AICancelled 广播
    chat_done {ok:false, error:"cancelled"} 并正常收尾;runner 侧容器内 pkill
    claude 真停执行(迟到终态因 req_id 已注销被丢弃)。
    守卫与 send_message 同口径(容器在跑/Runner 在线),但按取消契约回 HTTP 400;
    无在途对话幂等返回 cancelled=False(前端停止按钮与 POST 返回的竞态兜底)。
    """
    logger.info("取消对话请求 task=%s status=%s", task.task_id, task.status)
    container = (await db.execute(
        select(Container).where(
            Container.task_id == task.task_id, Container.status == "running"
        ).order_by(Container.id.desc()).limit(1)
    )).scalars().first()
    if container is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "任务容器不在运行,不可取消", status_code=400)
    runner_conn = runner_registry.get(container.runner_id)
    if runner_conn is None:
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "Runner offline,不可取消", status_code=400)

    # R34.F3:确认挂起 × 停止 → stop 优先,挂起确认先按 deny 收口并广播 resolved
    # (先于取消链;send_message_stream 收尾的兜底清理对本调用重入安全=no-op)
    await cleanup_task_confirms(task.task_id)
    req_ids = runner_service.find_stream_requests(task.task_id)
    if not req_ids:
        logger.info("取消对话:无在途流式请求 task=%s", task.task_id)
        return {"cancelled": False, "req_ids": []}
    for rid in req_ids:
        await runner_service.cancel_stream_request(runner_conn, rid)
    return {"cancelled": True, "req_ids": req_ids}


# ---------------------------------------------------------------------------
# R34.F3:AI 确认交互(BUG-UI-091)—— 挂起表 + 广播 + 应答下行
# ---------------------------------------------------------------------------
# 确认超时兜底:5min 无应答自动按 deny 收口(测试 monkeypatch 注入短时长,绝不真等)
CONFIRM_TIMEOUT_SECONDS = 300
# 内存挂起表(规格口径,不落库;进程重启=挂起全丢,由 runner 桥接层 5min 自兜底 deny)
confirm_futures: dict[str, asyncio.Future] = {}  # confirm_id → Future(result ∈ {"allow","deny"})
confirm_owners: dict[str, str] = {}              # confirm_id → task_id(任务结束/停止清理反查)
_confirm_channels: dict[str, dict] = {}          # confirm_id → {runner_id, task_id}(应答下行路由)
_confirm_resolved: dict[str, str] = {}           # 已结算结果备忘(应答与等待间的竞态窗口)
_confirm_bg_tasks: set = set()                   # 超时收割任务强引用(防 GC)

# 确认卡文案取参优先键(命令/路径类;取不到再取首个字符串值)
_CONFIRM_PARAM_KEYS = ("command", "file_path", "path", "notebook_path", "url", "pattern", "query")


def build_confirm_prompt(tool_name: str, tool_input: Optional[dict]) -> str:
    """确认卡人类可读文案:含工具名与关键参数(R34.F3 契约;截断 120 防超长命令刷屏)"""
    summary = ""
    for key in _CONFIRM_PARAM_KEYS:
        val = (tool_input or {}).get(key)
        if isinstance(val, str) and val.strip():
            summary = val.strip()
            break
    if not summary:
        for val in (tool_input or {}).values():
            if isinstance(val, str) and val.strip():
                summary = val.strip()
                break
    if len(summary) > 120:
        summary = summary[:117] + "..."
    if summary:
        return f"允许执行 {tool_name}({summary}) 吗?"
    return f"允许执行 {tool_name} 吗?"


async def register_confirm_request(task_id: str, delta: dict) -> str:
    """
    登记挂起确认 + 广播 chat_confirm_request(R34.F3):
    delta 为透传增量({prompt, options?}),confirm_id 在此生成并回填广播帧,
    前端据此弹确认卡并携 confirm_id 应答 POST /tasks/{id}/confirm。
    """
    confirm_id = uuid.uuid4().hex
    confirm_futures[confirm_id] = asyncio.get_running_loop().create_future()
    confirm_owners[confirm_id] = task_id
    await task_event_registry.broadcast(task_id, {
        "type": "chat_confirm_request",
        "confirm_id": confirm_id,
        "prompt": delta.get("prompt", ""),
        "options": delta.get("options") or ["allow", "deny"],
    })
    logger.info("确认请求已登记并广播 task=%s confirm=%s prompt=%s", task_id, confirm_id, delta.get("prompt", ""))
    return confirm_id


def resolve_confirm(confirm_id: str, choice: str) -> bool:
    """
    应答挂起确认(一次性):set_result 放行执行协程 + 注销挂起表;
    confirm_id 不存在/已应答/已收口 → False(调用方回 4001)。
    """
    fut = confirm_futures.get(confirm_id)
    if fut is None or fut.done():
        logger.info("确认应答拒绝(不存在/已应答) confirm=%s", confirm_id)
        return False
    _confirm_resolved[confirm_id] = choice  # 竞态备忘:等待方尚未 await 时补读
    confirm_futures.pop(confirm_id, None)
    confirm_owners.pop(confirm_id, None)
    fut.set_result(choice)
    logger.info("确认已应答 confirm=%s choice=%s", confirm_id, choice)
    return True


async def wait_confirm(confirm_id: str) -> str:
    """
    执行协程唯一等待点(R34.F3):应答 set_result 放行返回其选择;
    CONFIRM_TIMEOUT_SECONDS 超时按 deny 收口 + 广播
    chat_confirm_resolved {confirm_id, choice:"deny", reason:"timeout"} + 注销。
    """
    fut = confirm_futures.get(confirm_id)
    if fut is None:
        # 竞态窗口:应答发生在登记与等待之间(resolve 已弹出条目)→ 取备忘结果
        memo = _confirm_resolved.pop(confirm_id, None)
        if memo is not None:
            logger.info("确认等待命中竞态备忘(应答先于等待) confirm=%s choice=%s", confirm_id, memo)
            return memo
        logger.warning("确认等待:未知 confirm_id=%s,按 deny 放行", confirm_id)
        return "deny"
    try:
        choice = await asyncio.wait_for(fut, timeout=CONFIRM_TIMEOUT_SECONDS)
        _confirm_resolved.pop(confirm_id, None)  # 结算备忘已消费
        return choice if choice in ("allow", "deny") else "deny"
    except asyncio.TimeoutError:
        task_id = confirm_owners.pop(confirm_id, None)
        confirm_futures.pop(confirm_id, None)
        _confirm_channels.pop(confirm_id, None)
        _confirm_resolved.pop(confirm_id, None)
        await task_event_registry.broadcast(task_id or "", {
            "type": "chat_confirm_resolved",
            "confirm_id": confirm_id,
            "choice": "deny",
            "reason": "timeout",
        })
        logger.info("确认超时自动拒绝 confirm=%s task=%s", confirm_id, task_id)
        return "deny"


async def cleanup_task_confirms(task_id: str) -> int:
    """
    任务结束/停止清理:该任务全部挂起按 deny 收口并注销,逐条广播
    chat_confirm_resolved {choice:"deny", reason:"stopped"};返回收口条数
    (未知任务 no-op 返回 0)。负向探查:确认挂起 × 任务停止 → stop 优先。
    """
    ids = [cid for cid, owner in confirm_owners.items() if owner == task_id]
    for confirm_id in ids:
        fut = confirm_futures.pop(confirm_id, None)
        confirm_owners.pop(confirm_id, None)
        _confirm_channels.pop(confirm_id, None)
        _confirm_resolved[confirm_id] = "deny"
        if fut is not None and not fut.done():
            fut.set_result("deny")
        await task_event_registry.broadcast(task_id, {
            "type": "chat_confirm_resolved",
            "confirm_id": confirm_id,
            "choice": "deny",
            "reason": "stopped",
        })
    if ids:
        logger.info("任务挂起确认已按 deny 收口 task=%s count=%d", task_id, len(ids))
    return len(ids)


async def deliver_confirm_choice(confirm_id: str, choice: str) -> None:
    """
    应答下行 Runner(尽力而为):桥接收到 exec_tool_confirm 写应答文件放行容器内
    CLI;通道缺失(流内 control 路径无下行/Runner 已重启)仅记日志 —— 超时兜底
    在桥接层,执行不悬挂。
    """
    channel = _confirm_channels.pop(confirm_id, None)
    if channel is None:
        logger.info("确认应答无下行通道 confirm=%s(非桥接路径或已清理)", confirm_id)
        return
    conn = runner_registry.get(channel.get("runner_id", ""))
    if conn is None:
        logger.warning("确认下行失败:Runner 不在线 confirm=%s runner=%s", confirm_id, channel.get("runner_id"))
        return
    try:
        await runner_service.send_to_runner(conn, {
            "type": "exec_tool_confirm",
            "req_id": channel.get("req_id", ""),
            "confirm_id": confirm_id,
            "choice": choice,
        })
        logger.info("确认应答已下行 runner=%s confirm=%s choice=%s", conn.runner_id, confirm_id, choice)
    except Exception as e:
        logger.warning("确认下行发送失败 confirm=%s: %s", confirm_id, e)


async def handle_runner_confirm_request(task_id: str, req_id: str, runner_id: str,
                                        tool_name: str, tool_input: dict) -> str:
    """
    Runner 桥接权限请求上行(R34.F3 实证:确认请求的信号源是桥接侧 tools/call,
    不是 CLI stdout)→ 登记挂起 + 广播 chat_confirm_request + 挂起下行通道 + 超时收割。
    """
    confirm_id = await register_confirm_request(task_id, {
        "type": "chat_confirm_request",
        "prompt": build_confirm_prompt(tool_name, tool_input),
        "options": ["allow", "deny"],
    })
    _confirm_channels[confirm_id] = {"runner_id": runner_id, "req_id": req_id, "task_id": task_id}
    # 超时收割:wait_confirm 5min 无应答内部自动 deny + 广播 resolved(reason=timeout)
    reaper = asyncio.create_task(wait_confirm(confirm_id))
    _confirm_bg_tasks.add(reaper)
    reaper.add_done_callback(_confirm_bg_tasks.discard)
    return confirm_id


# ---------------------------------------------------------------------------
# 结束:完成 / 停止 / 重试 / 超时
# ---------------------------------------------------------------------------
async def finish_task(db: AsyncSession, task: Task, operator: User, status: str = "done") -> None:
    """
    完成任务:所有仓库 git add -A + commit([ai:type] title)+ push(创建者 token)
    → status=done → 容器销毁(销毁前强制 push 由 Runner 兜底)。
    """
    # F2.e:收所有 running 容器(原 limit(1) 只收最新一条,历史行漏网 → BUG-073 泄漏路径 1)
    containers_result = await db.execute(
        select(Container).where(
            Container.task_id == task.task_id, Container.status == "running"
        )
    )
    containers = containers_result.scalars().all()

    if containers:
        # 取第一个容器做 git commit/push(只需一次)
        container = containers[0]
        # R37.F8(BUG-082):Runner 离线 → 显式报错(原:静默跳过 commit,任务照常
        # done,用户以为已提交;「完成=提交」语义下必须诚实失败)。
        # 仅约束 status="done"(打磨完成);取消收尾(status=cancelled)保持宽容——
        # 取消绝不能被提交凭据卡死(R35.F2 契约:取消容忍 finish 失败)
        runner_conn = runner_registry.get(container.runner_id)
        if runner_conn is None and status == "done":
            raise BizError(
                ErrCode.TERMINAL_UNAVAILABLE,
                "Runner 离线,无法提交仓库;请稍后重试打磨完成,或联系管理员",
            )
        creator = (await db.execute(
            select(User).where(User.user_id == task.created_by)
        )).scalars().first()
        creator_token = ""
        if creator is not None and creator.gitlab_token_encrypted:
            from app.core.encryption import decrypt_token

            creator_token = decrypt_token(creator.gitlab_token_encrypted)

        # R37.F8(BUG-082):提交凭据链 = 创建者 token → 平台 bot token 回退 → 皆无显式报错
        # (原:creator_token 空即整段静默跳过;需求分支本由 bot 创建,回退天然有推送权)。
        # 显式报错仅 status="done";取消收尾走宽容分支(尽力提交,凭据缺失静默跳过)
        commit_token = creator_token
        if not commit_token:
            from app.services.platform_settings_service import get_gitlab_bot_config

            bot_token = ""
            try:
                _, bot_token, _ = await get_gitlab_bot_config(db)
            except BizError:
                bot_token = ""
            if not bot_token and status == "done":
                raise BizError(
                    ErrCode.BOT_TOKEN_NOT_CONFIGURED,
                    "创建者未绑定 GitLab Token 且平台未配置 Bot Token,无法提交仓库;"
                    "请先在个人设置绑定 GitLab Token 后重新执行打磨完成",
                )
            commit_token = bot_token
            if bot_token:
                logger.info(
                    "finish 提交回退平台 bot token task=%s(创建者未绑定个人 token)",
                    task.task_id,
                )

        if runner_conn is not None and commit_token:
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
                        "token": commit_token,
                    }, timeout=60.0)
                except Exception as e:
                    logger.warning("仓库 commit/push 失败 task=%s repo=%s: %s", task.task_id, mount, e)

        # 路径后置:PRD 终态回传钩子——此刻 push 已完成(GitLab 有实际文件)、容器仍在线
        # (发现器可用),发现实际 PRD 路径 → 回写 prd_file_path + 回填 prd_content。
        # 覆盖全部收尾入口(完成任务/手动停止/取消需求收尾);内部自捕获异常,失败不阻塞收尾
        if task.type == "requirement":
            from app.services.requirement_service import sync_prd_from_container
            await sync_prd_from_container(db, task.task_id)

        # 销毁容器(停止指令;Runner 销毁前强制 push 未 push commit)
        await container_service.request_stop(db, container)

        # F2.e:收所有 running 容器(原 limit(1) 只收最新一条,历史行漏网 → BUG-073 泄漏路径 1)
        for c in containers[1:]:
            await container_service.request_stop(db, c)

    task.status = status
    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if status == "cancelled":
        task.error_message = "用户手动停止"
    await db.flush()
    # R34.F3:任务结束清理挂起确认(有挂起按 deny 收口 + 广播 resolved reason=stopped)
    await cleanup_task_confirms(task.task_id)
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

    F2.c:retry 前先清旧容器(status IN (running, creating) → request_stop + destroyed),
    避免 retry 叠新容器不清旧(BUG-073 泄漏路径 1)。
    """
    if task.status not in ("failed", "cancelled", "timeout"):
        raise BizError(ErrCode.TASK_REQ_STATUS_INVALID, "当前状态不可重试")

    # F2.c:清理旧 running/creating 容器(retry 前收口,防泄漏)
    old_containers_result = await db.execute(
        select(Container).where(
            Container.task_id == task.task_id,
            Container.status.in_(["running", "creating"]),
        )
    )
    old_containers = old_containers_result.scalars().all()
    for old_container in old_containers:
        await container_service.request_stop(db, old_container)
        old_container.status = "destroyed"
        old_container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info("retry 清理旧容器 task=%s container=%s", task.task_id, old_container.container_id)
    await db.flush()

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
        # F2.e:收所有 running 容器(原 limit(1) 只收最新一条,历史行漏网 → BUG-073 泄漏路径 1)
        containers_result = await db.execute(
            select(Container).where(
                Container.task_id == task.task_id, Container.status == "running"
            )
        )
        containers = containers_result.scalars().all()
        # R37.F10(BUG-085):打磨任务销毁容器前兜底回传 PRD——容器一停,未走
        # 「打磨完成」链路的 PRD.md 就没了(纯容器内存货);自开 session 同步
        # (sweep 会话是否 commit 不可依赖),await 内联保证先回传后销毁
        if task.type == "requirement" and containers:
            from app.services import requirement_service as _req_service

            try:
                await _req_service._sync_prd_background(task.task_id)
            except Exception:
                logger.warning("超时清扫 PRD 兜底回传失败(不阻塞销毁) task=%s", task.task_id)
        for container in containers:
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
