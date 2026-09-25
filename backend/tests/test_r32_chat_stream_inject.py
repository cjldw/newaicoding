"""
R32 任务对话 Skills/MCP 注入 + 流式输出(平台侧)
==========================
F1 注入:
- handle_container_started → inject_task_claude_assets 下发 exec_tool=claude_inject
  (skills 写 /root/.claude/skills/*.md;mcp 合并写 /root/.claude.json)
- 无技能且无 MCP 时零下发;Runner 离线静默跳过
F3 流式:
- runner_service.request_runner_stream / route_stream_event / resolve_stream_request
- claude_service.run_prompt_stream(stream_iter + finalize)
- task_service._stream_event_to_chat(assistant 文本块 → chat_delta)
- runner_ws:result 先结算流式请求,claude_stream 按 req_id 路由
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services import runner_service, task_service
from app.services.runner_service import runner_registry
from app.services.task_service import _stream_event_to_chat


class FakeRunnerWS:
    """Runner WebSocket 替身(记录下发消息;与 test_tasks_api 同款)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


def _mk_task(task_id: str, project_id: str) -> Task:
    return Task(
        task_id=task_id, req_id=str(uuid.uuid4()), project_id=project_id,
        type="dev", title="t", description="d",
        base_branch="b", work_branch="b", status="running", created_by="u",
    )


# ---------------------------------------------------------------------------
# F1:注入下发
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inject_skills_and_mcp_dispatches_claude_inject(db_session, registered_user, monkeypatch):
    """有技能 + 有 MCP → 一条 claude_inject,args 带 skills/mcpServers"""
    project = Project(name="p", slug=f"pj-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()

    async def fake_skills(db, project_id):
        return [{"name": "prd-review", "content": "# 评审技能"}]

    async def fake_mcp(db, proj):
        return {"mcpServers": {"gitlab": {"url": "http://mcp.example.com"}}}

    monkeypatch.setattr(task_service.skill_service, "list_project_skill_contents", fake_skills)
    monkeypatch.setattr(task_service.mcp_service, "get_decrypted_config", fake_mcp)

    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    await db_session.flush()
    conn = FakeRunnerWS()
    runner_registry.register(runner.runner_id, "worker", conn, host="test")

    async def fake_request(conn_, message, timeout=15.0):
        conn_.websocket.sent.append(message)
        return {"ok": True, "data": {"skills": 1, "mcp": 1}}

    monkeypatch.setattr(runner_service, "request_runner", fake_request)

    task = _mk_task(str(uuid.uuid4()), project.project_id)
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner.runner_id, project_id=project.project_id,
        status="running", image="img", cpu_limit="2c", mem_limit="4g", disk_limit="10g",
    )
    db_session.add(task)
    db_session.add(container)
    await db_session.flush()

    await task_service.inject_task_claude_assets(db_session, task, container)

    assert len(conn.sent) == 1
    msg = conn.sent[0]
    assert msg["type"] == "exec_tool"
    assert msg["tool"] == "claude_inject"
    assert msg["args"]["skills"] == [{"name": "prd-review", "content": "# 评审技能"}]
    assert msg["args"]["mcp_config"]["mcpServers"]["gitlab"]["url"] == "http://mcp.example.com"
    runner_registry.unregister(runner.runner_id)


@pytest.mark.asyncio
async def test_inject_skips_when_nothing_to_inject(db_session, registered_user, monkeypatch):
    """无技能且无 MCP → 零下发"""
    project = Project(name="p", slug=f"pj-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()

    async def fake_skills(db, project_id):
        return []

    async def fake_mcp(db, proj):
        return None

    monkeypatch.setattr(task_service.skill_service, "list_project_skill_contents", fake_skills)
    monkeypatch.setattr(task_service.mcp_service, "get_decrypted_config", fake_mcp)

    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    await db_session.flush()
    conn = FakeRunnerWS()
    runner_registry.register(runner.runner_id, "worker", conn, host="test")

    task = _mk_task(str(uuid.uuid4()), project.project_id)
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner.runner_id, project_id=project.project_id,
        status="running", image="img", cpu_limit="2c", mem_limit="4g", disk_limit="10g",
    )
    db_session.add(task)
    db_session.add(container)
    await db_session.flush()

    await task_service.inject_task_claude_assets(db_session, task, container)
    assert conn.sent == []
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# F3:流式事件转换与 req 路由
# ---------------------------------------------------------------------------
def test_stream_event_to_chat_assistant_text_block():
    evt = {
        "type": "assistant",
        "message": {"content": [
            {"type": "text", "text": "你好,"},
            {"type": "tool_use", "name": "Bash"},
        ]},
    }
    assert _stream_event_to_chat(evt) == {"type": "chat_delta", "text": "你好,"}


def test_stream_event_to_chat_ignores_non_text():
    assert _stream_event_to_chat({"type": "system", "subtype": "init"}) is None
    assert _stream_event_to_chat({"type": "result", "result": "done"}) is None
    assert _stream_event_to_chat({"type": "assistant", "message": {"content": []}}) is None


@pytest.mark.asyncio
async def test_stream_request_lifecycle():
    """register → route 两条增量 → resolve 终态;重复 resolve 幂等 False"""
    conn_obj = runner_registry.register(f"stream-{uuid.uuid4().hex[:6]}", "worker", FakeRunnerWS(), host="test")
    req_id, queue = await runner_service.request_runner_stream(
        conn_obj, {"type": "exec_tool", "tool": "claude_prompt_stream", "task_id": "t1"}, timeout=5,
    )
    assert conn_obj.websocket.sent and conn_obj.websocket.sent[0]["req_id"] == req_id

    assert runner_service.route_stream_event(req_id, '{"type":"assistant","message":{"content":[{"type":"text","text":"你"}]}}')
    assert runner_service.route_stream_event(req_id, '{"type":"assistant","message":{"content":[{"type":"text","text":"好"}]}}')
    assert not runner_service.route_stream_event("no-such-req", "{}")

    assert runner_service.resolve_stream_request(req_id, True, data={"result": "你好", "tokens_in": 3, "tokens_out": 2})
    assert not runner_service.resolve_stream_request(req_id, True, data={})  # 已注销

    e1 = await queue.get()
    e2 = await queue.get()
    e3 = await queue.get()
    assert e1["type"] == "stream" and "你" in e1["line"]
    assert e2["type"] == "stream" and "好" in e2["line"]
    assert e3 == {"type": "done", "ok": True, "data": {"result": "你好", "tokens_in": 3, "tokens_out": 2}, "error": ""}
