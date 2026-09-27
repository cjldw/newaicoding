"""
R34.F3 AI 确认交互(后端)— TDD Red 契约测试
====================================================
契约(DEVPLAN/R34.F3.md;负向探查:确认挂起 × stop 优先按 deny 收口):

平台侧 POST /api/tasks/{task_id}/confirm:
- 请求 {confirm_id: str, choice: "allow" | "deny"}(Literal,非法 choice → 422)
- 成功 200 code=0 data={"ok": true};Future set_result(choice) 放行执行协程
- confirm_id 不存在 / 已应答 → code=4001(200 + 业务码,与 R28 头像 4001 同口径)
- 任务不存在 → 404 code=404「任务不存在」;未认证 → 401
- 非项目成员 → 403 code=1901(鉴权=任务成员,与 send_message 同口径)

task_service 侧(Red 阶段拍板的实现面;Green 按此落地):
- confirm_futures: dict[confirm_id, asyncio.Future](result ∈ {"allow","deny"})
  —— 规格原文「内存挂起表 dict[confirm_id, asyncio.Future]」的字面落地
- confirm_owners: dict[confirm_id, task_id](任务结束/停止清理时反查)
- CONFIRM_TIMEOUT_SECONDS = 300(5min 兜底;测试 patch 注入短时长,绝不真等)
- register_confirm_request(task_id, delta) -> confirm_id:登记挂起 Future + 广播
  {"type":"chat_confirm_request","confirm_id",...,"prompt","options":["allow","deny"]}
- resolve_confirm(confirm_id, choice) -> bool:set_result + 注销(一次性);False=未知/已应答
- wait_confirm(confirm_id) -> "allow"|"deny":执行协程唯一等待点,
  wait_for(CONFIRM_TIMEOUT_SECONDS),超时按 deny 收口并广播
  {"type":"chat_confirm_resolved","confirm_id","choice":"deny","reason":"timeout"}
- cleanup_task_confirms(task_id) -> int:任务结束/停止时全部挂起按 deny 收口并注销
- _stream_event_to_chat 新增分支:CLI permission/control 事件 → chat_confirm_request
  (CLI 具体机制待 rd-dev 实证 --permission-prompt-tool;本测试用 stream-json
  control 事件作入参样板,若 CLI 事件形态不同,rd-dev 调整【入参样板】而非断言契约:
  输出必须含 type/prompt(人类可读,带工具名与关键参数)/options)

不测(理由见 .scratch/R34.F3/qa-red-tests.md):
- runner 侧 --permission-prompt-tool / 容器内 CLI 交互:机制未定(规格最大不确定点),
  不写 runner 测试,归 rd-dev 实证后补
- 前端确认卡 UI / useTaskChatStream 分支:前端层,归前端 QA
- 后端重启 → 挂起全按 deny:内存表口径,进程重启非 pytest 可测面(规格已声明可接受)
"""
import asyncio
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.services import runner_service
from app.services import task_service as ts
from app.services.runner_service import runner_registry
from app.services.task_service import _stream_event_to_chat


class FakeRunnerWS:
    """Runner WebSocket 替身(记录下发消息;与 test_task_messages_cancel 同款)"""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict):
        self.sent.append(payload)


class _RecordingRegistry:
    """task_event_registry 替身:记录广播帧(与 test_r32f6_task_events 同款)"""

    def __init__(self):
        self.frames: list[tuple[str, dict]] = []

    async def broadcast(self, task_id, payload):
        import time as _t
        self.frames.append((_t.monotonic(), payload))
        return 1


# ---------------------------------------------------------------------------
# 造数助手
# ---------------------------------------------------------------------------
async def _mk_task(db_session, registered_user):
    """项目 + 需求 + 任务(creator=owner,即项目成员)。confirm 接口只操作内存
    挂起表,不依赖容器/Runner —— 最小造数"""
    project = Project(name="确认交互项目", slug=f"cf-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()), title="确认功能", description="d", status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:8]}", created_by=registered_user["user_id"],
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    task = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="dev", title="确认测试任务", description="d",
        base_branch="master", work_branch=f"req-{uuid.uuid4().hex[:6]}",
        status="running", conversation_id=str(uuid.uuid4()),
        created_by=registered_user["user_id"],
    )
    db_session.add(task)
    await db_session.flush()
    return {"project": project, "req": req, "task": task}


async def _mk_running_task_with_runner(db_session, registered_user, register_conn=True):
    """running 任务 + running 容器 + (可选)在线 Runner 连接(stop 收口用)"""
    env = await _mk_task(db_session, registered_user)
    task = env["task"]
    runner_id = f"rn-{uuid.uuid4().hex[:6]}"
    db_session.add(Runner(name=runner_id, role="worker", token_hash="x",
                          status="online", created_by="t"))
    await db_session.flush()
    conn = None
    if register_conn:
        conn = runner_registry.register(runner_id, "worker", FakeRunnerWS(), host="test")
    db_session.add(Container(
        container_id=f"docker-{uuid.uuid4().hex[:8]}", task_id=task.task_id,
        runner_id=runner_id, project_id=task.project_id,
        status="running", image="img", cpu_limit="2c", mem_limit="4g", disk_limit="10g",
    ))
    await db_session.flush()
    env["conn"] = conn
    return env


async def _open_stream(conn, task) -> str:
    """注册一条执行中的流式请求(模拟 send_message_stream 进行中,使 cancel 可追踪)"""
    req_id, _queue = await runner_service.request_runner_stream(
        conn, {"type": "exec_tool", "tool": "claude_prompt_stream", "task_id": task.task_id},
        timeout=60,
    )
    return req_id


def _confirm_delta(prompt="允许执行 Bash(git push) 吗?"):
    """chat_confirm_request 增量(_stream_event_to_chat 分支的产物形态)"""
    return {"type": "chat_confirm_request", "prompt": prompt, "options": ["allow", "deny"]}


# ---------------------------------------------------------------------------
# A. 契约主路径:应答挂起确认 → set_result 放行挂起 Future
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_allow_resolves_pending_future(client, auth_headers, db_session,
                                                     registered_user):
    """成员应答 allow → 200 code=0 data={"ok":true};挂起 Future 收到 "allow" 放行"""
    env = await _mk_task(db_session, registered_user)
    task = env["task"]
    cid = await ts.register_confirm_request(task.task_id, _confirm_delta())
    fut = ts.confirm_futures[cid]

    resp = await client.post(f"/api/tasks/{task.task_id}/confirm",
                             json={"confirm_id": cid, "choice": "allow"},
                             headers=auth_headers)
    assert resp.status_code == 200, f"应 200,实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"] == {"ok": True}, body

    assert fut.done(), "应答后挂起 Future 应完成(放行执行协程)"
    assert fut.result() == "allow", f"Future 结果应为 allow,实际 {fut.result()}"


@pytest.mark.asyncio
async def test_confirm_deny_resolves_pending_future(client, auth_headers, db_session,
                                                    registered_user):
    """成员应答 deny → 挂起 Future 收到 "deny"(AI 收到拒绝结果继续)"""
    env = await _mk_task(db_session, registered_user)
    task = env["task"]
    cid = await ts.register_confirm_request(task.task_id, _confirm_delta())
    fut = ts.confirm_futures[cid]

    resp = await client.post(f"/api/tasks/{task.task_id}/confirm",
                             json={"confirm_id": cid, "choice": "deny"},
                             headers=auth_headers)
    assert resp.status_code == 200, f"应 200,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 0, resp.json()
    assert fut.done() and fut.result() == "deny", \
        f"Future 应以 deny 完成,实际 done={fut.done()}"


@pytest.mark.asyncio
async def test_confirm_twice_second_rejected_4001(client, auth_headers, db_session,
                                                  registered_user):
    """重复应答同一 confirm_id:第一次 200,第二次 code=4001(confirm_id 一次性);
    应答后挂起表已注销该条目"""
    env = await _mk_task(db_session, registered_user)
    task = env["task"]
    cid = await ts.register_confirm_request(task.task_id, _confirm_delta())

    r1 = await client.post(f"/api/tasks/{task.task_id}/confirm",
                           json={"confirm_id": cid, "choice": "allow"}, headers=auth_headers)
    assert r1.status_code == 200 and r1.json()["code"] == 0, r1.text

    assert cid not in ts.confirm_futures, "已应答条目应从挂起表注销"
    r2 = await client.post(f"/api/tasks/{task.task_id}/confirm",
                           json={"confirm_id": cid, "choice": "allow"}, headers=auth_headers)
    assert r2.status_code == 200, f"业务码响应,实际 {r2.status_code}: {r2.text}"
    assert r2.json()["code"] == 4001, f"重复应答应 code=4001,实际 {r2.json()}"


@pytest.mark.asyncio
async def test_confirm_unknown_id_rejected_4001(client, auth_headers, db_session,
                                                registered_user):
    """confirm_id 不存在 → code=4001"""
    env = await _mk_task(db_session, registered_user)
    resp = await client.post(f"/api/tasks/{env['task'].task_id}/confirm",
                             json={"confirm_id": str(uuid.uuid4()), "choice": "allow"},
                             headers=auth_headers)
    assert resp.status_code == 200, f"业务码响应,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 4001, resp.json()


# ---------------------------------------------------------------------------
# B. 鉴权与参数
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_task_not_found_404(client, auth_headers):
    """任务不存在 → 404 统一响应体(code=404「任务不存在」,get_task_or_404 口径)"""
    resp = await client.post(f"/api/tasks/{uuid.uuid4()}/confirm",
                             json={"confirm_id": "x", "choice": "allow"},
                             headers=auth_headers)
    assert resp.status_code == 404, f"应 404,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 404, resp.json()
    assert "任务不存在" in resp.json()["message"], resp.json()


@pytest.mark.asyncio
async def test_confirm_unauthenticated_401(client, db_session, registered_user):
    """未认证 → 401(get_current_user 口径,与 send_message 同)"""
    env = await _mk_task(db_session, registered_user)
    resp = await client.post(f"/api/tasks/{env['task'].task_id}/confirm",
                             json={"confirm_id": "x", "choice": "allow"})
    assert resp.status_code == 401, f"应 401,实际 {resp.status_code}"


@pytest.mark.asyncio
async def test_confirm_non_member_forbidden_403_1901(client, auth_headers, db_session,
                                                     registered_user, second_user_headers):
    """已认证但非项目成员 → 403 code=1901(鉴权=任务成员)"""
    env = await _mk_task(db_session, registered_user)
    resp = await client.post(f"/api/tasks/{env['task'].task_id}/confirm",
                             json={"confirm_id": "x", "choice": "allow"},
                             headers=second_user_headers)
    assert resp.status_code == 403, f"应 403,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1901, resp.json()


@pytest.mark.asyncio
async def test_confirm_invalid_choice_422(client, auth_headers, db_session, registered_user):
    """choice 非法(非 "allow"/"deny")→ 422(Literal 校验)"""
    env = await _mk_task(db_session, registered_user)
    resp = await client.post(f"/api/tasks/{env['task'].task_id}/confirm",
                             json={"confirm_id": "x", "choice": "maybe"},
                             headers=auth_headers)
    assert resp.status_code == 422, f"应 422,实际 {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# C. 负向探查:确认挂起 × 任务停止 → stop 优先,挂起按 deny 收口
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_cancels_pending_confirm_as_deny(client, auth_headers, db_session,
                                                    registered_user):
    """确认挂起期间执行 messages/cancel(停止):挂起确认按 deny 收口 +
    广播 chat_confirm_resolved;此后应答该 confirm_id → 4001(一次性已失效)"""
    env = await _mk_running_task_with_runner(db_session, registered_user)
    task, conn = env["task"], env["conn"]
    reg = _RecordingRegistry()
    saved_registry = ts.task_event_registry
    ts.task_event_registry = reg
    try:
        await _open_stream(conn, task)  # 执行中(生产语义:挂起确认必伴随在途流)
        cid = await ts.register_confirm_request(task.task_id, _confirm_delta())
        fut = ts.confirm_futures[cid]

        resp = await client.post(f"/api/tasks/{task.task_id}/messages/cancel",
                                 headers=auth_headers)
        assert resp.status_code == 200, f"停止应 200,实际 {resp.status_code}: {resp.text}"
        assert resp.json()["data"]["cancelled"] is True, resp.json()

        assert fut.done(), "停止后挂起确认应立即收口"
        assert fut.result() == "deny", f"停止收口应为 deny,实际 {fut.result()}"
        resolved = [f[1] for f in reg.frames if f[1]["type"] == "chat_confirm_resolved"]
        assert len(resolved) == 1, f"应广播恰 1 条 chat_confirm_resolved,实际 {reg.frames}"
        assert resolved[0]["confirm_id"] == cid, resolved
        assert resolved[0]["choice"] == "deny", resolved

        r2 = await client.post(f"/api/tasks/{task.task_id}/confirm",
                               json={"confirm_id": cid, "choice": "allow"},
                               headers=auth_headers)
        assert r2.json()["code"] == 4001, f"停止收口后应答应 4001,实际 {r2.json()}"
    finally:
        ts.task_event_registry = saved_registry
        runner_registry.unregister(conn.runner_id)


# ---------------------------------------------------------------------------
# D. task_service 单元:透传分支 / 挂起表 / 超时 / 清理
# ---------------------------------------------------------------------------
def test_stream_event_permission_maps_to_chat_confirm_request():
    """CLI permission/control 事件 → chat_confirm_request(prompt 人类可读、含工具名
    与关键参数;options 固定两档)。CLI 机制未定:入参样板为 stream-json control 事件,
    rd-dev 实证后如形态不同,改样板不改输出契约"""
    evt = {
        "type": "control_request",
        "request_id": "ctl-1",
        "request": {"subtype": "can_use_tool", "tool_name": "Bash",
                    "input": {"command": "git push origin main", "description": "推送分支"}},
    }
    delta = _stream_event_to_chat(evt)
    assert delta is not None, "permission 事件不得被静默丢弃(BUG-UI-091 根因)"
    assert delta["type"] == "chat_confirm_request", delta
    assert "Bash" in delta["prompt"], f"prompt 应含工具名,实际 {delta['prompt']}"
    assert "git push" in delta["prompt"], f"prompt 应含关键参数,实际 {delta['prompt']}"
    assert delta["options"] == ["allow", "deny"], delta

    # 非 can_use_tool 的 control 事件不产生确认请求(不过度捕获)
    evt2 = {"type": "control_request", "request_id": "c2",
            "request": {"subtype": "interrupt"}}
    assert _stream_event_to_chat(evt2) is None


@pytest.mark.asyncio
async def test_register_confirm_request_broadcasts_and_pends(monkeypatch):
    """register_confirm_request:登记挂起 Future + 广播 chat_confirm_request
    (confirm_id 回填进帧,前端据此弹确认卡)"""
    reg = _RecordingRegistry()
    monkeypatch.setattr(ts, "task_event_registry", reg)
    delta = _confirm_delta()

    cid = await ts.register_confirm_request("t1", delta)

    frames = [f[1] for f in reg.frames if f[1]["type"] == "chat_confirm_request"]
    assert len(frames) == 1, f"应广播恰 1 条确认请求,实际 {reg.frames}"
    assert frames[0]["confirm_id"] == cid, frames
    assert frames[0]["prompt"] == delta["prompt"], frames
    assert frames[0]["options"] == ["allow", "deny"], frames

    assert cid in ts.confirm_futures, "应登记进挂起表"
    assert not ts.confirm_futures[cid].done(), "未应答前 Future 不得完成"
    assert ts.confirm_owners[cid] == "t1", "应登记归属任务(清理反查用)"


@pytest.mark.asyncio
async def test_wait_confirm_returns_user_choice_allow():
    """wait_confirm:用户应答后返回其选择,执行协程放行"""
    cid = await ts.register_confirm_request("t1", _confirm_delta())
    waiter = asyncio.create_task(ts.wait_confirm(cid))
    await asyncio.sleep(0.02)
    assert not waiter.done(), "未应答前执行协程应挂起等待"

    assert ts.resolve_confirm(cid, "allow") is True
    assert await asyncio.wait_for(waiter, timeout=1) == "allow"


@pytest.mark.asyncio
async def test_confirm_timeout_auto_deny_broadcast_resolved(monkeypatch):
    """5min 超时自动 deny(patch CONFIRM_TIMEOUT_SECONDS=0.05 注入,绝不真等):
    wait_confirm 返回 "deny" + 广播 chat_confirm_resolved {choice:"deny",
    reason:"timeout"} + 挂起表注销(此后应答 4001)"""
    monkeypatch.setattr(ts, "CONFIRM_TIMEOUT_SECONDS", 0.05)
    reg = _RecordingRegistry()
    monkeypatch.setattr(ts, "task_event_registry", reg)

    cid = await ts.register_confirm_request("t1", _confirm_delta())
    choice = await ts.wait_confirm(cid)

    assert choice == "deny", f"超时应按 deny 收口,实际 {choice}"
    assert cid not in ts.confirm_futures, "超时后应从挂起表注销"

    resolved = [f[1] for f in reg.frames if f[1]["type"] == "chat_confirm_resolved"]
    assert len(resolved) == 1, f"应广播恰 1 条 resolved,实际 {reg.frames}"
    assert resolved[0] == {"type": "chat_confirm_resolved", "confirm_id": cid,
                           "choice": "deny", "reason": "timeout"}, resolved
    assert ts.resolve_confirm(cid, "allow") is False, "超时收口后 confirm_id 应失效"


@pytest.mark.asyncio
async def test_confirm_id_one_shot_new_request_new_id():
    """confirm_id 一次性:应答后失效;新确认请求分配新 confirm_id 且互不影响"""
    c1 = await ts.register_confirm_request("t1", _confirm_delta("p1"))
    f1 = ts.confirm_futures[c1]
    assert ts.resolve_confirm(c1, "deny") is True
    assert f1.done() and f1.result() == "deny", "首次应答应生效"
    assert ts.resolve_confirm(c1, "allow") is False, "已应答的 confirm_id 不得再次生效"

    c2 = await ts.register_confirm_request("t1", _confirm_delta("p2"))
    assert c2 != c1, "新确认请求不得复用旧 confirm_id"
    assert not ts.confirm_futures[c2].done()


@pytest.mark.asyncio
async def test_cleanup_task_confirms_denies_and_unregisters():
    """任务结束清理挂起表:该任务全部挂起按 deny 收口并注销;
    其他任务挂起不受影响;未知任务清理为 no-op"""
    c1 = await ts.register_confirm_request("t1", _confirm_delta("p1"))
    c2 = await ts.register_confirm_request("t1", _confirm_delta("p2"))
    c3 = await ts.register_confirm_request("t2", _confirm_delta("p3"))
    f1, f2, f3 = ts.confirm_futures[c1], ts.confirm_futures[c2], ts.confirm_futures[c3]

    n = await ts.cleanup_task_confirms("t1")
    assert n == 2, f"应收口 t1 的 2 条挂起,实际 {n}"
    assert f1.done() and f1.result() == "deny", "挂起应按 deny 收口"
    assert f2.done() and f2.result() == "deny", "挂起应按 deny 收口"
    assert c1 not in ts.confirm_futures and c1 not in ts.confirm_owners, "应注销挂起表"
    assert c2 not in ts.confirm_futures and c2 not in ts.confirm_owners, "应注销挂起表"

    assert not f3.done() and c3 in ts.confirm_futures, "其他任务挂起不得被误清"
    assert await ts.cleanup_task_confirms("no-such-task") == 0, "未知任务清理应 no-op"
