"""
R7 工作台「与我相关」口径测试
==============================
summary 四维口径升级:created_by=me → (JSON_CONTAINS(related_user_ids, me) ∪ created_by=me);
任务维加需求传导(req_id IN 我相关的需求)并去重;recent 行透传 delivery_date。

覆盖(R7.md 完成判据 + 测试验证逻辑):
1. 用户 B 是需求 X 关联用户(非创建者)→ summary.requirements 统计/最近列表含 X
2. 创建者口径回归:B 创建的需求照常出现
3. 任务传导:B 关联需求 X 的 dev/test/release 任务进任务维;既创建又关联不重复计
4. 他人数据不出现:仅与 A 相关的需求/任务,B(同项目成员)不可见
5. related_user_ids NULL 存量需求:仅创建者可见(原口径)
6. delivery_date 透传:requirements recent 行含 delivery_date(前端徽章用)

Red 基线(2026-09-26):现实现 app/api/dashboard.py 为 created_by=only,
用例 1/3/6 预期失败(新口径未实现),用例 2/4/5 为原口径回归守护(应保持通过)。
"""
import uuid
from datetime import date

import pytest

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.models.task import Task
from tests.test_projects_api import _register_and_login


# ---------------------------------------------------------------------------
# 造数辅助(与 test_dashboard.py 同风格;扩展 related_user_ids/delivery_date/req 传导)
# ---------------------------------------------------------------------------
async def _setup_project(db_session, owner_id, name="R7工作台项目"):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name=name, slug=f"r7-{uuid.uuid4().hex[:6]}", owner_id=owner_id)
    db_session.add(project)
    await db_session.flush()
    return project


async def _add_member(db_session, project, user_id, invited_by):
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=user_id, role="editor", invited_by=invited_by,
    ))
    await db_session.flush()


async def _mk_req(db_session, project, creator_id, title, status="approved",
                  related_user_ids=None, delivery_date=None):
    r = Requirement(
        req_id=str(uuid.uuid4()), title=title, description="d", status=status,
        priority="medium", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        related_user_ids=related_user_ids, delivery_date=delivery_date,
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _mk_task(db_session, project, creator_id, requirement, task_type, title, status="running"):
    t = Task(
        task_id=str(uuid.uuid4()), req_id=requirement.req_id, project_id=project.project_id,
        type=task_type, title=title, description="d",
        base_branch="b", work_branch="b", status=status,
        conversation_id=str(uuid.uuid4()), created_by=creator_id,
    )
    db_session.add(t)
    await db_session.flush()
    return t


def _recent_ids(block) -> list:
    return [row["req_id"] if "req_id" in row else row["task_id"] for row in block["recent"]]


# ---------------------------------------------------------------------------
# 1. 关联用户(非创建者)命中需求维
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_related_user_sees_requirement(client, auth_headers, db_session, registered_user):
    """B 是需求 X 的关联用户(创建者为 A)→ B 的 summary.requirements 含 X"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req = await _mk_req(db_session, project, registered_user["user_id"], "关联需求X",
                        related_user_ids=[b_uid])

    resp = await client.get("/api/dashboard/summary", headers=b_headers)
    assert resp.status_code == 200
    block = resp.json()["data"]["requirements"]
    assert block["total"] == 1, f"关联用户应命中需求统计,实际 total={block['total']}"
    assert req.req_id in _recent_ids(block), "关联需求应出现在最近列表"


@pytest.mark.asyncio
async def test_related_user_counts_by_status(client, auth_headers, db_session, registered_user):
    """关联命中的需求同样计入 by_status 分布(口径统一)"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    await _mk_req(db_session, project, registered_user["user_id"], "关联需求X",
                  status="in_progress", related_user_ids=[b_uid])

    resp = await client.get("/api/dashboard/summary", headers=b_headers)
    by_status = resp.json()["data"]["requirements"]["by_status"]
    assert by_status["in_progress"] == 1, f"关联需求应计入状态分布,实际 {by_status}"


# ---------------------------------------------------------------------------
# 2. 创建者口径回归
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_creator_scope_regression(client, auth_headers, db_session, registered_user):
    """原口径回归:自己创建的需求照常出现(即便同时把他人列为关联用户)"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)

    req = await _mk_req(db_session, project, registered_user["user_id"], "我创建的需求",
                        related_user_ids=[b_uid])

    resp = await client.get("/api/dashboard/summary", headers=auth_headers)
    block = resp.json()["data"]["requirements"]
    assert block["total"] == 1
    assert req.req_id in _recent_ids(block)


# ---------------------------------------------------------------------------
# 3. 任务传导 + 去重
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_task_propagation_from_related_req(client, auth_headers, db_session, registered_user):
    """B 关联需求 X → X 的 dev/test/release 任务(他人创建)进 B 的任务维统计与最近列表"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req_x = await _mk_req(db_session, project, registered_user["user_id"], "关联需求X",
                          related_user_ids=[b_uid])
    dev = await _mk_task(db_session, project, registered_user["user_id"], req_x, "dev", "开发任务")
    test_t = await _mk_task(db_session, project, registered_user["user_id"], req_x, "test", "测试任务")
    release_t = await _mk_task(db_session, project, registered_user["user_id"], req_x, "release", "发布任务")

    resp = await client.get("/api/dashboard/summary", headers=b_headers)
    data = resp.json()["data"]
    assert data["dev_tasks"]["total"] == 1, \
        f"关联需求的 dev 任务应传导计入,实际 {data['dev_tasks']['total']}"
    assert data["test_tasks"]["total"] == 1
    assert data["release_tasks"]["total"] == 1
    assert dev.task_id in _recent_ids(data["dev_tasks"])
    assert test_t.task_id in _recent_ids(data["test_tasks"])
    assert release_t.task_id in _recent_ids(data["release_tasks"])


@pytest.mark.asyncio
async def test_task_propagation_dedup(client, auth_headers, db_session, registered_user):
    """去重:B 创建的任务落在自己关联的需求 X 上,同任务命中「创建」与「传导」两分支只计一次"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req_x = await _mk_req(db_session, project, registered_user["user_id"], "关联需求X",
                          related_user_ids=[b_uid])
    # A 创建的传导任务 + B 自己创建(且需求与自己相关)的任务
    dev_a = await _mk_task(db_session, project, registered_user["user_id"], req_x, "dev", "A的开发任务")
    dev_b = await _mk_task(db_session, project, b_uid, req_x, "dev", "B的开发任务")

    resp = await client.get("/api/dashboard/summary", headers=b_headers)
    block = resp.json()["data"]["dev_tasks"]
    assert block["total"] == 2, \
        f"两分支去重后应为 2(A 传导 1 + B 自建 1),实际 {block['total']}(重复计则 >2)"
    ids = _recent_ids(block)
    assert dev_a.task_id in ids and dev_b.task_id in ids
    assert len(ids) == len(set(ids)), f"最近列表任务去重,实际 {ids}"


# ---------------------------------------------------------------------------
# 4. 他人数据不出现
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_others_related_data_not_visible(client, auth_headers, db_session, registered_user):
    """需求仅与第三者 C 相关(非 B 非 B 创建)→ B 同项目成员也不可见(项目可见≠数据可见)"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    c_headers, c_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req_z = await _mk_req(db_session, project, registered_user["user_id"], "仅C相关需求",
                          related_user_ids=[c_uid])
    await _mk_task(db_session, project, registered_user["user_id"], req_z, "dev", "C相关开发任务")

    resp = await client.get("/api/dashboard/summary", headers=b_headers)
    data = resp.json()["data"]
    assert data["requirements"]["total"] == 0, "仅他人相关的需求不应出现在 B 的统计"
    assert _recent_ids(data["requirements"]) == []
    assert data["dev_tasks"]["total"] == 0, "仅他人相关需求的任务不应传导给 B"


# ---------------------------------------------------------------------------
# 5. related_user_ids NULL 存量:仅创建者可见
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_null_related_legacy_creator_only(client, auth_headers, db_session, registered_user):
    """存量需求 related_user_ids=NULL:创建者照常可见,关联用户口径不得误伤放大"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req_w = await _mk_req(db_session, project, registered_user["user_id"], "存量需求W",
                          related_user_ids=None)  # 显式 NULL
    await _mk_task(db_session, project, registered_user["user_id"], req_w, "dev", "存量开发任务")

    # 创建者可见(原口径)
    resp_owner = await client.get("/api/dashboard/summary", headers=auth_headers)
    data_owner = resp_owner.json()["data"]
    assert data_owner["requirements"]["total"] == 1
    assert req_w.req_id in _recent_ids(data_owner["requirements"])
    assert data_owner["dev_tasks"]["total"] == 1

    # 同项目成员 B(非创建者、非关联)不可见
    resp_b = await client.get("/api/dashboard/summary", headers=b_headers)
    data_b = resp_b.json()["data"]
    assert data_b["requirements"]["total"] == 0, "NULL 关联存量需求仅创建者可见"
    assert data_b["dev_tasks"]["total"] == 0, "NULL 关存量的任务不传导给非创建者"


# ---------------------------------------------------------------------------
# 6. delivery_date 透传
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delivery_date_passthrough(client, auth_headers, db_session, registered_user):
    """recent 行透传 delivery_date(前端徽章用):关联用户视角与创建者视角都要带"""
    project = await _setup_project(db_session, registered_user["user_id"])
    b_headers, b_uid = await _register_and_login(client)
    await _add_member(db_session, project, b_uid, registered_user["user_id"])

    req = await _mk_req(db_session, project, registered_user["user_id"], "带交付时间需求",
                        related_user_ids=[b_uid], delivery_date=date(2026, 10, 1))

    # 关联用户 B:行可见且带 delivery_date
    resp_b = await client.get("/api/dashboard/summary", headers=b_headers)
    rows_b = [r for r in resp_b.json()["data"]["requirements"]["recent"] if r["req_id"] == req.req_id]
    assert rows_b, "关联用户 recent 应含该需求"
    assert rows_b[0].get("delivery_date") == "2026-10-01", \
        f"recent 行应透传 delivery_date,实际 {rows_b[0]}"

    # 创建者 A:同样透传
    resp_a = await client.get("/api/dashboard/summary", headers=auth_headers)
    rows_a = [r for r in resp_a.json()["data"]["requirements"]["recent"] if r["req_id"] == req.req_id]
    assert rows_a, "创建者 recent 应含该需求"
    assert rows_a[0].get("delivery_date") == "2026-10-01", \
        f"创建者视角 recent 行应透传 delivery_date,实际 {rows_a[0]}"
