"""
R34.F2 对话框模型切换 —— 后端契约(4 层 + 越权校验)Red 测试
==========================================================
契约(docs/20260927_AI对话框气泡优化/DEVPLAN/R34.F2.md):
1. api 层:SendMessageRequest 加 config_id: str | None = None,透传
2. service 层:send_message_stream / send_message 加参,函数内
   llm_service.resolve_config(db, task.project_id, config_id)
3. claude_service 层:run_prompt_stream args 加 model 字段
4. runner 层:--model CLI flag 透传(本文件验证到 claude_service 入参为止)
5. 越权校验:config_id 须属于 task.project_id,否则拒绝(_get_config_or_404 模式)

现状(未实现):SendMessageRequest 只有 content,config_id 被 pydantic 静默忽略,
resolve_config 不接收 config_id,run_prompt_stream 无 model 形参 → 以下断言全部失败(Red)。
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.core.encryption import encrypt_token
from app.models.container import Container
from app.models.model_config import ModelConfig
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import TaskMessage
from app.services import llm_service
from app.services.runner_service import runner_registry
from tests.test_projects_api import _seed_gitlab_settings


class FakeRunnerWS:
    """Runner WebSocket 替身(记录下发消息;与 test_tasks_api 同款)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


async def _setup(db_session, registered_user):
    """项目(main repo)+ 在线 Runner(DB + 内存连接)+ 默认模型配置;返回 (project, runner, conn, ws)"""
    await _seed_gitlab_settings(db_session)
    runner = Runner(name=f"rn-{uuid.uuid4().hex[:6]}", role="worker",
                    token_hash="x", status="online", created_by="t")
    db_session.add(runner)
    project = Project(name="模型切换项目", slug=f"mc-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main",
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_repo_id=311, gitlab_bind_type="manual",
        created_by=registered_user["user_id"],
    ))
    db_session.add(ModelConfig(
        project_id=project.project_id, name="default-cfg",
        base_url="https://llm.example.com/v1",
        api_key_encrypted=encrypt_token("sk-x"),
        model="cfg-default-model", is_default=True, enabled=True,
        created_by=registered_user["user_id"],
    ))
    await db_session.flush()

    ws = FakeRunnerWS()
    conn = runner_registry.register(runner.runner_id, "worker", ws, "10.0.0.8")
    return project, runner, conn, ws


async def _bind_gitlab_token(db_session, user_id):
    from app.models.user import User

    result = await db_session.execute(sqlalchemy.select(User).where(User.user_id == user_id))
    user = result.scalars().first()
    if user is not None:
        user.gitlab_token_encrypted = encrypt_token("glpat-user")
        await db_session.flush()
    return user


async def _mk_requirement(db_session, project, creator_id, status="approved"):
    r = Requirement(
        req_id=str(uuid.uuid4()), title="登录功能", description="d",
        status=status, req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_running_task(client, auth_headers, db_session, registered_user):
    """走完整创建流:approved 需求 → API 建任务 → 容器置 running(与 test_tasks_api 同款)"""
    project, runner, conn, ws = await _setup(db_session, registered_user)
    await _bind_gitlab_token(db_session, registered_user["user_id"])
    req = await _mk_requirement(db_session, project, registered_user["user_id"], "approved")

    resp = await client.post(
        f"/api/requirements/{req.req_id}/tasks",
        headers=auth_headers,
        json={"type": "dev", "title": "t", "description": "d"},
    )
    assert resp.json()["code"] == 0, resp.json()
    task_id = resp.json()["data"]["task_id"]

    # fake WS 无 container_started 回报:手动把容器置 running(模拟回报完成)
    container_row = (await db_session.execute(
        sqlalchemy.select(Container).where(Container.task_id == task_id)
    )).scalars().first()
    container_row.status = "running"
    await db_session.flush()
    return project, runner, task_id


def _patch_stream_capture(monkeypatch):
    """替身 run_prompt_stream:记录每次调用的 kwargs(观察 model 是否透传)"""
    from app.services import claude_service

    captured: list[dict] = []

    async def fake_run_prompt_stream(runner_conn, container_id, prompt, task_id_, *args, **kwargs):
        captured.append({"prompt": prompt, "kwargs": dict(kwargs), "args": args})

        async def stream_iter():
            yield {"type": "assistant", "message": {"content": [{"type": "text", "text": "已处理"}]}}

        async def finalize():
            return {"result": "已处理", "tokens_in": 10, "tokens_out": 5}

        return stream_iter(), finalize

    monkeypatch.setattr(claude_service, "run_prompt_stream", fake_run_prompt_stream)
    return captured


def _patch_resolve_spy(monkeypatch):
    """resolve_config 间谍:记录 (project_id, config_id) 入参后委托原实现(保留回退链语义)"""
    calls: list[tuple] = []
    original = llm_service.resolve_config

    async def spy(db, project_id, config_id=None):
        calls.append((project_id, config_id))
        return await original(db, project_id, config_id)

    monkeypatch.setattr(llm_service, "resolve_config", spy)
    # 兼容契约实现可能存在的 from-import 直绑(task_service.resolve_config)
    monkeypatch.setattr(__import__("app.services.task_service", fromlist=["x"]),
                        "resolve_config", spy, raising=False)
    return calls


# ---------------------------------------------------------------------------
# 1. 正向:请求体携带 config_id → 执行路径使用该配置
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_with_config_id_uses_that_config(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """携带 config_id 发送 → resolve_config 收到该 config_id;下游 model = 该配置的 model"""
    project, runner, task_id = await _mk_running_task(client, auth_headers, db_session, registered_user)

    # 追加一个启用但非默认的配置(模拟用户在对话框里切换到它)
    picked = ModelConfig(
        project_id=project.project_id, name="picked-cfg",
        base_url="https://llm.example.com/v2",
        api_key_encrypted=encrypt_token("sk-y"),
        model="cfg-picked-model", is_default=False, enabled=True,
        created_by=registered_user["user_id"],
    )
    db_session.add(picked)
    await db_session.flush()

    calls = _patch_resolve_spy(monkeypatch)
    captured = _patch_stream_capture(monkeypatch)

    resp = await client.post(
        f"/api/tasks/{task_id}/messages",
        headers=auth_headers,
        json={"content": "用切换后的模型跑", "config_id": picked.config_id},
    )
    body = resp.json()
    assert body["code"] == 0, body

    # 契约 2:service 层把 config_id 透传给 resolve_config
    assert (project.project_id, picked.config_id) in calls, (
        f"resolve_config 未收到 config_id 入参,实际调用:{calls}"
    )
    # 契约 3:claude_service 层收到解析出的 model(而非默认配置的)
    assert len(captured) == 1, captured
    assert captured[0]["kwargs"].get("model") == "cfg-picked-model", (
        f"执行路径未使用所选配置,captured={captured}"
    )
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 2. 负向:config_id 属于其他项目 → 拒绝(越权校验)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_rejects_cross_project_config_id(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """config_id 属于其他项目 → 业务报错,且该配置的 model 不得进入执行路径"""
    project, runner, task_id = await _mk_running_task(client, auth_headers, db_session, registered_user)

    # 其他项目 + 它自己的默认配置
    other_project = Project(name="其他项目", slug=f"ot-{uuid.uuid4().hex[:6]}",
                            owner_id=registered_user["user_id"])
    db_session.add(other_project)
    await db_session.flush()
    other_cfg = ModelConfig(
        project_id=other_project.project_id, name="other-cfg",
        base_url="https://llm.example.com/v9",
        api_key_encrypted=encrypt_token("sk-z"),
        model="other-project-model", is_default=True, enabled=True,
        created_by=registered_user["user_id"],
    )
    db_session.add(other_cfg)
    await db_session.flush()

    captured = _patch_stream_capture(monkeypatch)

    resp = await client.post(
        f"/api/tasks/{task_id}/messages",
        headers=auth_headers,
        json={"content": "尝试越权用别家配置", "config_id": other_cfg.config_id},
    )
    body = resp.json()
    # 越权校验:业务错误码非 0(具体码按契约落地,404/权限码均可,HTTP 4xx 同样算拒绝)
    assert body["code"] != 0, (
        f"跨项目 config_id 未被拒绝(越权),实际返回 {body}"
    )
    # 越权配置的 model 绝不能被执行路径消费
    assert all(c["kwargs"].get("model") != "other-project-model" for c in captured), captured
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 3. 负向:config_id 不存在 → 回退链(项目 default),不报错
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_with_unknown_config_id_falls_back_to_default(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """不存在的 config_id → resolve_config 回退到项目 default → 正常执行,model=默认配置"""
    project, runner, task_id = await _mk_running_task(client, auth_headers, db_session, registered_user)

    captured = _patch_stream_capture(monkeypatch)

    resp = await client.post(
        f"/api/tasks/{task_id}/messages",
        headers=auth_headers,
        json={"content": "配置已失效,应回退默认", "config_id": f"cfg-gone-{uuid.uuid4().hex[:8]}"},
    )
    body = resp.json()
    # 分片契约:resolve_config 查不到自动走回退链(项目 default → 平台默认),不报错
    assert body["code"] == 0, body
    assert len(captured) == 1, captured
    assert captured[0]["kwargs"].get("model") == "cfg-default-model", (
        f"未回退到项目默认配置,captured={captured}"
    )
    runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# 4. 回归:不传 config_id → 现状不变
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_message_without_config_id_regression(
    client, auth_headers, db_session, registered_user, monkeypatch,
):
    """不传 config_id(现状前端旧版)→ code 0,user+assistant 台账照旧"""
    project, runner, task_id = await _mk_running_task(client, auth_headers, db_session, registered_user)

    _patch_stream_capture(monkeypatch)

    resp = await client.post(
        f"/api/tasks/{task_id}/messages",
        headers=auth_headers,
        json={"content": "普通消息"},
    )
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"]["message_id"], body

    msgs = (await db_session.execute(
        sqlalchemy.select(TaskMessage).where(TaskMessage.task_id == task_id)
    )).scalars().all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "普通消息"
    runner_registry.unregister(runner.runner_id)
