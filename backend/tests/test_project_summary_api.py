"""
R1 项目聚合统计接口测试 — TDD Red Phase
=========================================
GET /api/projects/{project_id}/summary

覆盖完成判据 9 条:
1. 鉴权矩阵(登录成员 200/未登录 401/非成员访问 private 项目 404)
2. 四维 by_status 零填充对账
3. active+polish_tasks 口径
4. tokens 聚合(total=in+out/by_type/全 null 全 0)
5. recent_7d 四计数(7 天内外边界)
6. latest_release 三态(deployed 有 preview_url/无 release 为 null/非 deployed preview_url 空串)
7. recent Top5 恰 5 条 updated_at 倒序白名单字段
8. 空项目全零不 500
9. 响应最小化(无 PII/token/extended_attributes 原文)
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task

# 状态全集(与 dashboard.py 保持一致,零填充依据)
REQ_STATUSES = ("draft", "polishing", "reviewing", "approved", "in_progress", "done", "archived", "rejected")
TASK_STATUSES = ("pending", "running", "cases_review", "passed", "failed", "done", "cancelled", "timeout")


# ---------------------------------------------------------------------------
# Local fixture: 非首个注册用户(避免 bootstrap superadmin 陷阱)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def non_bootstrap_second_user_headers(client, registered_user):
    """第二用户(非首个注册,避免 bootstrap superadmin)"""
    phone = f"137{str(uuid.uuid4().int)[:8]}"
    password = "Test1234"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": password})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200
    access_token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _create_project(db_session, owner_id, visibility="private", name=None):
    """创建项目并返回"""
    slug = f"proj-{uuid.uuid4().hex[:8]}"
    project = Project(
        name=name or f"test-{slug}",
        slug=slug,
        owner_id=owner_id,
        visibility=visibility,
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    return project


async def _add_member(db_session, project_id, user_id, role="viewer"):
    """添加项目成员"""
    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
        invited_by=project_id,  # 简化
    )
    db_session.add(member)
    await db_session.flush()
    return member


async def _create_requirement(db_session, project_id, created_by, status="draft",
                               title=None, updated_at=None, created_at=None):
    """创建需求"""
    req = Requirement(
        req_id=str(uuid.uuid4()),
        project_id=project_id,
        title=title or f"req-{uuid.uuid4().hex[:6]}",
        description="test desc",
        status=status,
        created_by=created_by,
    )
    if updated_at is not None:
        req.updated_at = updated_at
    if created_at is not None:
        req.created_at = created_at
    else:
        # 显式设置 created_at,替代模型 before_insert event
        if updated_at is not None:
            req.created_at = updated_at - timedelta(days=30)
        else:
            req.created_at = datetime.now()
    db_session.add(req)
    await db_session.flush()
    return req


async def _create_task(db_session, project_id, created_by, task_type="dev",
                        status="pending", title=None, tokens_in=None, tokens_out=None,
                        updated_at=None, created_at=None, finished_at=None,
                        extended_attributes=None, work_branch=None):
    """创建任务"""
    task = Task(
        task_id=str(uuid.uuid4()),
        req_id=str(uuid.uuid4()),  # 简化:不关联真实需求
        project_id=project_id,
        type=task_type,
        title=title or f"task-{uuid.uuid4().hex[:6]}",
        description="test task",
        base_branch="main",
        work_branch=work_branch or f"feat-{uuid.uuid4().hex[:6]}",
        status=status,
        created_by=created_by,
        total_tokens_in=tokens_in,
        total_tokens_out=tokens_out,
        extended_attributes=extended_attributes,
    )
    if updated_at is not None:
        task.updated_at = updated_at
    if created_at is not None:
        task.created_at = created_at
    else:
        # 显式设置 created_at,替代模型 before_insert event
        if finished_at is not None:
            task.created_at = finished_at - timedelta(days=30)
        else:
            task.created_at = datetime.now()
    if finished_at is not None:
        task.finished_at = finished_at
    db_session.add(task)
    await db_session.flush()
    return task


# ---------------------------------------------------------------------------
# 判据 1: 鉴权矩阵
# ---------------------------------------------------------------------------
class TestAuthMatrix:
    """判据 1: 登录成员 200 / 未登录 401 / 非成员访问 private 项目 404"""

    @pytest.mark.asyncio
    async def test_member_get_summary_200(self, client, auth_headers, db_session, registered_user):
        """登录成员(项目 owner)访问 summary 返回 200"""
        project = await _create_project(db_session, registered_user["user_id"])

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "data" in data

    @pytest.mark.asyncio
    async def test_unauthenticated_401(self, client, db_session, registered_user):
        """未登录访问 summary 返回 401"""
        project = await _create_project(db_session, registered_user["user_id"])

        resp = await client.get(f"/api/projects/{project.project_id}/summary")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_member_private_project_404(
        self, client, non_bootstrap_second_user_headers, db_session, registered_user
    ):
        """非成员访问 private 项目返回 404(防枚举)"""
        project = await _create_project(db_session, registered_user["user_id"], visibility="private")

        resp = await client.get(
            f"/api/projects/{project.project_id}/summary",
            headers=non_bootstrap_second_user_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 判据 2: 四维 by_status 零填充对账
# ---------------------------------------------------------------------------
class TestByStatusZeroFill:
    """判据 2: 四维 by_status 零填充聚合"""

    @pytest.mark.asyncio
    async def test_requirements_by_status_zero_filled(
        self, client, auth_headers, db_session, registered_user
    ):
        """需求 by_status 8 态零填充:造 3 条不同状态需求,响应包含全部 8 态"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造 3 条需求:draft / polishing / done
        await _create_requirement(db_session, project.project_id, uid, status="draft")
        await _create_requirement(db_session, project.project_id, uid, status="polishing")
        await _create_requirement(db_session, project.project_id, uid, status="done")

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        req_by_status = data["requirements"]["by_status"]
        # 8 态全部存在
        for s in REQ_STATUSES:
            assert s in req_by_status, f"缺少状态 {s}"
        # 计数正确
        assert req_by_status["draft"] == 1
        assert req_by_status["polishing"] == 1
        assert req_by_status["done"] == 1
        # 未出现的状态为 0
        assert req_by_status["reviewing"] == 0
        assert req_by_status["archived"] == 0

    @pytest.mark.asyncio
    async def test_tasks_by_status_zero_filled(
        self, client, auth_headers, db_session, registered_user
    ):
        """任务 by_status 8 态零填充:dev/test/release 三维度各自独立"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造 dev 任务:pending / running
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="pending")
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="running")
        # 造 test 任务:passed
        await _create_task(db_session, project.project_id, uid, task_type="test", status="passed")
        # 造 release 任务:done
        await _create_task(db_session, project.project_id, uid, task_type="release", status="done")

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # dev_tasks
        dev_by_status = data["dev_tasks"]["by_status"]
        for s in TASK_STATUSES:
            assert s in dev_by_status, f"dev_tasks 缺少状态 {s}"
        assert dev_by_status["pending"] == 1
        assert dev_by_status["running"] == 1
        assert dev_by_status["passed"] == 0

        # test_tasks
        test_by_status = data["test_tasks"]["by_status"]
        for s in TASK_STATUSES:
            assert s in test_by_status, f"test_tasks 缺少状态 {s}"
        assert test_by_status["passed"] == 1

        # release_tasks
        release_by_status = data["release_tasks"]["by_status"]
        for s in TASK_STATUSES:
            assert s in release_by_status, f"release_tasks 缺少状态 {s}"
        assert release_by_status["done"] == 1


# ---------------------------------------------------------------------------
# 判据 3: active+polish_tasks 口径
# ---------------------------------------------------------------------------
class TestActiveAndPolishTasks:
    """判据 3: active/polish_tasks 口径"""

    @pytest.mark.asyncio
    async def test_requirements_active_and_polish_tasks(
        self, client, auth_headers, db_session, registered_user
    ):
        """requirements.active = polishing+reviewing; polish_tasks = type=requirement 任务数"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造需求:polishing + reviewing(应计入 active) + draft(不计入)
        await _create_requirement(db_session, project.project_id, uid, status="polishing")
        await _create_requirement(db_session, project.project_id, uid, status="reviewing")
        await _create_requirement(db_session, project.project_id, uid, status="draft")

        # 造 type=requirement 任务(polish_tasks 计数)
        await _create_task(db_session, project.project_id, uid, task_type="requirement", status="running")
        await _create_task(db_session, project.project_id, uid, task_type="requirement", status="pending")
        # 造 type=dev 任务(不计入 polish_tasks)
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="running")

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # requirements.active = polishing(1) + reviewing(1) = 2
        assert data["requirements"]["active"] == 2
        # polish_tasks = type=requirement 的任务数 = 2
        assert data["requirements"]["polish_tasks"] == 2

    @pytest.mark.asyncio
    async def test_tasks_active_definition(
        self, client, auth_headers, db_session, registered_user
    ):
        """tasks.active = pending+running+cases_review"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # dev 任务:pending(计入) + running(计入) + cases_review(计入) + passed(不计入)
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="pending")
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="running")
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="cases_review")
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="passed")

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # dev_tasks.active = pending(1) + running(1) + cases_review(1) = 3
        assert data["dev_tasks"]["active"] == 3


# ---------------------------------------------------------------------------
# 判据 4: tokens 聚合
# ---------------------------------------------------------------------------
class TestTokensAggregation:
    """判据 4: tokens 聚合(total=in+out/by_type/全 null 全 0)"""

    @pytest.mark.asyncio
    async def test_tokens_total_and_by_type(
        self, client, auth_headers, db_session, registered_user
    ):
        """tokens.total = in+out; by_type 按任务类型分组"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # dev 任务:in=100, out=50
        await _create_task(db_session, project.project_id, uid, task_type="dev",
                           status="done", tokens_in=100, tokens_out=50)
        # test 任务:in=200, out=80
        await _create_task(db_session, project.project_id, uid, task_type="test",
                           status="done", tokens_in=200, tokens_out=80)
        # release 任务:in=50, out=20
        await _create_task(db_session, project.project_id, uid, task_type="release",
                           status="done", tokens_in=50, tokens_out=20)
        # requirement 任务:in=30, out=10
        await _create_task(db_session, project.project_id, uid, task_type="requirement",
                           status="done", tokens_in=30, tokens_out=10)

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        tokens = data["tokens"]
        # total = sum(in) + sum(out) = (100+200+50+30) + (50+80+20+10) = 380 + 160 = 540
        assert tokens["total"] == 540
        assert tokens["in"] == 380
        assert tokens["out"] == 160
        # by_type
        assert tokens["by_type"]["dev"] == 150  # 100+50
        assert tokens["by_type"]["test"] == 280  # 200+80
        assert tokens["by_type"]["release"] == 70  # 50+20
        assert tokens["by_type"]["requirement"] == 40  # 30+10

    @pytest.mark.asyncio
    async def test_tokens_all_null_coalesce_zero(
        self, client, auth_headers, db_session, registered_user
    ):
        """全 null tokens 项目:tokens 全 0"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造任务 tokens 为 null(模型默认 0,但显式设 None)
        await _create_task(db_session, project.project_id, uid, task_type="dev",
                           status="done", tokens_in=None, tokens_out=None)

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        tokens = data["tokens"]
        assert tokens["total"] == 0
        assert tokens["in"] == 0
        assert tokens["out"] == 0


# ---------------------------------------------------------------------------
# 判据 5: recent_7d 四计数
# ---------------------------------------------------------------------------
class TestRecent7d:
    """判据 5: recent_7d 四计数(7 天内外边界)"""

    @pytest.mark.asyncio
    async def test_recent_7d_boundary(
        self, client, auth_headers, db_session, registered_user
    ):
        """7 天内/外数据边界:窗口外不计入"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]
        now = datetime.now()

        # 需求:7 天内创建(计入) + 7 天外创建(不计入)
        await _create_requirement(
            db_session, project.project_id, uid, status="draft",
            created_at=now - timedelta(days=3),
        )
        await _create_requirement(
            db_session, project.project_id, uid, status="draft",
            created_at=now - timedelta(days=10),
        )

        # 需求完成:status=done 且 updated_at 在 7 天内
        await _create_requirement(
            db_session, project.project_id, uid, status="done",
            updated_at=now - timedelta(days=2),
        )
        # 需求完成但 updated_at 在 7 天外(不计入)
        await _create_requirement(
            db_session, project.project_id, uid, status="done",
            updated_at=now - timedelta(days=15),
        )

        # 任务:7 天内创建(计入)
        await _create_task(
            db_session, project.project_id, uid, task_type="dev", status="running",
            created_at=now - timedelta(days=5),
        )
        # 任务:7 天外创建(不计入)
        await _create_task(
            db_session, project.project_id, uid, task_type="dev", status="running",
            created_at=now - timedelta(days=20),
        )

        # 任务完成:status=done 且 finished_at 在 7 天内
        await _create_task(
            db_session, project.project_id, uid, task_type="dev", status="done",
            finished_at=now - timedelta(days=1),
        )
        # 任务完成但 finished_at 在 7 天外(不计入)
        await _create_task(
            db_session, project.project_id, uid, task_type="dev", status="done",
            finished_at=now - timedelta(days=30),
        )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        r7d = data["recent_7d"]
        # requirements_created: 7 天内 1 条
        assert r7d["requirements_created"] == 1
        # requirements_completed: status=done 且 updated_at 在 7 天内 1 条
        assert r7d["requirements_completed"] == 1
        # tasks_created: 7 天内 1 条
        assert r7d["tasks_created"] == 1
        # tasks_completed: status=done 且 finished_at 在 7 天内 1 条
        assert r7d["tasks_completed"] == 1


# ---------------------------------------------------------------------------
# 判据 6: latest_release 三态
# ---------------------------------------------------------------------------
class TestLatestRelease:
    """判据 6: latest_release 三态"""

    @pytest.mark.asyncio
    async def test_latest_release_deployed_with_preview_url(
        self, client, auth_headers, db_session, registered_user
    ):
        """有 deployed release 任务:返回 branch/preview_url/finished_at"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造 release 任务,deploy_phase=deployed,带 deploy_host/deploy_port
        await _create_task(
            db_session, project.project_id, uid, task_type="release", status="done",
            work_branch="main",
            extended_attributes={
                "deploy_phase": "deployed",
                "deploy_host": "10.0.0.1",
                "deploy_port": 3000,
            },
            finished_at=datetime.now(),
        )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        lr = data["latest_release"]
        assert lr is not None
        assert lr["branch"] == "main"
        assert lr["status"] == "done"
        assert "preview_url" in lr
        assert lr["preview_url"] != ""
        assert "finished_at" in lr

    @pytest.mark.asyncio
    async def test_latest_release_no_release_null(
        self, client, auth_headers, db_session, registered_user
    ):
        """无 release 任务:latest_release 为 null"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 只造 dev 任务,无 release
        await _create_task(db_session, project.project_id, uid, task_type="dev", status="done")

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["latest_release"] is None

    @pytest.mark.asyncio
    async def test_latest_release_non_deployed_empty_preview_url(
        self, client, auth_headers, db_session, registered_user
    ):
        """release 任务 deploy_phase != deployed:preview_url 为空串"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造 release 任务,deploy_phase=building(非 deployed)
        await _create_task(
            db_session, project.project_id, uid, task_type="release", status="running",
            work_branch="main",
            extended_attributes={
                "deploy_phase": "building",
                "deploy_host": "10.0.0.1",
                "deploy_port": 3000,
            },
        )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        lr = data["latest_release"]
        assert lr is not None
        assert lr["preview_url"] == ""


# ---------------------------------------------------------------------------
# 判据 7: recent Top5 恰 5 条 updated_at 倒序白名单字段
# ---------------------------------------------------------------------------
class TestRecentTop5:
    """判据 7: recent Top5 恰 5 条 updated_at 倒序白名单字段"""

    @pytest.mark.asyncio
    async def test_recent_requirements_exactly_5_desc(
        self, client, auth_headers, db_session, registered_user
    ):
        """造 6 条需求,响应恰 5 条且按 updated_at 倒序;字段为白名单"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]
        now = datetime.now()

        # 造 6 条需求,updated_at 依次递增
        for i in range(6):
            await _create_requirement(
                db_session, project.project_id, uid, status="draft",
                title=f"req-{i}",
                updated_at=now - timedelta(hours=i),
            )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        recent_reqs = data["recent_requirements"]
        # 恰 5 条
        assert len(recent_reqs) == 5
        # updated_at 倒序(第 1 条最新)
        for i in range(len(recent_reqs) - 1):
            assert recent_reqs[i]["updated_at"] >= recent_reqs[i + 1]["updated_at"]
        # 白名单字段:req_id, title, status, priority, delivery_date, updated_at
        whitelist = {"req_id", "title", "status", "priority", "delivery_date", "updated_at"}
        for item in recent_reqs:
            assert set(item.keys()) == whitelist, f"字段不匹配白名单: {set(item.keys())} vs {whitelist}"

    @pytest.mark.asyncio
    async def test_recent_tasks_exactly_5_desc(
        self, client, auth_headers, db_session, registered_user
    ):
        """造 6 条任务,响应恰 5 条且按 updated_at 倒序;字段为白名单"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]
        now = datetime.now()

        # 造 6 条任务,updated_at 依次递增
        for i in range(6):
            await _create_task(
                db_session, project.project_id, uid, task_type="dev", status="running",
                title=f"task-{i}",
                updated_at=now - timedelta(hours=i),
            )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        recent_tasks = data["recent_tasks"]
        # 恰 5 条
        assert len(recent_tasks) == 5
        # updated_at 倒序
        for i in range(len(recent_tasks) - 1):
            assert recent_tasks[i]["updated_at"] >= recent_tasks[i + 1]["updated_at"]
        # 白名单字段:task_id, type, title, status, updated_at, finished_at
        whitelist = {"task_id", "type", "title", "status", "updated_at", "finished_at"}
        for item in recent_tasks:
            assert set(item.keys()) == whitelist, f"字段不匹配白名单: {set(item.keys())} vs {whitelist}"


# ---------------------------------------------------------------------------
# 判据 8: 空项目全零不 500
# ---------------------------------------------------------------------------
class TestEmptyProject:
    """判据 8: 空项目全零不 500"""

    @pytest.mark.asyncio
    async def test_empty_project_all_zero(
        self, client, auth_headers, db_session, registered_user
    ):
        """新项目(无需求无任务):全零、null、空数组,不 500"""
        project = await _create_project(db_session, registered_user["user_id"])

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 需求统计全零
        assert data["requirements"]["total"] == 0
        for s in REQ_STATUSES:
            assert data["requirements"]["by_status"][s] == 0
        assert data["requirements"]["active"] == 0
        assert data["requirements"]["polish_tasks"] == 0

        # 任务统计全零
        for dim in ("dev_tasks", "test_tasks", "release_tasks"):
            assert data[dim]["total"] == 0
            for s in TASK_STATUSES:
                assert data[dim]["by_status"][s] == 0
            assert data[dim]["active"] == 0

        # tokens 全零
        assert data["tokens"]["total"] == 0
        assert data["tokens"]["in"] == 0
        assert data["tokens"]["out"] == 0

        # recent_7d 全零
        assert data["recent_7d"]["requirements_created"] == 0
        assert data["recent_7d"]["requirements_completed"] == 0
        assert data["recent_7d"]["tasks_created"] == 0
        assert data["recent_7d"]["tasks_completed"] == 0

        # latest_release null
        assert data["latest_release"] is None

        # recent 数组空
        assert data["recent_requirements"] == []
        assert data["recent_tasks"] == []


# ---------------------------------------------------------------------------
# 判据 9: 响应最小化
# ---------------------------------------------------------------------------
class TestResponseMinimization:
    """判据 9: 响应最小化(无 PII/token/extended_attributes 原文)"""

    @pytest.mark.asyncio
    async def test_no_pii_or_extended_attributes_in_response(
        self, client, auth_headers, db_session, registered_user
    ):
        """响应 JSON 无成员 PII/token/extended_attributes 原文"""
        project = await _create_project(db_session, registered_user["user_id"])
        uid = registered_user["user_id"]

        # 造需求 + 任务(带 extended_attributes)
        await _create_requirement(db_session, project.project_id, uid, status="draft")
        await _create_task(
            db_session, project.project_id, uid, task_type="release", status="done",
            extended_attributes={"deploy_phase": "deployed", "deploy_host": "10.0.0.1", "deploy_port": 3000},
        )

        resp = await client.get(f"/api/projects/{project.project_id}/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 序列化为字符串检查敏感字段
        data_str = str(data)

        # 不应包含 extended_attributes 原文
        assert "deploy_host" not in data_str
        assert "deploy_port" not in data_str
        assert "deploy_phase" not in data_str

        # latest_release 只含白名单字段
        lr = data["latest_release"]
        if lr is not None:
            allowed_keys = {"task_id", "title", "status", "branch", "preview_url", "finished_at"}
            assert set(lr.keys()) == allowed_keys, f"latest_release 字段超出白名单: {set(lr.keys())}"

        # recent_requirements 不含 PII(如 created_by)
        for req in data["recent_requirements"]:
            assert "created_by" not in req
            assert "background" not in req
            assert "description" not in req

        # recent_tasks 不含 PII(如 created_by, container_id, runner_id)
        for task in data["recent_tasks"]:
            assert "created_by" not in task
            assert "container_id" not in task
            assert "runner_id" not in task
            assert "extended_attributes" not in task
