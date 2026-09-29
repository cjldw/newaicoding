"""BUG-069(R5.F2) 后端侧:AI 回复空 content 落库兜底

根因:runner 返回 result 空时,task_service 直接落库空 content,前端 refetch 后
展示空气泡 = 「输出一段后消失」。

修复 F2:落库前 content 空 → 用 runner 累积文本兜底;仍空 → 占位文案 + error_message。

用例:
- ① result 空 + runner 附带累积文本 → 落库 content=累积文本
- ② 双空 → 落占位文案 + error_message 留痕
- ③ 正常路径 content=result 不变(回归)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task, TaskMessage
from app.services import claude_service, task_service, file_upload_service, llm_service
from app.services.runner_service import runner_registry


class FakeRunnerWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


async def _mk_running_task(db_session, registered_user):
    """项目 + 需求 + running 任务 + running 容器 + 在线 Runner 连接"""
    project = Project(name=f"p-{uuid.uuid4().hex[:6]}", slug=f"pj-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()), title="r", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}", created_by=registered_user["user_id"],
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="t", description="d",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status="running", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()

    runner_id = f"rn-{uuid.uuid4().hex[:6]}"
    db_session.add(Runner(name=runner_id, role="worker", token_hash="x",
                          status="online", created_by="t"))
    await db_session.flush()
    conn = runner_registry.register(runner_id, "worker", FakeRunnerWS(), host="test")
    db_session.add(Container(
        container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner_id, project_id=project.project_id,
        status="running", image="img", cpu_limit="2c", mem_limit="4g", disk_limit="10g",
    ))
    await db_session.flush()
    return {"project": project, "req": req, "task": task, "conn": conn}


def _mock_stream(monkeypatch, events: list[dict], finalize_data: dict):
    """替身 run_prompt_stream:返回 (stream_iter, finalize)"""
    async def fake_run_prompt_stream(*args, **kwargs):
        async def stream_iter():
            for evt in events:
                yield evt
        async def finalize():
            return finalize_data
        return stream_iter(), finalize
    monkeypatch.setattr(claude_service, "run_prompt_stream", fake_run_prompt_stream)


# ---------------------------------------------------------------------------
# ① 核心 Red:result 空 + 累积文本 → 落库 content=累积文本
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_stream_fallback_to_accumulated_text(
    db_session, registered_user, monkeypatch
):
    """runner 返回 result 空但带 accumulated_text → 落库 content=accumulated_text"""
    ctx = await _mk_running_task(db_session, registered_user)
    task = ctx["task"]

    # 模拟:流式事件无 result,finalize 返回 result 空 + accumulated_text 非空
    events = [
        {"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "项目需要"},
        }},
        {"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "登录加上图形验证码"},
        }},
    ]
    finalize_data = {
        "result": "",  # 无 result 事件
        "tokens_in": 10,
        "tokens_out": 20,
        "accumulated_text": "项目需要登录加上图形验证码",  # F1 新增字段
    }
    _mock_stream(monkeypatch, events, finalize_data)

    # mock file_upload_service.resolve_file_refs(避免文件上传逻辑)
    async def fake_resolve(db, task_id, content):
        return content, None
    monkeypatch.setattr("app.services.file_upload_service.resolve_file_refs", fake_resolve)

    # mock llm_service.resolve_config(避免模型配置校验)
    async def fake_resolve_config(db, project_id, config_id=None):
        return {"model": "claude-sonnet-4-20250514"}
    monkeypatch.setattr(llm_service, "resolve_config", fake_resolve_config)

    user = MagicMock()
    user.user_id = registered_user["user_id"]
    result = await task_service.send_message_stream(db_session, task, user, "项目需要登录加上图形验证码")

    # 断言:assistant 消息 content=累积文本(非空)
    ai_msg = (await db_session.execute(
        TaskMessage.__table__.select().where(
            TaskMessage.task_id == task.task_id,
            TaskMessage.role == "assistant",
        )
    )).first()
    assert ai_msg is not None
    assert ai_msg.content == "项目需要登录加上图形验证码"


# ---------------------------------------------------------------------------
# ② 双空 → 落占位文案 + error_message
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_stream_both_empty_fallback_to_placeholder(
    db_session, registered_user, monkeypatch
):
    """result 空 + accumulated_text 空 → 落占位文案 + error_message 留痕"""
    ctx = await _mk_running_task(db_session, registered_user)
    task = ctx["task"]

    events = []  # 无任何流式事件
    finalize_data = {
        "result": "",
        "tokens_in": 0,
        "tokens_out": 0,
        "accumulated_text": "",  # 也无累积文本
    }
    _mock_stream(monkeypatch, events, finalize_data)

    async def fake_resolve(db, task_id, content):
        return content, None
    monkeypatch.setattr("app.services.file_upload_service.resolve_file_refs", fake_resolve)

    async def fake_resolve_config(db, project_id, config_id=None):
        return {"model": "claude-sonnet-4-20250514"}
    monkeypatch.setattr(llm_service, "resolve_config", fake_resolve_config)

    user = MagicMock()
    user.user_id = registered_user["user_id"]
    result = await task_service.send_message_stream(db_session, task, user, "ping")

    ai_msg = (await db_session.execute(
        TaskMessage.__table__.select().where(
            TaskMessage.task_id == task.task_id,
            TaskMessage.role == "assistant",
        )
    )).first()
    assert ai_msg is not None
    assert ai_msg.content == "[AI 回复执行中断,未获取到回复内容,请重试]"


# ---------------------------------------------------------------------------
# ③ 回归:正常路径 content=result 不变
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_stream_normal_path_unchanged(
    db_session, registered_user, monkeypatch
):
    """正常 result 非空 → 落库 content=result(行为不变)"""
    ctx = await _mk_running_task(db_session, registered_user)
    task = ctx["task"]

    events = [
        {"type": "stream_event", "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "正常回复"},
        }},
    ]
    finalize_data = {
        "result": "正常回复",
        "tokens_in": 5,
        "tokens_out": 10,
    }
    _mock_stream(monkeypatch, events, finalize_data)

    async def fake_resolve(db, task_id, content):
        return content, None
    monkeypatch.setattr("app.services.file_upload_service.resolve_file_refs", fake_resolve)

    async def fake_resolve_config(db, project_id, config_id=None):
        return {"model": "claude-sonnet-4-20250514"}
    monkeypatch.setattr(llm_service, "resolve_config", fake_resolve_config)

    user = MagicMock()
    user.user_id = registered_user["user_id"]
    result = await task_service.send_message_stream(db_session, task, user, "hi")

    ai_msg = (await db_session.execute(
        TaskMessage.__table__.select().where(
            TaskMessage.task_id == task.task_id,
            TaskMessage.role == "assistant",
        )
    )).first()
    assert ai_msg is not None
    assert ai_msg.content == "正常回复"
