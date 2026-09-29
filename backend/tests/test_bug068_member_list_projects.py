"""
BUG-068:非 owner 成员的项目列表为空
====================================
规格:R2.md line 331 "成员体系 R12 接入后扩展为成员项目";
     R12.md line 1341 "数据范围:用户是成员的所有项目"。
修法:list_projects 从 owner-only 改为 owner ∪ 成员行去重;超管可见全部。
"""
import uuid
import pytest

from tests.test_projects_api import _insert_project


async def _register_and_login(client):
    """注册+登录一个新用户,返回 (headers, user_id)"""
    phone = f"138{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    access_token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}, user_id


async def _register_superadmin(client):
    """注册第一个用户(自动成为 superadmin)"""
    phone = f"187{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    access_token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}, user_id


@pytest.mark.asyncio
async def test_member_only_user_can_see_project(client, db_session):
    """成员-only 用户(非 owner)能在列表看到自己作为成员的项目"""
    from app.models.project_member import ProjectMember

    # 造一个 owner(不是当前测试用户)
    owner_headers, owner_id = await _register_and_login(client)
    # 造一个成员用户
    member_headers, member_id = await _register_and_login(client)

    # owner 建一个项目
    project = await _insert_project(db_session, owner_id=owner_id)

    # 把 member 加为 editor 成员行
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=member_id,
        role="editor", invited_by=owner_id,
    ))
    await db_session.flush()

    # 成员用户 list → 应看到这个项目
    resp = await client.get("/api/projects", headers=member_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["total"] >= 1, f"成员应看到项目,实际 total={data['data']['total']}"
    pids = [item["project_id"] for item in data["data"]["items"]]
    assert project.project_id in pids, f"成员列表应包含 project {project.project_id},实际: {pids}"


@pytest.mark.asyncio
async def test_owner_still_sees_own_projects(client, db_session):
    """owner 仍能看到自己创建的项目"""
    owner_headers, owner_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=owner_id)

    resp = await client.get("/api/projects", headers=owner_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["total"] >= 1
    pids = [item["project_id"] for item in data["data"]["items"]]
    assert project.project_id in pids


@pytest.mark.asyncio
async def test_soft_deleted_project_not_in_list(client, db_session):
    """软删项目不出现在成员列表"""
    from app.models.project_member import ProjectMember

    owner_headers, owner_id = await _register_and_login(client)
    member_headers, member_id = await _register_and_login(client)

    # 建一个已软删的项目
    project = await _insert_project(db_session, owner_id=owner_id, status="deleted")
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=member_id,
        role="editor", invited_by=owner_id,
    ))
    await db_session.flush()

    resp = await client.get("/api/projects", headers=member_headers)
    data = resp.json()
    pids = [item["project_id"] for item in data["data"]["items"]]
    assert project.project_id not in pids, "软删项目不应出现在列表"


@pytest.mark.asyncio
async def test_superadmin_sees_all_projects(client, db_session):
    """超管能看到所有项目(含非成员项目)"""
    # 先注册超管(第一个用户)
    sa_headers, sa_id = await _register_superadmin(client)
    # 再注册一个普通用户建项目
    user_headers, user_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=user_id)

    # 超管 list → 应看到所有项目
    resp = await client.get("/api/projects", headers=sa_headers)
    assert resp.status_code == 200
    data = resp.json()
    pids = [item["project_id"] for item in data["data"]["items"]]
    assert project.project_id in pids, "超管应能看到所有项目"


@pytest.mark.asyncio
async def test_no_duplicate_projects_for_owner_who_is_also_member(client, db_session):
    """owner 同时也是成员行时(懒回填场景),列表不重复"""
    from app.models.project_member import ProjectMember

    owner_headers, owner_id = await _register_and_login(client)
    project = await _insert_project(db_session, owner_id=owner_id)
    # owner 自己也有一条成员行
    db_session.add(ProjectMember(
        project_id=project.project_id, user_id=owner_id,
        role="owner", invited_by=owner_id,
    ))
    await db_session.flush()

    resp = await client.get("/api/projects", headers=owner_headers)
    data = resp.json()
    pids = [item["project_id"] for item in data["data"]["items"]]
    # 不应重复
    assert pids.count(project.project_id) == 1, f"不应重复: {pids}"
