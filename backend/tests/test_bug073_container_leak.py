"""
BUG-073 容器泄漏修复测试(R3.F3)
================================
4 条泄漏路径的 TDD 验证:
- F2.a: request_stop 等回报 + 超时兜底
- F2.b: Runner 离线分支补发 stop
- F2.c: retry_task 清旧容器
- F2.d: lifespan 启动孤儿对账
- F2.e: finish_task / sweep_timeouts 收所有 running 容器(非 limit(1))

测试策略:
- docker/Runner 外部依赖全 mock(不碰真 docker)
- 使用 test 库(aicoding_test),沿用 conftest.py fixture
- 串行跑(pytest -p no:asyncio 或默认单线程)
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from app.models.container import Container
from app.models.project import Project, ProjectRepo
from app.models.requirement import Requirement
from app.models.runner import Runner
from app.models.task import Task
from app.models.user import User
from app.services import container_service, runner_service, task_service
from app.services.runner_service import runner_registry


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
async def _insert_runner(db_session, name="runner-a", role="worker", status="online",
                         current=0, maximum=10):
    """直插 Runner 行"""
    r = Runner(
        name=name,
        role=role,
        token_hash="placeholder-hash",
        status=status,
        current_containers=current,
        max_containers=maximum,
        created_by="test",
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _insert_container(db_session, project_id, runner_id="r-1", status="running",
                            container_id=None, task_id=None):
    """直插 Container 行"""
    c = Container(
        container_id=container_id or f"docker-{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        runner_id=runner_id,
        project_id=project_id,
        status=status,
        image="platform/devbox:v2",
        exposed_ports=[5173, 8000],
    )
    db_session.add(c)
    await db_session.flush()
    return c


async def _insert_task(db_session, project_id, req_id, status="running", created_by="test-user"):
    """直插 Task 行"""
    t = Task(
        req_id=req_id,
        project_id=project_id,
        type="dev",
        title=f"test-task-{uuid.uuid4().hex[:6]}",
        description="test description",
        base_branch="master",
        work_branch="work",
        status=status,
        created_by=created_by,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) if status == "running" else None,
    )
    db_session.add(t)
    await db_session.flush()
    return t


async def _insert_requirement(db_session, project_id, created_by="test-user"):
    """直插 Requirement 行"""
    req = Requirement(
        project_id=project_id,
        title=f"test-req-{uuid.uuid4().hex[:6]}",
        description="test description",
        status="approved",
        req_branch=f"req-{uuid.uuid4().hex[:6]}",
        created_by=created_by,
    )
    db_session.add(req)
    await db_session.flush()
    return req


# ---------------------------------------------------------------------------
# F2.a: request_stop 等回报 + 超时兜底
# ---------------------------------------------------------------------------
class TestRequestStopTimeout:
    """F2.a: request_stop 下发后等 Runner container_stopped 回报,超时 60s 未回报 → 直接置 destroyed"""

    @pytest.mark.asyncio
    async def test_request_stop_timeout_force_destroy(self, db_session, monkeypatch):
        """Runner 无回报 → 超时后容器置 destroyed + destroyed_at"""
        runner = await _insert_runner(db_session, "r-timeout", current=1)
        project = Project(name="p-timeout", slug=f"pt-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-timeout-1", task_id="task-timeout"
        )

        # mock Runner 连接存在,但不回报 container_stopped
        conn = runner_registry.register(runner.runner_id, "worker", None, "10.0.0.1")

        sent_messages = []

        async def fake_send(c, message):
            sent_messages.append(message)
            # 模拟 Runner 不回报(不触发 handle_container_stopped)

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        # 调用 request_stop,应等待回报超时后强制置 destroyed
        # 为避免测试等 60s,patch 超时时间为 0.1s
        with patch("app.services.container_service.STOP_TIMEOUT_SECONDS", 0.1):
            await container_service.request_stop(db_session, container)

        # 验证:下发了 stop_container 消息
        assert len(sent_messages) == 1
        assert sent_messages[0]["type"] == "stop_container"
        assert sent_messages[0]["container_id"] == "docker-timeout-1"

        # 验证:超时后容器状态置为 destroyed + destroyed_at 非空
        await db_session.refresh(container)
        assert container.status == "destroyed", f"期望 destroyed,实际 {container.status}"
        assert container.destroyed_at is not None, "destroyed_at 应被设置"

        runner_registry.unregister(runner.runner_id)

    @pytest.mark.asyncio
    async def test_request_stop_normal_path_waits_for_report(self, db_session, monkeypatch):
        """Runner 正常回报 → 容器置 destroyed(由 handle_container_stopped 处理)"""
        runner = await _insert_runner(db_session, "r-normal", current=1)
        project = Project(name="p-normal", slug=f"pn-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-normal-1", task_id="task-normal"
        )

        conn = runner_registry.register(runner.runner_id, "worker", None, "10.0.0.2")

        async def fake_send(c, message):
            # 模拟 Runner 立即回报 container_stopped
            await container_service.handle_container_stopped(db_session, "docker-normal-1")

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        with patch("app.services.container_service.STOP_TIMEOUT_SECONDS", 5.0):
            await container_service.request_stop(db_session, container)

        await db_session.refresh(container)
        assert container.status == "destroyed"
        assert container.destroyed_at is not None

        runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# F2.b: Runner 离线分支补发 stop
# ---------------------------------------------------------------------------
class TestRunnerOfflineResend:
    """F2.b: Runner 离线时容器标 stopped + destroyed_at NULL,Runner 恢复后补发 stop"""

    @pytest.mark.asyncio
    async def test_runner_offline_marks_stopped(self, db_session, monkeypatch):
        """Runner 离线 → 容器标 stopped + destroyed_at NULL"""
        runner = await _insert_runner(db_session, "r-offline", current=1)
        project = Project(name="p-offline", slug=f"po-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-offline-1", task_id="task-offline"
        )

        # Runner 不在线(runner_registry 无连接)
        assert runner_registry.get(runner.runner_id) is None

        await container_service.request_stop(db_session, container)

        await db_session.refresh(container)
        assert container.status == "stopped", f"期望 stopped,实际 {container.status}"
        assert container.destroyed_at is None, "destroyed_at 应为 NULL(待补发)"

    @pytest.mark.asyncio
    async def test_runner_reconnect_resends_stop(self, db_session, monkeypatch):
        """Runner 重连后,对 stopped + destroyed_at NULL 的容器补发 stop"""
        runner = await _insert_runner(db_session, "r-reconnect", current=1)
        project = Project(name="p-reconnect", slug=f"pr-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        # 容器已标 stopped( Runner 离线时标记)
        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="stopped", container_id="docker-reconnect-1", task_id="task-reconnect"
        )
        container.destroyed_at = None
        await db_session.flush()

        # 模拟 Runner 重连(注册连接)
        runner_registry.register(runner.runner_id, "worker", None, "10.0.0.3")

        # 模拟 Runner 重连,触发补发逻辑
        sent_messages = []

        async def fake_send(c, message):
            sent_messages.append(message)

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        # 调用补发函数(由 runner_ws.py register 或周期巡检调用)
        await container_service.resend_stop_for_offline_containers(db_session, runner.runner_id)

        # 验证:补发了 stop_container 消息
        assert len(sent_messages) == 1
        assert sent_messages[0]["type"] == "stop_container"
        assert sent_messages[0]["container_id"] == "docker-reconnect-1"

        runner_registry.unregister(runner.runner_id)

    @pytest.mark.asyncio
    async def test_runner_ws_register_calls_resend_stop(self, db_session, monkeypatch):
        """F2.b 接线验证:runner_ws.py register 流程调用 resend_stop_for_offline_containers"""
        from app.api import runner_ws as runner_ws_module

        runner = await _insert_runner(db_session, "r-ws-register", current=1)
        project = Project(name="p-ws-register", slug=f"pws-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        # 容器已标 stopped(待补发)
        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="stopped", container_id="docker-ws-1", task_id="task-ws-1"
        )
        container.destroyed_at = None
        await db_session.flush()

        # mock runner_registry.register
        runner_registry.register(runner.runner_id, "worker", None, "10.0.0.4")

        # mock resend_stop_for_offline_containers 追踪调用
        resend_called = []

        async def fake_resend(db, runner_id):
            resend_called.append(runner_id)

        monkeypatch.setattr(container_service, "resend_stop_for_offline_containers", fake_resend)

        # mock async_session_factory 返回测试 db session
        from app.database import async_session_factory as real_factory
        from unittest.mock import AsyncMock

        class FakeSessionContext:
            def __init__(self):
                self.session = db_session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(runner_ws_module, "async_session_factory", lambda: FakeSessionContext())

        # 模拟 WebSocket register 流程
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_json = AsyncMock(side_effect=[
            {"type": "register", "token": "placeholder-hash", "machine_info": {}},
            WebSocketDisconnect(),
        ])
        mock_ws.send_json = AsyncMock()
        mock_ws.client = MagicMock()
        mock_ws.client.host = "10.0.0.4"

        # mock handle_register 返回 runner
        async def fake_handle_register(db, token, machine_info):
            return runner

        monkeypatch.setattr(runner_service, "handle_register", fake_handle_register)

        # 执行 runner_ws 主函数
        await runner_ws_module.runner_ws(mock_ws)

        # 验证:resend_stop_for_offline_containers 被调用
        assert len(resend_called) == 1, f"resend 应被调用 1 次,实际 {len(resend_called)}"
        assert resend_called[0] == runner.runner_id

        runner_registry.unregister(runner.runner_id)


# ---------------------------------------------------------------------------
# F2.c: retry_task 清旧容器
# ---------------------------------------------------------------------------
class TestRetryTaskCleanup:
    """F2.c: retry_task 前清旧容器(status IN (running, creating) → request_stop + destroyed)"""

    @pytest.mark.asyncio
    async def test_retry_task_cleans_old_running_containers(self, db_session, monkeypatch, client, auth_headers, registered_user):
        """retry_task 前清旧 running 容器"""
        runner = await _insert_runner(db_session, "r-retry", current=2)
        project = Project(name="p-retry", slug=f"pry-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id, created_by=registered_user["user_id"])

        task = await _insert_task(db_session, project.project_id, req.req_id, status="cancelled",
                                  created_by=registered_user["user_id"])

        # 旧 running 容器(应被清理)
        old_container_1 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-old-1", task_id=task.task_id
        )
        old_container_2 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-old-2", task_id=task.task_id
        )

        # mock start_task(避免真实调度和启动)
        async def fake_start_task(db, task, project, requirement):
            # 模拟新建容器
            new_container = Container(
                container_id=f"docker-new-{uuid.uuid4().hex[:6]}",
                task_id=task.task_id,
                runner_id=runner.runner_id,
                project_id=project.project_id,
                status="creating",
                image="platform/devbox:v2",
                exposed_ports=[5173, 8000],
            )
            db_session.add(new_container)
            await db_session.flush()
            return new_container

        monkeypatch.setattr(task_service, "start_task", fake_start_task)

        # mock request_stop(避免真实下发)
        stopped_containers = []

        async def fake_request_stop(db, container):
            container.status = "destroyed"
            container.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            stopped_containers.append(container.container_id)
            await db.flush()

        monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

        # 执行 retry_task
        await task_service.retry_task(db_session, task)

        # 验证:旧 running 容器被清理(置 destroyed)
        await db_session.refresh(old_container_1)
        await db_session.refresh(old_container_2)
        assert old_container_1.status == "destroyed", f"旧容器 1 应 destroyed,实际 {old_container_1.status}"
        assert old_container_2.status == "destroyed", f"旧容器 2 应 destroyed,实际 {old_container_2.status}"
        assert len(stopped_containers) == 2, f"应调用 2 次 request_stop,实际 {len(stopped_containers)}"


# ---------------------------------------------------------------------------
# F2.d: lifespan 启动孤儿对账
# ---------------------------------------------------------------------------
class TestLifespanOrphanReconciliation:
    """F2.d: lifespan 启动时扫描 running/creating 容器,对账 docker 真实状态"""

    @pytest.mark.asyncio
    async def test_lifespan_destroys_orphan_containers(self, db_session, monkeypatch):
        """DB running 但 docker 明确无此容器(exists=False) → 置 destroyed"""
        runner = await _insert_runner(db_session, "r-orphan", current=2)
        project = Project(name="p-orphan", slug=f"por-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        # 孤儿容器(docker 侧明确不存在)
        orphan_1 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-orphan-1", task_id="task-orphan-1"
        )
        orphan_2 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="creating", container_id="docker-orphan-2", task_id="task-orphan-2"
        )

        # mock docker inspect:明确证据表明不存在
        async def fake_inspect(container_id):
            return {"exists": False}

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect)

        # 执行孤儿对账
        await container_service.reconcile_orphan_containers(db_session)

        # 验证:孤儿容器置 destroyed
        await db_session.refresh(orphan_1)
        await db_session.refresh(orphan_2)
        assert orphan_1.status == "destroyed", f"孤儿 1 应 destroyed,实际 {orphan_1.status}"
        assert orphan_2.status == "destroyed", f"孤儿 2 应 destroyed,实际 {orphan_2.status}"

    @pytest.mark.asyncio
    async def test_lifespan_inspect_unknown_skips_container(self, db_session, monkeypatch):
        """F2.d fail-safe:inspect 返回 None(未知) → 跳过,绝不置 destroyed(防数据损坏)"""
        runner = await _insert_runner(db_session, "r-unknown", current=1)
        project = Project(name="p-unknown", slug=f"pun-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        # running 容器,inspect 无结论
        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-unknown-1", task_id="task-unknown-1"
        )

        # mock inspect 返回 None(未知/未实现)
        async def fake_inspect_none(container_id):
            return None

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect_none)

        await container_service.reconcile_orphan_containers(db_session)

        # 验证:容器状态不变(不被误杀)
        await db_session.refresh(container)
        assert container.status == "running", f"inspect 无结论时不应改变状态,实际 {container.status}"
        assert container.destroyed_at is None, "destroyed_at 应保持 NULL"

    @pytest.mark.asyncio
    async def test_lifespan_inspect_exception_skips_container(self, db_session, monkeypatch):
        """F2.d fail-safe:inspect 抛异常 → 跳过,绝不置 destroyed"""
        runner = await _insert_runner(db_session, "r-exception", current=1)
        project = Project(name="p-exception", slug=f"pex-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-exception-1", task_id="task-exception-1"
        )

        # mock inspect 抛异常
        async def fake_inspect_error(container_id):
            raise ConnectionError("Runner 不可达")

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect_error)

        await container_service.reconcile_orphan_containers(db_session)

        # 验证:容器状态不变(不被误杀)
        await db_session.refresh(container)
        assert container.status == "running", f"inspect 异常时不应改变状态,实际 {container.status}"
        assert container.destroyed_at is None, "destroyed_at 应保持 NULL"

    @pytest.mark.asyncio
    async def test_lifespan_stops_container_if_task_terminal(self, db_session, monkeypatch):
        """docker 有容器但对应 task 已终态 → 后台补发 stop(asyncio.create_task)"""
        runner = await _insert_runner(db_session, "r-terminal", current=1)
        project = Project(name="p-terminal", slug=f"pte-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id)
        task = await _insert_task(db_session, project.project_id, req.req_id, status="cancelled")

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-terminal-1", task_id=task.task_id
        )

        # mock docker inspect(容器存在)
        async def fake_inspect(container_id):
            return {"exists": True, "State": {"Status": "running"}}

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect)

        # mock _dispatch_stop_in_background 追踪调用(同步函数,返回协程)
        dispatched = []

        def fake_dispatch(container_id):
            dispatched.append(container_id)  # 立即追加,不等协程执行
            async def noop():
                pass
            return noop()

        monkeypatch.setattr(container_service, "_dispatch_stop_in_background", fake_dispatch)

        # 执行孤儿对账
        await container_service.reconcile_orphan_containers(db_session)

        # 验证:补发了 stop(后台派发,task 已终态)
        assert len(dispatched) == 1
        assert dispatched[0] == "docker-terminal-1"

    @pytest.mark.asyncio
    async def test_lifespan_inspect_unknown_but_task_terminal_dispatches_stop(self, db_session, monkeypatch):
        """F2.d 修正:inspect 无结论 + task 终态 → 仍补发 stop(不阻断)"""
        runner = await _insert_runner(db_session, "r-unknown-terminal", current=1)
        project = Project(name="p-unknown-terminal", slug=f"put-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id)
        task = await _insert_task(db_session, project.project_id, req.req_id, status="done")

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-unknown-terminal-1", task_id=task.task_id
        )

        # mock inspect 返回 None(未知)
        async def fake_inspect_none(container_id):
            return None

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect_none)

        # mock _dispatch_stop_in_background 追踪调用(同步函数,返回协程)
        dispatched = []

        def fake_dispatch(container_id):
            dispatched.append(container_id)  # 立即追加,不等协程执行
            async def noop():
                pass
            return noop()

        monkeypatch.setattr(container_service, "_dispatch_stop_in_background", fake_dispatch)

        await container_service.reconcile_orphan_containers(db_session)

        # 验证:inspect 无结论但 task 终态 → 仍补发 stop
        assert len(dispatched) == 1, f"应派发 1 条补发,实际 {len(dispatched)}"
        assert dispatched[0] == "docker-unknown-terminal-1"

        # 验证:容器状态不变(不被直接置 destroyed)
        await db_session.refresh(container)
        assert container.status == "running", f"inspect 无结论时不应直接置 destroyed,实际 {container.status}"

    @pytest.mark.asyncio
    async def test_lifespan_inspect_unknown_and_task_running_no_action(self, db_session, monkeypatch):
        """F2.d:inspect 无结论 + task running → 不杀不动"""
        runner = await _insert_runner(db_session, "r-unknown-running", current=1)
        project = Project(name="p-unknown-running", slug=f"pur-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id)
        task = await _insert_task(db_session, project.project_id, req.req_id, status="running")

        container = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-unknown-running-1", task_id=task.task_id
        )

        # mock inspect 返回 None(未知)
        async def fake_inspect_none(container_id):
            return None

        monkeypatch.setattr(container_service, "inspect_container_docker", fake_inspect_none)

        # mock _dispatch_stop_in_background 追踪调用(同步函数,返回协程)
        dispatched = []

        def fake_dispatch(container_id):
            dispatched.append(container_id)  # 立即追加,不等协程执行
            async def noop():
                pass
            return noop()

        monkeypatch.setattr(container_service, "_dispatch_stop_in_background", fake_dispatch)

        await container_service.reconcile_orphan_containers(db_session)

        # 验证:inspect 无结论 + task running → 不补发 stop
        assert len(dispatched) == 0, f"task running 时不应派发补发,实际 {len(dispatched)}"

        # 验证:容器状态不变
        await db_session.refresh(container)
        assert container.status == "running", f"不应改变状态,实际 {container.status}"
        assert container.destroyed_at is None, "destroyed_at 应保持 NULL"


# ---------------------------------------------------------------------------
# F2.e: finish_task / sweep_timeouts 收所有 running 容器
# ---------------------------------------------------------------------------
class TestFinishTaskAllContainers:
    """F2.e: finish_task / sweep_timeouts 收所有 running 容器(非 limit(1))"""

    @pytest.mark.asyncio
    async def test_finish_task_stops_all_running_containers(self, db_session, monkeypatch, client, auth_headers, registered_user):
        """finish_task 对所有 running 容器发收容(构造多条 running 断言不漏)"""
        runner = await _insert_runner(db_session, "r-finish", current=3)
        project = Project(name="p-finish", slug=f"pfi-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id, created_by=registered_user["user_id"])
        task = await _insert_task(db_session, project.project_id, req.req_id, status="running",
                                  created_by=registered_user["user_id"])

        # 同 task 多条 running 容器(实证路径 1)
        container_1 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-finish-1", task_id=task.task_id
        )
        container_2 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-finish-2", task_id=task.task_id
        )
        container_3 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-finish-3", task_id=task.task_id
        )

        # mock request_stop
        stopped_containers = []

        async def fake_request_stop(db, c):
            stopped_containers.append(c.container_id)
            c.status = "destroyed"
            c.destroyed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.flush()

        monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

        # mock git commit/push(避免真实调用)
        async def fake_request_runner(*args, **kwargs):
            return {"ok": True}

        monkeypatch.setattr(runner_service, "request_runner", fake_request_runner)

        # mock operator
        operator = User(
            user_id=registered_user["user_id"],
            phone=registered_user["phone"],
            role="user",
        )

        # 执行 finish_task
        await task_service.finish_task(db_session, task, operator, status="done")

        # 验证:所有 running 容器都被收容
        assert len(stopped_containers) == 3, f"应调用 3 次 request_stop,实际 {len(stopped_containers)}"
        assert set(stopped_containers) == {"docker-finish-1", "docker-finish-2", "docker-finish-3"}

    @pytest.mark.asyncio
    async def test_sweep_timeouts_stops_all_running_containers(self, db_session, monkeypatch):
        """sweep_timeouts 对所有 running 容器发收容(非 limit(1))"""
        runner = await _insert_runner(db_session, "r-sweep", current=2)
        project = Project(name="p-sweep", slug=f"psw-{uuid.uuid4().hex[:8]}", owner_id="test-user")
        db_session.add(project)
        await db_session.flush()

        req = await _insert_requirement(db_session, project.project_id)

        # 超时任务(started_at > 60 分钟前)
        task = Task(
            req_id=req.req_id,
            project_id=project.project_id,
            type="dev",
            title="timeout-task",
            description="test description",
            base_branch="master",
            work_branch="work",
            status="running",
            created_by="test-user",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=61),
        )
        db_session.add(task)
        await db_session.flush()

        # 同 task 多条 running 容器
        container_1 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-sweep-1", task_id=task.task_id
        )
        container_2 = await _insert_container(
            db_session, project.project_id, runner_id=runner.runner_id,
            status="running", container_id="docker-sweep-2", task_id=task.task_id
        )

        # mock request_stop
        stopped_containers = []

        async def fake_request_stop(db, c):
            stopped_containers.append(c.container_id)

        monkeypatch.setattr(container_service, "request_stop", fake_request_stop)

        # 执行 sweep_timeouts
        count = await task_service.sweep_timeouts(db_session)

        # 验证:任务转 timeout
        assert count == 1
        await db_session.refresh(task)
        assert task.status == "timeout"

        # 验证:所有 running 容器都被收容
        assert len(stopped_containers) == 2, f"应调用 2 次 request_stop,实际 {len(stopped_containers)}"
        assert set(stopped_containers) == {"docker-sweep-1", "docker-sweep-2"}
