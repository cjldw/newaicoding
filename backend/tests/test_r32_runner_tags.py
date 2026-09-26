"""
R32 Runner 标签管理与全字段编辑 - TDD Red 测试
=============================================
覆盖完成判据 1-7、9(判据 8 是前端 tsc/ui-check,不归后端 QA)
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.response import BizError
from app.models.runner import Runner
from app.services import runner_service


async def _make_runner(db_session, name=None, role="worker", status="online", tags=None, max_containers=10):
    """辅助:直接插库(绕过 create_runner 的 name 唯一校验,便于 seed 矩阵)"""
    runner = Runner(
        runner_id=str(uuid.uuid4()),
        name=name or f"runner-{uuid.uuid4().hex[:6]}",
        role=role,
        token_hash="x",
        status=status,
        max_containers=max_containers,
        current_containers=0,
        tags=tags,
        created_by="test",  # NOT NULL 列(R31 既有测试同惯例)
    )
    db_session.add(runner)
    await db_session.flush()
    return runner


class _AnyUser:
    """task_service operator 占位(照抄 test_r8f4_custom_env_vars 惯例)"""
    user_id = "u-test"
    role = "user"
    gitlab_username = "tester"
    nickname = "测试"


# ---------------------------------------------------------------------------
# 判据 1:调度匹配矩阵
# ---------------------------------------------------------------------------
class TestSchedulingMatchMatrix:
    @pytest.mark.asyncio
    async def test_pick_runner_dev_excludes_test_and_empty(self, db_session):
        """seed A[dev]/B[]/C[test] → pick(task_tag="dev") 永不返 C"""
        a = await _make_runner(db_session, tags=["dev"])
        b = await _make_runner(db_session, tags=[])
        c = await _make_runner(db_session, tags=["test"])

        # 多次采样确保稳定性
        for _ in range(10):
            picked = await runner_service.pick_runner_db(db_session, "worker", task_tag="dev")
            assert picked is not None
            assert picked.runner_id in (a.runner_id, b.runner_id)
            assert picked.runner_id != c.runner_id

    @pytest.mark.asyncio
    async def test_pick_runner_offline_returns_none(self, db_session):
        """A 离线 → 返 None"""
        await _make_runner(db_session, tags=["dev"], status="offline")
        picked = await runner_service.pick_runner_db(db_session, "worker", task_tag="dev")
        assert picked is None

    @pytest.mark.asyncio
    async def test_pick_runner_task_tag_none_unchanged(self, db_session):
        """task_tag=None(deploy/兜底)行为不变"""
        a = await _make_runner(db_session, tags=["dev"])
        b = await _make_runner(db_session, tags=[])

        # task_tag=None 时,所有 worker 都 eligible(兜底)
        for _ in range(10):
            picked = await runner_service.pick_runner_db(db_session, "worker", task_tag=None)
            assert picked is not None
            assert picked.runner_id in (a.runner_id, b.runner_id)


# ---------------------------------------------------------------------------
# 判据 2:调用点透传
# ---------------------------------------------------------------------------
class TestCallSitePassthrough:
    @pytest.mark.asyncio
    async def test_create_polish_task_passes_requirement_tag(self, db_session, registered_user):
        """create_polish_task → task_tag="requirement" """
        from app.models.project import Project
        from app.models.requirement import Requirement
        from app.services import task_service, container_service

        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        req = Requirement(
            req_id=str(uuid.uuid4()),
            project_id=project.project_id,
            title="r",
            description="d",
            req_branch="main",  # NOT NULL 列
            created_by=registered_user["user_id"],
        )
        db_session.add(req)
        await db_session.flush()

        # 打桩:LLM 配置(测试库无模型配置,resolve_config 会业务报错挡在调度前)+ 调度捕获
        llm_stub = AsyncMock(return_value={"base_url": "http://llm.test", "model": "test-model",
                                           "api_key": "k", "source": "project"})
        with patch("app.services.llm_service.resolve_config", llm_stub), \
             patch.object(container_service, "schedule_and_start", new_callable=AsyncMock) as mock_sched:
            await task_service.create_polish_task(db_session, project, req, _AnyUser())
            mock_sched.assert_called_once()
            call_kwargs = mock_sched.call_args.kwargs
            assert call_kwargs.get("task_tag") == "requirement"

    @pytest.mark.asyncio
    async def test_start_task_passes_dev_tag(self, db_session, registered_user):
        """start_task dev → task_tag="dev" """
        from app.models.project import Project
        from app.models.requirement import Requirement
        from app.models.task import Task
        from app.services import task_service, container_service

        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        # start_task 第 4 参是 requirement(env 需要 REQ_ID),落真行
        req = Requirement(
            req_id=str(uuid.uuid4()),
            project_id=project.project_id,
            title="r",
            description="d",
            req_branch="main",
            created_by=registered_user["user_id"],
        )
        db_session.add(req)
        await db_session.flush()

        task = Task(
            req_id=req.req_id,
            project_id=project.project_id,
            type="dev",
            title="t",
            description="d",
            base_branch="main",
            work_branch="main",
            status="pending",
            created_by=registered_user["user_id"],
        )
        db_session.add(task)
        await db_session.flush()

        # 打桩:LLM 配置(测试库无模型配置,resolve_config 会业务报错挡在调度前)+ 调度捕获
        llm_stub = AsyncMock(return_value={"base_url": "http://llm.test", "model": "test-model",
                                           "api_key": "k", "source": "project"})
        with patch("app.services.llm_service.resolve_config", llm_stub), \
             patch.object(container_service, "schedule_and_start", new_callable=AsyncMock) as mock_sched:
            await task_service.start_task(db_session, task, project, req)
            mock_sched.assert_called_once()
            call_kwargs = mock_sched.call_args.kwargs
            assert call_kwargs.get("task_tag") == "dev"

    @pytest.mark.asyncio
    async def test_start_task_release_passes_none_tag(self, db_session, registered_user):
        """start_task release → task_tag=None"""
        from app.models.project import Project
        from app.models.requirement import Requirement
        from app.models.task import Task
        from app.services import task_service, container_service

        project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:8]}", owner_id=registered_user["user_id"])
        db_session.add(project)
        await db_session.flush()

        req = Requirement(
            req_id=str(uuid.uuid4()),
            project_id=project.project_id,
            title="r",
            description="d",
            req_branch="main",
            created_by=registered_user["user_id"],
        )
        db_session.add(req)
        await db_session.flush()

        task = Task(
            req_id=req.req_id,
            project_id=project.project_id,
            type="release",
            title="t",
            description="d",
            base_branch="main",
            work_branch="main",
            status="pending",
            created_by=registered_user["user_id"],
        )
        db_session.add(task)
        await db_session.flush()

        # 打桩:LLM 配置(测试库无模型配置,resolve_config 会业务报错挡在调度前)+ 调度捕获
        llm_stub = AsyncMock(return_value={"base_url": "http://llm.test", "model": "test-model",
                                           "api_key": "k", "source": "project"})
        with patch("app.services.llm_service.resolve_config", llm_stub), \
             patch.object(container_service, "schedule_and_start", new_callable=AsyncMock) as mock_sched:
            await task_service.start_task(db_session, task, project, req)
            mock_sched.assert_called_once()
            call_kwargs = mock_sched.call_args.kwargs
            assert call_kwargs.get("task_tag") is None


# ---------------------------------------------------------------------------
# 判据 3:创建带 tags
# ---------------------------------------------------------------------------
class TestCreateWithTags:
    @pytest.mark.asyncio
    async def test_create_remote_with_tags(self, client, superadmin_headers, db_session):
        """远程 POST /api/admin/runners + tags 落库"""
        resp = await client.post(
            "/api/admin/runners",
            headers=superadmin_headers,
            json={
                "name": f"r-{uuid.uuid4().hex[:4]}",
                "role": "worker",
                "max_containers": 10,
                "tags": ["dev", "test"],
            },
        )
        data = resp.json()
        assert data["code"] == 0, data
        runner_id = data["data"]["runner_id"]

        result = await db_session.execute(select(Runner).where(Runner.runner_id == runner_id))
        runner = result.scalar_one()
        assert set(runner.tags or []) == {"dev", "test"}

    @pytest.mark.asyncio
    async def test_create_local_with_tags(self, client, superadmin_headers, db_session):
        """本机 POST /api/admin/runners/local + tags 落库"""
        with patch("app.services.local_runner_service.preflight", new_callable=AsyncMock), \
             patch("app.services.local_runner_service.spawn_local", new_callable=AsyncMock) as mock_spawn, \
             patch("app.services.local_runner_service.wait_online", new_callable=AsyncMock, return_value="online"):
            mock_spawn.return_value = {"env_keys": []}
            resp = await client.post(
                "/api/admin/runners/local",
                headers=superadmin_headers,
                json={"name": f"local-{uuid.uuid4().hex[:4]}", "max_containers": 5, "tags": ["requirement"]},
            )
        data = resp.json()
        assert data["code"] == 0, data
        runner_id = data["data"]["runner_id"]

        result = await db_session.execute(select(Runner).where(Runner.runner_id == runner_id))
        runner = result.scalar_one()
        assert set(runner.tags or []) == {"requirement"}

    @pytest.mark.asyncio
    async def test_create_with_illegal_tags_16008(self, client, superadmin_headers, db_session):
        """非法 tags 值 → 16008"""
        resp = await client.post(
            "/api/admin/runners",
            headers=superadmin_headers,
            json={"name": f"r-{uuid.uuid4().hex[:4]}", "role": "worker", "tags": ["gpu", "dev"]},
        )
        assert resp.json()["code"] == 16008

    @pytest.mark.asyncio
    async def test_create_deploy_with_nonempty_tags_16008(self, client, superadmin_headers, db_session):
        """deploy + 非空 tags → 16008"""
        resp = await client.post(
            "/api/admin/runners",
            headers=superadmin_headers,
            json={
                "name": f"deploy-{uuid.uuid4().hex[:4]}",
                "role": "deploy",
                "public_ip": "1.2.3.4",
                "tags": ["dev"],
            },
        )
        assert resp.json()["code"] == 16008


# ---------------------------------------------------------------------------
# 判据 4:PATCH 编辑族
# ---------------------------------------------------------------------------
class TestPatchEditFamily:
    @pytest.mark.asyncio
    async def test_patch_change_tags(self, client, superadmin_headers, db_session):
        """PATCH 改 tags"""
        runner = await _make_runner(db_session, tags=["dev"])
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"tags": ["test", "requirement"]},
        )
        data = resp.json()
        assert data["code"] == 0, data
        await db_session.refresh(runner)
        assert set(runner.tags or []) == {"test", "requirement"}

    @pytest.mark.asyncio
    async def test_patch_change_name(self, client, superadmin_headers, db_session):
        """PATCH 改名称"""
        runner = await _make_runner(db_session)
        new_name = f"new-{uuid.uuid4().hex[:4]}"
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"name": new_name},
        )
        assert resp.json()["code"] == 0, resp.text
        await db_session.refresh(runner)
        assert runner.name == new_name

    @pytest.mark.asyncio
    async def test_patch_change_max_containers(self, client, superadmin_headers, db_session):
        """PATCH 改最大容器数"""
        runner = await _make_runner(db_session, max_containers=10)
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"max_containers": 20},
        )
        assert resp.json()["code"] == 0, resp.text
        await db_session.refresh(runner)
        assert runner.max_containers == 20

    @pytest.mark.asyncio
    async def test_patch_name_conflict_16005(self, client, superadmin_headers, db_session):
        """名称冲突 → 16005"""
        r1 = await _make_runner(db_session, name=f"r1-{uuid.uuid4().hex[:4]}")
        r2 = await _make_runner(db_session, name=f"r2-{uuid.uuid4().hex[:4]}")
        resp = await client.patch(
            f"/api/admin/runners/{r2.runner_id}",
            headers=superadmin_headers,
            json={"name": r1.name},
        )
        assert resp.json()["code"] == 16005

    @pytest.mark.asyncio
    async def test_patch_name_unchanged_skip_dedup(self, client, superadmin_headers, db_session):
        """名称未变 → 跳过唯一校验(自撞防护)"""
        runner = await _make_runner(db_session, name=f"same-{uuid.uuid4().hex[:4]}")
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"name": runner.name},  # 同名
        )
        assert resp.json()["code"] == 0, resp.text

    @pytest.mark.asyncio
    async def test_patch_disabled_editable(self, client, superadmin_headers, db_session):
        """disabled runner 允许编辑"""
        runner = await _make_runner(db_session, status="disabled")
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"tags": ["dev"]},
        )
        assert resp.json()["code"] == 0, resp.text
        await db_session.refresh(runner)
        assert set(runner.tags or []) == {"dev"}

    @pytest.mark.asyncio
    async def test_patch_not_found_404(self, client, superadmin_headers, db_session):
        """runner 不存在 → 404"""
        resp = await client.patch(
            f"/api/admin/runners/{str(uuid.uuid4())}",
            headers=superadmin_headers,
            json={"tags": ["dev"]},
        )
        assert resp.status_code == 404 or resp.json()["code"] == 404


# ---------------------------------------------------------------------------
# 判据 5:列表 tags
# ---------------------------------------------------------------------------
class TestListTags:
    @pytest.mark.asyncio
    async def test_list_items_contain_tags(self, client, superadmin_headers, db_session):
        """items 含 tags 数组"""
        await _make_runner(db_session, tags=["dev", "test"])
        resp = await client.get("/api/admin/runners", headers=superadmin_headers)
        data = resp.json()
        assert data["code"] == 0
        items = data["data"]["items"]
        assert len(items) >= 1
        for item in items:
            assert "tags" in item
            assert isinstance(item["tags"], list)

    @pytest.mark.asyncio
    async def test_list_null_tags_as_empty_array(self, client, superadmin_headers, db_session):
        """NULL 存量 → []"""
        runner = await _make_runner(db_session, tags=None)
        resp = await client.get("/api/admin/runners", headers=superadmin_headers)
        data = resp.json()
        items = data["data"]["items"]
        target = [i for i in items if i["runner_id"] == runner.runner_id][0]
        assert target["tags"] == []


# ---------------------------------------------------------------------------
# 判据 6:8003 回归
# ---------------------------------------------------------------------------
class TestNoMatchRegression:
    @pytest.mark.asyncio
    async def test_no_dev_match_returns_none(self, db_session):
        """无 dev 匹配 → pick None → 既有 8003"""
        await _make_runner(db_session, tags=["test"])  # 只有 test 专属
        picked = await runner_service.pick_runner_db(db_session, "worker", task_tag="dev")
        assert picked is None


# ---------------------------------------------------------------------------
# 判据 9:审计 runner.update
# ---------------------------------------------------------------------------
class TestAuditRunnerUpdate:
    @pytest.mark.asyncio
    async def test_patch_audit_contains_before_after_tags(self, client, superadmin_headers, db_session):
        """runner.update 审计 detail 含 before_tags/after_tags"""
        from app.models.audit_log import AuditLog

        runner = await _make_runner(db_session, tags=["dev"])
        resp = await client.patch(
            f"/api/admin/runners/{runner.runner_id}",
            headers=superadmin_headers,
            json={"tags": ["test"]},
        )
        assert resp.json()["code"] == 0, resp.text

        result = await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action_type == "runner.update")
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        audit = result.scalar_one_or_none()
        assert audit is not None
        detail = audit.detail or {}
        assert "before_tags" in detail
        assert "after_tags" in detail
        assert set(detail["before_tags"]) == {"dev"}
        assert set(detail["after_tags"]) == {"test"}
