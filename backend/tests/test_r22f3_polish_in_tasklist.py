"""
R22.F3 打磨任务纳入 /manage/tasks 任务列表
==========================================
BUG-064:用户通过「开始打磨」创建的 type='requirement' 打磨任务不出现在 /manage/tasks。
根因:dashboard_views.py:135 白名单只接受 dev/test/release,排除 requirement。

覆盖:
1. requirement 类型任务出现在任务列表响应(超管口径,/tasks/dev 混合返回)
2. dev/test/release 既有查询零回归
3. scope 不变:created_by=me + 可见项目过滤仍生效(普通用户看不到他人任务)
"""
import uuid

import pytest

from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task
from tests.test_projects_api import _register_and_login


async def _setup(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(
        name="R22F3 项目", slug=f"r22f3-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_req(db_session, project, creator_id, title):
    r = Requirement(
        req_id=str(uuid.uuid4()), title=title, description="d", status="approved",
        priority="medium", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_task(db_session, project, creator_id, requirement, task_type, title, status="running"):
    t = Task(
        task_id=str(uuid.uuid4()), req_id=requirement.req_id,
        project_id=project.project_id, type=task_type, title=title,
        description="d", base_branch="b", work_branch="b", status=status,
        conversation_id=str(uuid.uuid4()), created_by=creator_id,
    )
    db_session.add(t)
    await db_session.flush()
    return t


# ---------------------------------------------------------------------------
# 1. requirement 类型任务出现在 /tasks/dev 响应(混合返回)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requirement_task_appears_in_dev_list(client, auth_headers, db_session, registered_user):
    """BUG-064:打磨任务(type='requirement')出现在 /tasks/dev 列表"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "打磨需求")

    # 创建 2 条打磨任务 + 1 条 dev 任务
    t1 = await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "打磨:A")
    t2 = await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "打磨:B")
    t3 = await _mk_task(db_session, project, registered_user["user_id"], req, "dev", "开发任务")

    resp = await client.get("/api/dashboard/tasks/dev", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    # 总数 = 3(2 requirement + 1 dev)
    assert data["total"] == 3, f"期望 3 条任务,实际 total={data['total']}"

    # 所有 task_id 都出现
    returned_ids = {item["task_id"] for item in data["items"]}
    assert t1.task_id in returned_ids, "打磨任务 t1 应出现在列表"
    assert t2.task_id in returned_ids, "打磨任务 t2 应出现在列表"
    assert t3.task_id in returned_ids, "dev 任务 t3 应出现在列表"

    # 类型字段正确
    types = {item["task_id"]: item["type"] for item in data["items"]}
    assert types[t1.task_id] == "requirement"
    assert types[t2.task_id] == "requirement"
    assert types[t3.task_id] == "dev"


# ---------------------------------------------------------------------------
# 2. dev/test/release 既有查询零回归
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_test_release_list_unchanged(client, auth_headers, db_session, registered_user):
    """test/release 维列表不受影响,仍只返回各自类型"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "需求")

    await _mk_task(db_session, project, registered_user["user_id"], req, "test", "测试任务", "passed")
    await _mk_task(db_session, project, registered_user["user_id"], req, "release", "发布任务", "deployed")
    await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "打磨任务", "running")

    # test 维:只返回 test 类型
    resp_test = await client.get("/api/dashboard/tasks/test", headers=auth_headers)
    data_test = resp_test.json()["data"]
    assert data_test["total"] == 1
    assert data_test["items"][0]["type"] == "test"

    # release 维:只返回 release 类型
    resp_release = await client.get("/api/dashboard/tasks/release", headers=auth_headers)
    data_release = resp_release.json()["data"]
    assert data_release["total"] == 1
    assert data_release["items"][0]["type"] == "release"


# ---------------------------------------------------------------------------
# 3. scope 不变:created_by=me + 可见项目过滤仍生效
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_filter_unchanged(client, auth_headers, db_session, registered_user):
    """普通用户看不到他人的打磨任务(scope 未破)"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "需求")

    # 超管创建 2 条打磨任务
    await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "超管打磨A", "running")
    await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "超管打磨B", "running")

    # 普通用户登录
    other_headers, other_uid = await _register_and_login(client)
    from app.models.project_member import ProjectMember
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=other_uid, role="editor",
        invited_by=registered_user["user_id"],
    ))
    await db_session.flush()

    # 普通用户查 /tasks/dev:应返回 0 条(created_by=me,他没有创建任何任务)
    resp = await client.get("/api/dashboard/tasks/dev", headers=other_headers)
    data = resp.json()["data"]
    assert data["total"] == 0, f"普通用户应看不到超管的打磨任务,实际 total={data['total']}"


# ---------------------------------------------------------------------------
# 4. 未知维度仍返回 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_dimension_still_404(client, auth_headers):
    """未知维度(非 dev/test/release/requirement)仍返回 404"""
    resp = await client.get("/api/dashboard/tasks/unknown", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. requirement 维度单独查询(可选:如果后端支持 /tasks/requirement)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requirement_dimension_alone(client, auth_headers, db_session, registered_user):
    """如果后端支持 /tasks/requirement,应只返回 requirement 类型"""
    project = await _setup(db_session, registered_user)
    req = await _mk_req(db_session, project, registered_user["user_id"], "需求")

    await _mk_task(db_session, project, registered_user["user_id"], req, "requirement", "打磨1", "running")
    await _mk_task(db_session, project, registered_user["user_id"], req, "dev", "开发1", "running")

    resp = await client.get("/api/dashboard/tasks/requirement", headers=auth_headers)
    # 如果后端支持此端点,应返回 200 + 只含 requirement
    if resp.status_code == 200:
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["type"] == "requirement"
    else:
        # 不支持也 OK,/tasks/dev 混合返回已满足需求
        assert resp.status_code == 404
