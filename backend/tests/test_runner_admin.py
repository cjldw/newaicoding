"""
R16 Runner 管理接口测试(后端)
==========================
覆盖:创建(token 一次性)/注册(bcrypt 校验)/心跳(漂移拒绝)/offline 判定
/重置 token(旧失效)/禁用/删除(16001)/对账/DB 调度
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.container import Container
from app.models.project import Project
from app.models.runner import Runner
from app.models.task import Task
from app.services import runner_service


async def _make_runner(db_session, operator_user_id, name=None, role="worker", status="offline"):
    runner, token = await runner_service.create_runner(
        db_session, operator_user_id,
        name=name or f"runner-{uuid.uuid4().hex[:6]}",
        role=role,
    )
    # create 后置状态(注册语义外的直插场景)
    runner.status = status
    await db_session.flush()
    return runner, token


# ---------------------------------------------------------------------------
# 创建 / 重置 / 禁用 / 删除
# ---------------------------------------------------------------------------
class TestRunnerAdmin:
    @pytest.mark.asyncio
    async def test_create_runner_success(self, client, superadmin_headers, db_session):
        """超管创建 Runner:返回一次性 token;平台只存 hash"""
        resp = await client.post(
            "/api/admin/runners",
            headers=superadmin_headers,
            json={"name": f"runner-bj-{uuid.uuid4().hex[:4]}", "role": "worker", "max_containers": 10},
        )
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["token"].startswith("plt-runner-")

        # 非超管 → 19002
        resp = await client.get("/api/admin/runners", headers={"Authorization": "Bearer x"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_deploy_requires_public_ip(self, client, superadmin_headers, db_session):
        """deploy 角色缺公网 IP:拒绝"""
        resp = await client.post(
            "/api/admin/runners",
            headers=superadmin_headers,
            json={"name": f"deploy-{uuid.uuid4().hex[:4]}", "role": "deploy"},
        )
        assert resp.json()["code"] != 0

    @pytest.mark.asyncio
    async def test_reset_token_invalidates_old(self, client, superadmin_headers, db_session):
        """重置 token:新 token 能注册,旧 token 失效"""
        runner, old_token = await _make_runner(db_session, "op", status="online")
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/reset-token",
            headers=superadmin_headers,
        )
        data = resp.json()
        assert data["code"] == 0
        new_token = data["data"]["token"]
        assert new_token != old_token

        # 旧 token 注册失败 / 新 token 成功
        assert await runner_service.handle_register(db_session, old_token, None) is None
        registered = await runner_service.handle_register(db_session, new_token, {"os": "linux"})
        assert registered is not None and registered.runner_id == runner.runner_id

    @pytest.mark.asyncio
    async def test_disable_runner(self, client, superadmin_headers, db_session):
        """禁用 Runner:不再参与调度"""
        runner, token = await _make_runner(db_session, "op", status="online")
        resp = await client.post(
            f"/api/admin/runners/{runner.runner_id}/disable",
            headers=superadmin_headers,
        )
        assert resp.json()["code"] == 0
        await db_session.refresh(runner)
        assert runner.status == "disabled"
        assert await runner_service.pick_runner_db(db_session, "worker") is None

    @pytest.mark.asyncio
    async def test_delete_runner_with_containers(self, client, superadmin_headers, auth_headers,
                                                 db_session, registered_user):
        """Runner 上有进行中任务(running)的运行中容器:删除失败 16001(R16.F3 收窄后语义)"""
        runner, _ = await _make_runner(db_session, "op")
        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        task = Task(
            req_id=str(uuid.uuid4()), project_id=project.project_id, type="dev",
            title="t", description="d", base_branch="main", work_branch="main",
            status="running", created_by=registered_user["user_id"],
        )
        db_session.add(task)
        await db_session.flush()
        db_session.add(Container(
            container_id=f"docker-{uuid.uuid4().hex[:10]}",
            runner_id=runner.runner_id,
            project_id=project.project_id,
            task_id=task.task_id,
            status="running",
            exposed_ports=[5173, 8000],
        ))
        await db_session.flush()

        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )
        assert resp.json()["code"] == 16001

        # 清掉容器后可删除
        result = await db_session.execute(Container.__table__.delete())
        await db_session.flush()
        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )
        assert resp.json()["code"] == 0

    @pytest.mark.asyncio
    async def test_delete_runner_allows_non_running_task_containers(self, client, superadmin_headers,
                                                                    auth_headers, db_session, registered_user):
        """R16.F3/BUG-042:容器在但关联任务已非进行中(cancelled)→ 放行删除;
        以及 task_id 为空的部署容器 → 放行"""
        runner, _ = await _make_runner(db_session, "op")
        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        task = Task(
            req_id=str(uuid.uuid4()), project_id=project.project_id, type="dev",
            title="t", description="d", base_branch="main", work_branch="main",
            status="cancelled", created_by=registered_user["user_id"],
        )
        db_session.add(task)
        await db_session.flush()
        db_session.add(Container(
            container_id=f"docker-{uuid.uuid4().hex[:10]}",
            runner_id=runner.runner_id,
            project_id=project.project_id,
            task_id=task.task_id,
            status="running",
            exposed_ports=[5173],
        ))
        # 部署容器:task_id NULL(R7 deployed 常驻)
        db_session.add(Container(
            container_id=f"docker-{uuid.uuid4().hex[:10]}",
            runner_id=runner.runner_id,
            project_id=project.project_id,
            task_id=None,
            status="running",
            exposed_ports=[80],
        ))
        await db_session.flush()

        resp = await client.delete(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
        )
        assert resp.json()["code"] == 0, resp.text


# ---------------------------------------------------------------------------
# 注册 / 心跳 / offline 判定 / 对账
# ---------------------------------------------------------------------------
class TestRegisterHeartbeat:
    @pytest.mark.asyncio
    async def test_runner_register_success(self, db_session):
        """token 匹配 → online + machine_info;错误 token → None"""
        runner, token = await _make_runner(db_session, "op")

        bad = await runner_service.handle_register(db_session, "plt-runner-wrong", {"os": "linux"})
        assert bad is None

        ok = await runner_service.handle_register(db_session, token, {"os": "linux", "cpu_count": 8})
        assert ok is not None
        assert ok.status == "online"
        assert ok.machine_info["cpu_count"] == 8

    @pytest.mark.asyncio
    async def test_runner_register_disabled_rejected(self, db_session):
        """disabled Runner 的 token 不允许注册"""
        runner, token = await _make_runner(db_session, "op", status="disabled")
        assert await runner_service.handle_register(db_session, token, None) is None

    @pytest.mark.asyncio
    async def test_runner_heartbeat(self, db_session):
        """心跳更新 last_heartbeat_at;漂移 >5min 拒绝"""
        runner, _ = await _make_runner(db_session, "op", status="online")
        before = runner.last_heartbeat_at

        ok = await runner_service.handle_heartbeat(db_session, runner, datetime.now(timezone.utc).timestamp())
        assert ok is True
        assert runner.last_heartbeat_at is not None
        if before is not None:
            assert runner.last_heartbeat_at >= before

        # 时钟漂移 6 分钟 → 拒绝
        drift_ts = (datetime.now(timezone.utc) - timedelta(minutes=6)).timestamp()
        ok = await runner_service.handle_heartbeat(db_session, runner, drift_ts)
        assert ok is False

    @pytest.mark.asyncio
    async def test_runner_offline_detection(self, db_session):
        """心跳超 60s:巡检标 offline"""
        runner, _ = await _make_runner(db_session, "op", status="online")
        runner.last_heartbeat_at = (datetime.now(timezone.utc) - timedelta(seconds=61)).replace(tzinfo=None)
        await db_session.flush()

        count = await runner_service.sweep_offline(db_session)
        assert count >= 1
        await db_session.refresh(runner)
        assert runner.status == "offline"

    @pytest.mark.asyncio
    async def test_runner_sync_reconcile(self, db_session, registered_user):
        """恢复对账:DB 有上报无 → destroyed;状态不一致以 Runner 为准"""
        runner, _ = await _make_runner(db_session, "op", status="online")
        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        still_running = Container(
            container_id="docker-keep", runner_id=runner.runner_id,
            project_id=project.project_id, status="running", exposed_ports=[],
        )
        gone = Container(
            container_id="docker-gone", runner_id=runner.runner_id,
            project_id=project.project_id, status="running", exposed_ports=[],
        )
        mismatched = Container(
            container_id="docker-mismatch", runner_id=runner.runner_id,
            project_id=project.project_id, status="running", exposed_ports=[],
        )
        db_session.add_all([still_running, gone, mismatched])
        await db_session.flush()

        await runner_service.handle_sync(db_session, runner, [
            {"container_id": "docker-keep", "status": "running"},
            {"container_id": "docker-mismatch", "status": "stopped"},
        ])
        await db_session.refresh(gone)
        await db_session.refresh(mismatched)
        assert gone.status == "destroyed"           # DB 有上报无 → destroyed
        assert mismatched.status == "stopped"       # 以 Runner 上报为准
        assert still_running.status == "running"
        assert runner.current_containers == 1       # 只有 keep 计入
