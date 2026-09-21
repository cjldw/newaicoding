"""
R8 容器平台侧测试(调度/配额/回报处理)
==========================
Runner 程序本体测试见 runner/tests/(独立目录,不依赖 docker SDK)。
"""
import pytest

from app.models.container import Container
from app.models.project import Project, PlatformSetting
from app.services import container_service
from app.services.runner_service import RunnerConnection, RunnerRegistry


async def _insert_container(db_session, project_id, runner_id="r-1", status="running",
                            container_id=None, task_id=None):
    c = Container(
        container_id=container_id or f"docker-{uuid4_hex()}",
        task_id=task_id,
        runner_id=runner_id,
        project_id=project_id,
        status=status,
        image="platform/devbox:v1",
        exposed_ports=[5173, 8000],
    )
    db_session.add(c)
    await db_session.flush()
    return c


def uuid4_hex():
    import uuid
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# 调度器
# ---------------------------------------------------------------------------
class TestScheduler:
    def test_schedule_runner_least_loaded(self):
        """调度器选最少负载 Runner;负载相同随机(本用例两条最少负载均可)"""
        registry = RunnerRegistry()
        r1 = RunnerConnection(runner_id="r1", role="general", load=3)
        r2 = RunnerConnection(runner_id="r2", role="general", load=1)
        r3 = RunnerConnection(runner_id="r3", role="general", load=2)
        for r in (r1, r2, r3):
            registry.register(r.runner_id, r.role, None, "")
            registry._runners[r.runner_id].load = r.load

        picked = registry.pick_runner("general")
        assert picked.runner_id == "r2"

    def test_schedule_runner_deploy_role(self):
        """部署任务只选 deploy Runner;普通任务不占用 deploy Runner"""
        registry = RunnerRegistry()
        registry.register("deploy-1", "deploy", None, "")
        registry.register("general-1", "general", None, "")
        registry._runners["deploy-1"].load = 5
        registry._runners["general-1"].load = 0

        # 部署任务:负载 5 也只能选 deploy
        assert registry.pick_runner("deploy").runner_id == "deploy-1"
        # 普通任务:不选 deploy
        assert registry.pick_runner("general").runner_id == "general-1"

    def test_no_runner_available(self):
        """无匹配 Runner 返回 None(服务层转 8003)"""
        registry = RunnerRegistry()
        assert registry.pick_runner("deploy") is None


# ---------------------------------------------------------------------------
# 配额
# ---------------------------------------------------------------------------
class TestQuotas:
    @pytest.mark.asyncio
    async def test_user_container_limit(self, client, auth_headers, db_session, registered_user):
        """单用户同时运行容器 >5:8001"""
        project = Project(name="p", slug=f"p-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        for _ in range(5):
            await _insert_container(db_session, project.project_id, status="running")

        with pytest.raises(Exception) as exc_info:
            await container_service.check_quotas(db_session, registered_user["user_id"])
        assert getattr(exc_info.value, "code", None) == 8001

    @pytest.mark.asyncio
    async def test_platform_container_limit(self, client, auth_headers, db_session, registered_user):
        """平台总容器数超限(max_containers_total):8002"""
        # 设置平台上限为 1
        db_session.add(PlatformSetting(key="max_containers_total", value=1, updated_by="t"))
        project = Project(name="p2", slug=f"p2-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        await _insert_container(db_session, project.project_id, status="running")

        # 另一个用户名下再检查:平台总数已 1 >= 上限 1 → 8002
        other_user_id = f"00000000-0000-0000-0000-{uuid4_hex()}"
        with pytest.raises(Exception) as exc_info:
            await container_service.check_quotas(db_session, other_user_id)
        assert getattr(exc_info.value, "code", None) == 8002


# ---------------------------------------------------------------------------
# 回报处理
# ---------------------------------------------------------------------------
class TestRunnerReports:
    @pytest.mark.asyncio
    async def test_container_started_update_db(self, client, auth_headers, db_session, registered_user):
        """container_started 回报后:status=running,端口映射入库,占位 id 替换"""
        project = Project(name="p3", slug=f"p3-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        c = await _insert_container(db_session, project.project_id, status="creating", task_id="task-abc")

        await container_service.handle_container_started(
            db_session, task_id="task-abc", docker_container_id="docker-real-1",
            ports={"5173": 20001, "8000": 20002},
        )
        await db_session.refresh(c)
        assert c.status == "running"
        assert c.container_id == "docker-real-1"
        assert c.runner_host_port_5173 == 20001
        assert c.runner_host_port_8000 == 20002

    @pytest.mark.asyncio
    async def test_container_event_die_update_db(self, client, auth_headers, db_session, registered_user):
        """die 事件回报后:status=failed"""
        project = Project(name="p4", slug=f"p4-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        c = await _insert_container(db_session, project.project_id, status="running",
                                    container_id="docker-die-1")

        await container_service.handle_container_event(
            db_session, event="die", docker_container_id="docker-die-1", exit_code=1
        )
        await db_session.refresh(c)
        assert c.status == "failed"

    @pytest.mark.asyncio
    async def test_container_stopped_update_db(self, client, auth_headers, db_session, registered_user):
        """container_stopped 回报后:destroyed + destroyed_at;调度负载减一"""
        project = Project(name="p5", slug=f"p5-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        await _insert_container(db_session, project.project_id, status="running",
                                container_id="docker-stop-1")

        from app.services.runner_service import runner_registry
        conn = runner_registry.register("r-1", "general", None, "")
        conn.load = 1

        await container_service.handle_container_stopped(db_session, "docker-stop-1")
        result = await db_session.execute(
            Container.__table__.select().where(Container.container_id == "docker-stop-1")
        )
        row = result.mappings().first()
        assert row["status"] == "destroyed"
        assert row["destroyed_at"] is not None
        assert conn.load == 0
        runner_registry.unregister("r-1")


# ---------------------------------------------------------------------------
# 调度 + 下发(schedule_and_start,注入假 registry 与假 send)
# ---------------------------------------------------------------------------
class TestScheduleAndStart:
    @pytest.mark.asyncio
    async def test_schedule_and_start_sends_message(self, client, auth_headers, db_session,
                                                    registered_user, monkeypatch):
        """正常路径:登记 creating 行并下发 start_container 消息"""
        from app.services import runner_service as rs

        project = Project(name="p6", slug=f"p6-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        # 假 runner 注册表
        registry = RunnerRegistry()
        conn = registry.register("runner-x", "general", None, "10.0.0.1")
        monkeypatch.setattr(container_service, "runner_registry", registry)

        sent = []

        async def fake_send(c, message):
            sent.append(message)

        monkeypatch.setattr(rs, "send_to_runner", fake_send)

        container = await container_service.schedule_and_start(
            db_session,
            project_id=project.project_id,
            task_id="task-xyz",
            owner_user_id=registered_user["user_id"],
            env={"GITLAB_TOKEN": "x"},
            repos=[{"url": "https://gitlab.example.com/g/r.git", "path": "/workspace/r", "branch": "req-1"}],
        )
        assert container.status == "creating"
        assert container.runner_id == "runner-x"
        assert len(sent) == 1
        msg = sent[0]
        assert msg["type"] == "start_container"
        assert msg["task_id"] == "task-xyz"
        assert msg["ports"] == [5173, 8000]
        assert msg["repos"][0]["branch"] == "req-1"
        assert conn.load == 1

    @pytest.mark.asyncio
    async def test_no_runner_returns_8003(self, client, auth_headers, db_session, registered_user, monkeypatch):
        """无可用 Runner:8003"""
        from app.services import runner_service as rs

        project = Project(name="p7", slug=f"p7-{uuid4_hex()}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        empty_registry = RunnerRegistry()
        monkeypatch.setattr(container_service, "runner_registry", empty_registry)

        with pytest.raises(Exception) as exc_info:
            await container_service.schedule_and_start(
                db_session,
                project_id=project.project_id,
                task_id=None,
                owner_user_id=registered_user["user_id"],
                env={}, repos=[],
            )
        assert getattr(exc_info.value, "code", None) == 8003
