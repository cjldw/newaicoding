"""R9.F1 — 任务级 claude 会话 ID 机制测试

测试覆盖:
1. ensure_claude_session:懒生成 + 幂等
2. claude_service.run_prompt:session_id/resume 参数透传到 exec_tool args
3. task_service.send_message:组装链携带会话参数
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectRepo
from app.models.task import Task
from app.models.user import User
from app.services import claude_service


# ---------------------------------------------------------------------------
# 辅助:创建测试用 Task(参照 test_release_tasks.py 模式)
# ---------------------------------------------------------------------------
async def _make_task(db_session: AsyncSession, user_id: str, **overrides) -> Task:
    """创建最小可用 Task(含 project/requirement 外键)"""
    project = Project(
        project_id=str(uuid.uuid4()),
        name="r9f1-test",
        slug=f"r9f1-{uuid.uuid4().hex[:8]}",
        owner_id=user_id,
    )
    db_session.add(project)
    await db_session.flush()

    from app.models.requirement import Requirement
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="r9f1-req",
        description="d",
        status="approved",
        req_branch="main",
        created_by=user_id,
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()

    defaults = dict(
        task_id=str(uuid.uuid4()),
        req_id=req.req_id,
        project_id=project.project_id,
        type="dev",
        title="r9f1-task",
        description="d",
        base_branch="main",
        work_branch="main",
        status="running",
        conversation_id=str(uuid.uuid4()),
        created_by=user_id,
    )
    defaults.update(overrides)
    task = Task(**defaults)
    db_session.add(task)
    await db_session.flush()
    return task


async def _make_user(db_session: AsyncSession) -> User:
    """创建最小可用 User"""
    user = User(
        user_id=str(uuid.uuid4()),
        phone=f"138{str(uuid.uuid4().int)[:8]}",
        password_hash="x",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# 1. ensure_claude_session:懒生成 + 幂等
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ensure_claude_session_first_call_generates(db_session: AsyncSession):
    """首次调用:claude_session_id 为空 → 生成 uuid4 落库,返回 (sid, True)"""
    from app.services.task_service import ensure_claude_session

    user = await _make_user(db_session)
    task = await _make_task(db_session, user.user_id)
    assert task.claude_session_id is None  # 初始为空

    sid, created_now = await ensure_claude_session(db_session, task)

    # 生成合法 UUID4
    assert len(sid) == 36
    uuid.UUID(sid)  # 不抛异常即合法
    assert created_now is True
    # 落库(对象级)
    assert task.claude_session_id == sid


@pytest.mark.asyncio
async def test_ensure_claude_session_second_call_idempotent(db_session: AsyncSession):
    """二次调用:claude_session_id 已有值 → 返回同一 sid,created_now=False"""
    from app.services.task_service import ensure_claude_session

    user = await _make_user(db_session)
    task = await _make_task(db_session, user.user_id)

    sid1, created1 = await ensure_claude_session(db_session, task)
    assert created1 is True

    sid2, created2 = await ensure_claude_session(db_session, task)
    assert sid2 == sid1  # 同一 sid
    assert created2 is False  # 非新建


# ---------------------------------------------------------------------------
# 2. claude_service.run_prompt:session_id/resume 参数透传
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_prompt_no_session_params():
    """无 session 参数 → args 不含 session_id/resume 字段(兼容旧行为)"""
    fake_runner_conn = MagicMock()

    captured_msg = {}

    async def fake_request_runner(conn, message, timeout=None):
        captured_msg.update(message)
        return {"ok": True, "data": {"result": "ok", "tokens_in": 0, "tokens_out": 0}}

    with patch("app.services.runner_service.request_runner", side_effect=fake_request_runner):
        await claude_service.run_prompt(fake_runner_conn, "container_123", "hello")

    assert captured_msg["type"] == "exec_tool"
    assert captured_msg["tool"] == "claude_prompt"
    args = captured_msg["args"]
    assert args["prompt"] == "hello"
    # 无 session 字段
    assert "session_id" not in args
    assert "resume" not in args


@pytest.mark.asyncio
async def test_run_prompt_with_session_id_first_time():
    """session_id + resume=False → args 含 session_id 字段(首次建会话语义)"""
    fake_runner_conn = MagicMock()

    captured_msg = {}

    async def fake_request_runner(conn, message, timeout=None):
        captured_msg.update(message)
        return {"ok": True, "data": {"result": "ok", "tokens_in": 0, "tokens_out": 0}}

    test_sid = str(uuid.uuid4())
    with patch("app.services.runner_service.request_runner", side_effect=fake_request_runner):
        await claude_service.run_prompt(
            fake_runner_conn, "container_123", "hello",
            session_id=test_sid, resume=False,
        )

    args = captured_msg["args"]
    assert args["session_id"] == test_sid
    # resume=False 时不传 resume 字段(代码逻辑:if resume 才加)
    assert "resume" not in args


@pytest.mark.asyncio
async def test_run_prompt_with_resume():
    """resume=True → args 含 resume=True 字段(续接已有会话语义)"""
    fake_runner_conn = MagicMock()

    captured_msg = {}

    async def fake_request_runner(conn, message, timeout=None):
        captured_msg.update(message)
        return {"ok": True, "data": {"result": "ok", "tokens_in": 0, "tokens_out": 0}}

    test_sid = str(uuid.uuid4())
    with patch("app.services.runner_service.request_runner", side_effect=fake_request_runner):
        await claude_service.run_prompt(
            fake_runner_conn, "container_123", "hello",
            session_id=test_sid, resume=True,
        )

    args = captured_msg["args"]
    assert args["session_id"] == test_sid
    assert args["resume"] is True


# ---------------------------------------------------------------------------
# 3. send_message 组装链:mock 断言 args 携带会话参数
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_passes_session_params(db_session: AsyncSession):
    """send_message → run_prompt 调用携带 session_id + resume 参数"""
    from app.services import task_service
    from app.models.container import Container

    user = await _make_user(db_session)
    task = await _make_task(db_session, user.user_id, status="running")

    # 创建真实 Container 记录(避免 mock db_session.execute 破坏事务)
    container = Container(
        container_id="test_container_001",
        task_id=task.task_id,
        runner_id="test_runner_001",
        project_id=task.project_id,
        status="running",
        image="test:latest",
        exposed_ports=[5173],
    )
    db_session.add(container)
    await db_session.flush()

    mock_runner_conn = MagicMock()

    with (
        patch("app.services.task_service.runner_registry") as mock_registry,
        patch("app.services.task_service.claude_service.run_prompt",
              new_callable=AsyncMock) as mock_run_prompt,
        patch("app.services.file_upload_service.resolve_file_refs",
              new_callable=AsyncMock, return_value=("test message", [])),
        patch("app.services.task_service.task_event_registry") as mock_event_registry,
    ):
        mock_registry.get.return_value = mock_runner_conn
        mock_run_prompt.return_value = {"result": "AI response", "tokens_in": 10, "tokens_out": 20}
        mock_event_registry.broadcast = AsyncMock()

        await task_service.send_message(db_session, task, user, "test message")

        # 断言 run_prompt 被调用,且携带 session 参数
        assert mock_run_prompt.called
        call_kwargs = mock_run_prompt.call_args.kwargs
        assert "session_id" in call_kwargs
        assert call_kwargs["session_id"] is not None
        assert len(call_kwargs["session_id"]) == 36
        # 首次调用:resume=False(因为 created_now=True)
        assert call_kwargs.get("resume") is False

        # 二次调用:resume=True
        await task_service.send_message(db_session, task, user, "second message")
        second_call_kwargs = mock_run_prompt.call_args.kwargs
        assert second_call_kwargs["session_id"] == call_kwargs["session_id"]  # 同一 sid
        assert second_call_kwargs.get("resume") is True  # 续接
