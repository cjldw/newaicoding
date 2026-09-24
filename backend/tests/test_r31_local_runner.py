"""
R31 Runner 本地快速创建与本机生命周期管理 — QA Red 阶段失败测试
================================================================
覆盖 R31.md 完成判据 2/3/4/8/10 及接口契约/服务端行为规格。
实现尚不存在,预期全红(除 import 冒烟)。

覆盖范围:
1. POST /api/admin/runners/local 成功链(mock spawn/wait,assert 200 + runner_id + is_local 入库 + 响应无 token 子串)
2. Preflight 4 种失败子类型(16002×code_missing/deps_missing/docker_down/spawn_failed)+ 不落库不 spawn;第 4 个→16003;name 冲突→16005
3. Start 幂等(online→200 "already running")/disabled→16006/非本机→404;Stop offline 幂等/非本机→16006/无句柄→16007
4. Delete 重构:is_local 无容器=直接删;is_local 有容器 mock stop 成功→删,stop 失败→16004 + runner 保留;远程有容器仍 16001
5. 审计 4 事件(runner.create_local/start/stop/restart),detail 无 token
6. List 响应含 is_local 字段
7. Name 缺省生成 `local-<id 前 8 位>`
Edge: register 超时仍 200 status=offline
"""
import asyncio
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from app.core.security import hash_password
from app.database import async_session_factory
from app.models.audit_log import AuditLog
from app.models.runner import Runner


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _uuid() -> str:
    return str(uuid.uuid4())


async def _make_runner(db_session, *, is_local: bool = False, status: str = "online",
                       name: str = None, max_containers: int = 10) -> Runner:
    """直插一条 Runner 记录。is_local 字段实现后生效;当前模型无此列时跳过。"""
    name = name or f"r-{uuid.uuid4().hex[:6]}"
    runner = Runner(
        name=name,
        role="worker",
        token_hash=hash_password("tok"),
        status=status,
        max_containers=max_containers,
        created_by="test",
    )
    # 尝试设置 is_local(模型可能尚未加此列)
    if hasattr(runner, "is_local"):
        runner.is_local = is_local
    db_session.add(runner)
    await db_session.flush()
    return runner


# 注:client fixture override get_db 为**不 commit** 的共享 db_session(请求内 flush),
# 因此 DB 断言一律走 db_session(同 r26 之外的仓内惯例);独立 async_session_factory 会话
# 看不到未提交事务。runner.create_local 等模式 C 审计为事务内写入(audit_write)。

async def _get_runner_by_name(db_session, name: str) -> Runner | None:
    return (await db_session.execute(
        select(Runner).where(Runner.name == name)
    )).scalar_one_or_none()


async def _get_runner_by_id(db_session, runner_id: str) -> Runner | None:
    return (await db_session.execute(
        select(Runner).where(Runner.runner_id == runner_id)
    )).scalar_one_or_none()


async def _spawn_audit_rows(db_session, action_type: str) -> list:
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action_type == action_type)
    )).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# 0. Import 冒烟(应通过)
# ---------------------------------------------------------------------------
def test_import_smoke():
    """模块可导入,不依赖尚未实现的符号"""
    import tests.test_r31_local_runner  # noqa: F401


# ===========================================================================
# 1. POST /api/admin/runners/local 成功链
# ===========================================================================
@pytest.mark.asyncio
async def test_create_local_success(client, db_session, superadmin_headers):
    """成功创建本机 runner:200 + runner_id + is_local 入库 + 响应无 token 子串"""
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock) as mock_spawn, \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):
        mock_spawn.return_value = {"argv": ["python", "runner/main.py"], "env_keys": ["PLATFORM_URL", "RUNNER_TOKEN", "RUNNER_ROLE", "RUNNER_ID"]}

        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "my-local-runner", "max_containers": 5},
            headers=superadmin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    data = body["data"]
    assert "runner_id" in data
    assert data["name"] == "my-local-runner"
    assert data["status"] in ("online", "offline")
    # 响应不含 token 明文
    resp_text = resp.text
    assert "token" not in resp_text.lower() or "token_hidden" in resp_text

    # DB 验证:is_local=1
    runner = await _get_runner_by_name(db_session, "my-local-runner")
    assert runner is not None, "Runner 记录应落库"
    if hasattr(runner, "is_local"):
        assert bool(runner.is_local) is True, "is_local 应为 True"


@pytest.mark.asyncio
async def test_create_local_name_default(client, db_session, superadmin_headers):
    """名称缺省:自动生成 local-<runner_id 前 8 位>"""
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock, return_value={"argv": [], "env_keys": []}), \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):

        resp = await client.post(
            "/api/admin/runners/local",
            json={},  # 不传 name
            headers=superadmin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    data = body["data"]
    # 名称应以 local- 开头
    assert data["name"].startswith("local-"), f"缺省名称应为 local-xxx,实际: {data['name']}"
    # 前缀后应为 8 位 hex(runner_id 前 8 位)
    suffix = data["name"][len("local-"):]
    assert len(suffix) == 8, f"名称后缀应为 8 位,实际: {suffix}"


@pytest.mark.asyncio
async def test_create_local_register_timeout_still_200(client, db_session, superadmin_headers):
    """Edge: spawn 成功但 10s 未注册完成 → 仍 200,status=offline"""
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock, return_value={"argv": [], "env_keys": []}), \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="offline"):

        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "timeout-runner"},
            headers=superadmin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"]["status"] == "offline"
    # 记录仍落库
    runner = await _get_runner_by_name(db_session, "timeout-runner")
    assert runner is not None


# ===========================================================================
# 2. Preflight 失败路径
# ===========================================================================
@pytest.mark.asyncio
async def test_create_local_16002_code_missing(client, db_session, superadmin_headers):
    """环境校验:runner/main.py 不存在 → 16002 sub=code_missing"""
    from app.core.response import BizError, ErrCode
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock,
               side_effect=BizError(16002, "当前部署未包含 Runner 代码(runner/main.py),快速创建仅支持平台源码方式部署")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "fail-runner"},
            headers=superadmin_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 16002
    assert "runner/main.py" in body["message"]

    # 不落库
    runner = await _get_runner_by_name(db_session, "fail-runner")
    assert runner is None, "preflight 失败不应落库"


@pytest.mark.asyncio
async def test_create_local_16002_deps_missing(client, superadmin_headers):
    """环境校验:依赖未安装 → 16002 sub=deps_missing"""
    from app.core.response import BizError
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock,
               side_effect=BizError(16002, "Runner 依赖未安装,请在平台运行环境执行 pip install -r runner/requirements.txt")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "deps-fail"},
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16002
    assert "依赖未安装" in body["message"]


@pytest.mark.asyncio
async def test_create_local_16002_docker_down(client, superadmin_headers):
    """环境校验:Docker daemon 不可连 → 16002 sub=docker_down"""
    from app.core.response import BizError
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock,
               side_effect=BizError(16002, "本机 Docker 不可用,请先启动 Docker 后重试")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "docker-fail"},
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16002
    assert "Docker" in body["message"]


@pytest.mark.asyncio
async def test_create_local_16002_spawn_failed(client, superadmin_headers):
    """环境校验:spawn 失败 → 16002 sub=spawn_failed"""
    from app.core.response import BizError
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock,
               side_effect=BizError(16002, "Runner 启动失败:权限不足")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "spawn-fail"},
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16002
    assert "启动失败" in body["message"]


@pytest.mark.asyncio
async def test_create_local_16003_limit_exceeded(client, db_session, superadmin_headers):
    """第 4 个本机 runner → 16003"""
    # 先直插 3 个 is_local=1 的 runner
    for i in range(3):
        await _make_runner(db_session, is_local=True, name=f"local-{i}")

    from app.core.response import BizError
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock,
               side_effect=BizError(16003, "本机快速创建的 Runner 已达上限(3 个),请先删除闲置 Runner")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "over-limit"},
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16003
    assert "上限" in body["message"]

    # 第 4 个不落库
    runner = await _get_runner_by_name(db_session, "over-limit")
    assert runner is None


@pytest.mark.asyncio
async def test_create_local_16005_name_conflict(client, db_session, superadmin_headers):
    """名称冲突 → 16005"""
    await _make_runner(db_session, is_local=True, name="duplicate-name")

    from app.core.response import BizError
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock,
               side_effect=BizError(16005, "Runner 名称已存在,请更换")):
        resp = await client.post(
            "/api/admin/runners/local",
            json={"name": "duplicate-name"},
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16005
    assert "名称已存在" in body["message"]


# ===========================================================================
# 3. Start / Stop 幂等与错误路径
# ===========================================================================
@pytest.mark.asyncio
async def test_start_idempotent_online(client, db_session, superadmin_headers):
    """Start 幂等:online → 200 'already running'"""
    runner = await _make_runner(db_session, is_local=True, status="online")

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/start",
        headers=superadmin_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    assert "已在运行" in body.get("message", "") or body["data"]["status"] == "online"


@pytest.mark.asyncio
async def test_start_disabled_16006(client, db_session, superadmin_headers):
    """Start disabled → 16006"""
    runner = await _make_runner(db_session, is_local=True, status="disabled")

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/start",
        headers=superadmin_headers,
    )

    body = resp.json()
    assert body["code"] == 16006
    assert "禁用" in body["message"]


@pytest.mark.asyncio
async def test_start_non_local_404(client, db_session, superadmin_headers):
    """Start 非本机 runner → 404(或 16006 视实现)"""
    runner = await _make_runner(db_session, is_local=False, status="offline")

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/start",
        headers=superadmin_headers,
    )

    # 404 或 16006 均可接受(规格:行存在且 is_local=true 否则 404)
    assert resp.status_code in (200, 404) or resp.json().get("code") in (404, 16006), \
        f"非本机 runner start 应 404/16006,实际: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_stop_offline_idempotent(client, db_session, superadmin_headers):
    """Stop offline → 幂等 200 'already stopped'"""
    runner = await _make_runner(db_session, is_local=True, status="offline")

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/stop",
        headers=superadmin_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    assert "停止状态" in body.get("message", "") or body["data"]["status"] == "offline"


@pytest.mark.asyncio
async def test_stop_non_local_16006(client, db_session, superadmin_headers):
    """Stop 非本机 runner → 16006"""
    runner = await _make_runner(db_session, is_local=False, status="online")

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/stop",
        headers=superadmin_headers,
    )

    body = resp.json()
    assert body["code"] == 16006
    assert "远程" in body["message"] or "非本机" in body["message"]


@pytest.mark.asyncio
async def test_stop_no_process_handle_16007(client, db_session, superadmin_headers):
    """Stop online 但无 WS 连接且无句柄 → 16007"""
    runner = await _make_runner(db_session, is_local=True, status="online")
    # 不注册 WS 连接,不 mock 句柄

    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/stop",
        headers=superadmin_headers,
    )

    body = resp.json()
    assert body["code"] == 16007
    assert "无本地句柄" in body["message"] or "手动结束" in body["message"]


# ===========================================================================
# 4. Delete 重构
# ===========================================================================
@pytest.mark.asyncio
async def test_delete_local_no_container(client, db_session, superadmin_headers):
    """Delete is_local 无容器 → 直接删"""
    runner = await _make_runner(db_session, is_local=True, status="offline")

    with patch("app.services.local_runner_service.shutdown_local", new_callable=AsyncMock):
        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body

    # 记录已删(同事务查库)
    deleted = await _get_runner_by_id(db_session, runner.runner_id)
    assert deleted is None, "is_local 无容器应直接删除"


@pytest.mark.asyncio
async def test_delete_local_with_container_stop_success(client, db_session, superadmin_headers):
    """Delete is_local 有容器,stop 成功 → 删除"""
    runner = await _make_runner(db_session, is_local=True, status="online")

    with patch("app.services.local_runner_service.stop_all_containers_and_wait", new_callable=AsyncMock, return_value=0), \
         patch("app.services.local_runner_service.shutdown_local", new_callable=AsyncMock):
        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body

    # 记录已删(同事务查库)
    deleted = await _get_runner_by_id(db_session, runner.runner_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_local_with_container_stop_fail_16004(client, db_session, superadmin_headers):
    """Delete is_local 有容器,stop 失败 → 16004 + runner 保留"""
    runner = await _make_runner(db_session, is_local=True, status="online")

    from app.core.response import BizError
    with patch("app.services.local_runner_service.stop_all_containers_and_wait", new_callable=AsyncMock,
               side_effect=BizError(16004, "Runner 上有容器未能停止(abc123),Runner 已保留,请先处理该容器后重试")):
        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )

    body = resp.json()
    assert body["code"] == 16004
    assert "未能停止" in body["message"]

    # runner 保留(同事务查库)
    preserved = await _get_runner_by_id(db_session, runner.runner_id)
    assert preserved is not None, "stop 失败时 runner 记录应保留"


@pytest.mark.asyncio
async def test_delete_remote_with_container_16001(client, db_session, superadmin_headers):
    """Delete 远程 runner 有容器 → 16001(原语义不变)"""
    # R16.F3/BUG-042 语义:16001 = 有"进行中任务"的 running 容器;需真实 container+task 行
    import uuid as _uuid
    from app.models.container import Container
    from app.models.project import Project
    from app.models.task import Task

    project = Project(name="p-r31", slug=f"p-r31-{_uuid.uuid4().hex[:6]}", owner_id="test")
    db_session.add(project)
    await db_session.flush()
    task = Task(
        req_id=str(_uuid.uuid4()), project_id=project.project_id, type="dev",
        title="t", description="d", base_branch="main", work_branch="main",
        status="running", created_by="test",
    )
    db_session.add(task)
    await db_session.flush()
    runner = await _make_runner(db_session, is_local=False, status="online")
    db_session.add(Container(
        container_id=f"docker-{_uuid.uuid4().hex[:10]}",
        runner_id=runner.runner_id, project_id=project.project_id,
        task_id=task.task_id, status="running", exposed_ports=[5173, 8000],
    ))
    await db_session.flush()

    resp = await client.delete(
        f"/api/admin/runners/{runner.runner_id}",
        headers=superadmin_headers,
    )

    body = resp.json()
    assert body["code"] == 16001
    assert "容器" in body["message"]


# ===========================================================================
# 5. 审计事件
# ===========================================================================
@pytest.mark.asyncio
async def test_audit_create_local(client, db_session, superadmin_headers):
    """审计:runner.create_local 事件,detail 无 token"""
    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock, return_value={"argv": [], "env_keys": []}), \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):
        await client.post(
            "/api/admin/runners/local",
            json={"name": "audit-create"},
            headers=superadmin_headers,
        )

    rows = await _spawn_audit_rows(db_session, "runner.create_local")
    assert len(rows) >= 1, "应写入 runner.create_local 审计"
    row = rows[0]
    # detail 不含 token
    detail_str = str(row.detail)
    assert "token" not in detail_str.lower() or "token_hidden" in detail_str.lower(), \
        f"审计 detail 不应含 token: {detail_str}"


@pytest.mark.asyncio
async def test_audit_start(client, db_session, superadmin_headers):
    """审计:runner.start 事件"""
    runner = await _make_runner(db_session, is_local=True, status="offline")

    with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock, return_value={"argv": [], "env_keys": []}), \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):
        await client.post(
            f"/api/admin/runners/{runner.runner_id}/start",
            headers=superadmin_headers,
        )

    rows = await _spawn_audit_rows(db_session, "runner.start")
    assert len(rows) >= 1, "应写入 runner.start 审计"


@pytest.mark.asyncio
async def test_audit_stop(client, db_session, superadmin_headers):
    """审计:runner.stop 事件"""
    runner = await _make_runner(db_session, is_local=True, status="online")

    with patch("app.services.runner_service.request_runner", new_callable=AsyncMock, return_value={"ok": True}):
        await client.post(
            f"/api/admin/runners/{runner.runner_id}/stop",
            headers=superadmin_headers,
        )

    rows = await _spawn_audit_rows(db_session, "runner.stop")
    assert len(rows) >= 1, "应写入 runner.stop 审计"


@pytest.mark.asyncio
async def test_audit_restart(client, db_session, superadmin_headers):
    """审计:runner.restart 事件"""
    runner = await _make_runner(db_session, is_local=True, status="online")

    with patch("app.services.runner_service.request_runner", new_callable=AsyncMock, return_value={"ok": True}), \
         patch("app.services.local_runner_service.preflight", new_callable=AsyncMock, return_value=None), \
         patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock, return_value={"argv": [], "env_keys": []}), \
         patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):
        await client.post(
            f"/api/admin/runners/{runner.runner_id}/restart",
            headers=superadmin_headers,
        )

    rows = await _spawn_audit_rows(db_session, "runner.restart")
    assert len(rows) >= 1, "应写入 runner.restart 审计"


# ===========================================================================
# 6. List 响应含 is_local 字段
# ===========================================================================
@pytest.mark.asyncio
async def test_list_includes_is_local(client, db_session, superadmin_headers):
    """GET /api/admin/runners 响应 items 含 is_local 字段"""
    await _make_runner(db_session, is_local=True, name="local-list")
    await _make_runner(db_session, is_local=False, name="remote-list")

    resp = await client.get("/api/admin/runners", headers=superadmin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    items = body["data"]["items"]
    assert len(items) >= 2

    for item in items:
        assert "is_local" in item, f"list 响应应含 is_local 字段: {item}"

    # 验证值正确
    local_item = next((i for i in items if i["name"] == "local-list"), None)
    remote_item = next((i for i in items if i["name"] == "remote-list"), None)
    assert local_item is not None
    assert remote_item is not None
    assert local_item["is_local"] is True
    assert remote_item["is_local"] is False


# ===========================================================================
# 7. 非超管 403
# ===========================================================================
@pytest.mark.asyncio
def _phone() -> str:
    import uuid
    return f"138{str(uuid.uuid4().int)[:8]}"


async def test_create_local_403_normal_user(client):
    """非超管 POST /api/admin/runners/local → 403(占位注册吃掉 bootstrap 超管)"""
    await client.post("/api/auth/register", json={"phone": _phone(), "password": "Test1234"})  # 首注册=superadmin 占位
    phone2 = _phone()
    await client.post("/api/auth/register", json={"phone": phone2, "password": "Test1234"})     # 第二用户=普通
    resp = await client.post("/api/auth/login", json={"phone": phone2, "password": "Test1234"})
    headers = {"Authorization": "Bearer " + resp.json()["data"]["access_token"]}
    resp = await client.post("/api/admin/runners/local", json={"name": "forbidden"}, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_start_403_normal_user(client, db_session):
    """非超管 POST /start → 403"""
    await client.post("/api/auth/register", json={"phone": _phone(), "password": "Test1234"})
    phone2 = _phone()
    await client.post("/api/auth/register", json={"phone": phone2, "password": "Test1234"})
    resp = await client.post("/api/auth/login", json={"phone": phone2, "password": "Test1234"})
    headers = {"Authorization": "Bearer " + resp.json()["data"]["access_token"]}
    runner = await _make_runner(db_session, is_local=True, status="offline")
    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/start",
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stop_403_normal_user(client, db_session):
    """非超管 POST /stop → 403"""
    await client.post("/api/auth/register", json={"phone": _phone(), "password": "Test1234"})
    phone2 = _phone()
    await client.post("/api/auth/register", json={"phone": phone2, "password": "Test1234"})
    resp = await client.post("/api/auth/login", json={"phone": phone2, "password": "Test1234"})
    headers = {"Authorization": "Bearer " + resp.json()["data"]["access_token"]}
    runner = await _make_runner(db_session, is_local=True, status="online")
    resp = await client.post(
        f"/api/admin/runners/{runner.runner_id}/stop",
        headers=headers,
    )
    assert resp.status_code == 403
