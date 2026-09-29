"""
R8 容器平台侧测试(调度/配额/回报处理;R16 起调度为 DB 注册表)
==========================
Runner 程序本体测试见 runner/tests/(独立目录,不依赖 docker SDK)。
"""
import uuid

import pytest

from app.models.container import Container
from app.models.project import Project, PlatformSetting
from app.models.runner import Runner
from app.services import container_service, runner_service
from app.services.runner_service import runner_registry


async def _insert_container(db_session, project_id, runner_id="r-1", status="running",
                            container_id=None, task_id=None):
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


async def _insert_runner(db_session, name="runner-a", role="worker", status="online",
                         current=0, maximum=10):
    """直插 Runner 行(调度用;token_hash 填占位)"""
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


# ---------------------------------------------------------------------------
# 调度器(DB 注册表,R16)
# ---------------------------------------------------------------------------
class TestScheduler:
    @pytest.mark.asyncio
    async def test_schedule_runner_least_loaded(self, db_session):
        """调度器选最少负载 Runner"""
        await _insert_runner(db_session, "r1", current=3)
        r2 = await _insert_runner(db_session, "r2", current=1)
        await _insert_runner(db_session, "r3", current=2)

        picked = await runner_service.pick_runner_db(db_session, "worker")
        assert picked is not None and picked.runner_id == r2.runner_id

    @pytest.mark.asyncio
    async def test_schedule_runner_deploy_role(self, db_session):
        """部署任务只选 deploy Runner;普通任务不占用 deploy Runner"""
        deploy = await _insert_runner(db_session, "deploy-1", role="deploy", current=5)
        worker = await _insert_runner(db_session, "worker-1", current=0)

        picked_deploy = await runner_service.pick_runner_db(db_session, "deploy")
        assert picked_deploy.runner_id == deploy.runner_id
        picked_worker = await runner_service.pick_runner_db(db_session, "worker")
        assert picked_worker.runner_id == worker.runner_id

    @pytest.mark.asyncio
    async def test_no_runner_available(self, db_session):
        """无在线/匹配 Runner 返回 None(服务层转 8003)"""
        assert await runner_service.pick_runner_db(db_session, "deploy") is None
        await _insert_runner(db_session, "off", status="offline")
        await _insert_runner(db_session, "dis", status="disabled")
        assert await runner_service.pick_runner_db(db_session, "worker") is None

    @pytest.mark.asyncio
    async def test_full_runner_not_scheduled(self, db_session):
        """current_containers >= max_containers 的 Runner 不参与调度"""
        await _insert_runner(db_session, "full", current=10, maximum=10)
        assert await runner_service.pick_runner_db(db_session, "worker") is None


# ---------------------------------------------------------------------------
# 配额
# ---------------------------------------------------------------------------
class TestQuotas:
    @pytest.mark.asyncio
    async def test_user_container_limit(self, client, auth_headers, db_session, registered_user):
        """单用户同时运行容器 >5:8001"""
        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
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
        db_session.add(PlatformSetting(key="max_containers_total", value=1, updated_by="t"))
        project = Project(name="p2", slug=f"p2-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        await _insert_container(db_session, project.project_id, status="running")

        other_user_id = f"00000000-0000-0000-0000-{uuid.uuid4().hex}"
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
        project = Project(name="p3", slug=f"p3-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
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
        project = Project(name="p4", slug=f"p4-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
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
        """container_stopped 回报后:destroyed + destroyed_at;Runner 占用 -1"""
        project = Project(name="p5", slug=f"p5-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        runner = await _insert_runner(db_session, "r-1", current=1)
        await _insert_container(db_session, project.project_id, status="running",
                                container_id="docker-stop-1", runner_id=runner.runner_id)

        await container_service.handle_container_stopped(db_session, "docker-stop-1")
        await db_session.refresh(runner)
        result = await db_session.execute(
            Container.__table__.select().where(Container.container_id == "docker-stop-1")
        )
        row = result.mappings().first()
        assert row["status"] == "destroyed"
        assert row["destroyed_at"] is not None
        assert runner.current_containers == 0


# ---------------------------------------------------------------------------
# 调度 + 下发(schedule_and_start)
# ---------------------------------------------------------------------------
class TestScheduleAndStart:
    @pytest.mark.asyncio
    async def test_schedule_and_start_sends_message(self, client, auth_headers, db_session,
                                                    registered_user, monkeypatch):
        """正常路径:DB 在线 Runner + 内存连接 → 登记 creating 并下发消息"""
        runner = await _insert_runner(db_session, "runner-x", current=0)

        conn = runner_registry.register(runner.runner_id, "worker", None, "10.0.0.1")

        sent = []

        async def fake_send(c, message):
            sent.append(message)

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        project = Project(name="p6", slug=f"p6-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        container = await container_service.schedule_and_start(
            db_session,
            project_id=project.project_id,
            task_id="task-xyz",
            owner_user_id=registered_user["user_id"],
            env={"GITLAB_TOKEN": "x"},
            repos=[{"url": "https://gitlab.example.com/g/r.git", "path": "/workspace/r", "branch": "req-1"}],
        )
        assert container.status == "creating"
        assert container.runner_id == runner.runner_id
        assert len(sent) == 1
        msg = sent[0]
        assert msg["type"] == "start_container"
        assert msg["task_id"] == "task-xyz"
        # R1→R5(container_image):默认镜像钉住生产常量 aliyun 地址;下发消息与 DB 登记行同源
        assert msg["image"] == "registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2", \
            f"下发镜像应为 aliyun 默认,实际: {msg['image']}"
        assert container.image == "registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2", \
            f"登记镜像应为 aliyun 默认,实际: {container.image}"
        assert msg["ports"] == [5173, 8000]
        assert msg["repos"][0]["branch"] == "req-1"
        await db_session.refresh(runner)
        assert runner.current_containers == 1
        runner_registry.unregister(runner.runner_id)

    @pytest.mark.asyncio
    async def test_no_runner_returns_8003(self, client, auth_headers, db_session, registered_user):
        """无可用 Runner:8003(DB 空 + 无连接)"""
        project = Project(name="p7", slug=f"p7-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        with pytest.raises(Exception) as exc_info:
            await container_service.schedule_and_start(
                db_session,
                project_id=project.project_id,
                task_id=None,
                owner_user_id=registered_user["user_id"],
                env={}, repos=[],
            )
        assert getattr(exc_info.value, "code", None) == 8003


# ---------------------------------------------------------------------------
# 镜像解析链(R5 container_image:显式传参 > 后台设置 > DEFAULT_IMAGE 常量)
# ---------------------------------------------------------------------------
class TestImageResolution:
    @pytest.mark.asyncio
    async def test_setting_overrides_default_image(self, db_session, registered_user, monkeypatch):
        """后台配置 container_image 后,不传 image 的调度应改用设置值"""
        from app.services import platform_settings_service

        runner = await _insert_runner(db_session, "runner-img-set", current=0)
        runner_registry.register(runner.runner_id, "worker", None, "10.0.0.2")

        sent = []

        async def fake_send(c, message):
            sent.append(message)

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        project = Project(name="p-img-set", slug=f"pis-{uuid.uuid4().hex[:8]}",
                          owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        await platform_settings_service.update_settings(
            db_session, "test", {"container_image": "reg.example.com/ns/repo:v9"}
        )

        container = await container_service.schedule_and_start(
            db_session,
            project_id=project.project_id,
            task_id="task-img-set",
            owner_user_id=registered_user["user_id"],
            env={}, repos=[],
        )
        assert sent[0]["image"] == "reg.example.com/ns/repo:v9", sent[0]
        assert container.image == "reg.example.com/ns/repo:v9", container.image
        runner_registry.unregister(runner.runner_id)

    @pytest.mark.asyncio
    async def test_explicit_param_wins_over_setting(self, db_session, registered_user, monkeypatch):
        """显式传参优先级最高:设置项已配置时,传参值仍胜出"""
        from app.services import platform_settings_service

        runner = await _insert_runner(db_session, "runner-img-exp", current=0)
        runner_registry.register(runner.runner_id, "worker", None, "10.0.0.3")

        sent = []

        async def fake_send(c, message):
            sent.append(message)

        monkeypatch.setattr(runner_service, "send_to_runner", fake_send)

        project = Project(name="p-img-exp", slug=f"pie-{uuid.uuid4().hex[:8]}",
                          owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()
        await platform_settings_service.update_settings(
            db_session, "test", {"container_image": "reg.example.com/ns/repo:v9"}
        )

        container = await container_service.schedule_and_start(
            db_session,
            project_id=project.project_id,
            task_id="task-img-exp",
            owner_user_id=registered_user["user_id"],
            env={}, repos=[],
            image="explicit/custom:v1",
        )
        assert sent[0]["image"] == "explicit/custom:v1", sent[0]
        assert container.image == "explicit/custom:v1", container.image
        runner_registry.unregister(runner.runner_id)
