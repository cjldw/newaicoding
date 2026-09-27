"""
R3.1 后端项目/需求搜索接口 — QA Red 阶段测试
================================================
覆盖 R3.1 完成判据(docs/20260927_任务新建菜单优化/DEVPLAN/R3.1.md):
1. 项目列表接口 GET /api/projects 支持 q 参数按名称模糊搜索
2. 需求列表接口 GET /api/projects/{project_id}/requirements 支持 q 参数按标题/描述模糊搜索
3. 搜索不区分大小写(ilike)
4. 搜索无匹配时返回空列表(code=0,items=[],total=0,不报错)

Red 判定口径:实现未落地时接口会静默忽略 q 参数(FastAPI 不声明即丢弃),
返回未过滤的全量列表 —— 因此每个用例都播种"不匹配的干扰数据",
用"干扰数据必须被排除"的断言保证 Red 阶段必然失败,而非靠匹配项缺席失败。

数据全部直插 DB(绕过 GitLab,与 test_projects_api.py 同口径),不走创建接口。
"""
import uuid

import pytest


# ---------------------------------------------------------------------------
# 测试辅助:直插 DB 造数据(绕过 GitLab)
# ---------------------------------------------------------------------------
async def _insert_project(db_session, owner_id, name, status="active"):
    """直插一条项目记录,返回 Project ORM 对象"""
    from app.models.project import Project

    p = Project(
        name=name,
        slug=f"proj-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        status=status,
        visibility="private",
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _insert_requirement(db_session, project, creator_id, title, description="d"):
    """直插一条需求记录,返回 Requirement ORM 对象"""
    from app.models.requirement import Requirement

    r = Requirement(
        req_id=str(uuid.uuid4()),
        title=title,
        description=description,
        status="draft",
        priority="medium",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id,
        project_id=project.project_id,
    )
    db_session.add(r)
    await db_session.flush()
    return r


# ---------------------------------------------------------------------------
# 1. 项目列表接口 q 搜索(按名称)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_list_search_by_name(client, db_session, registered_user, auth_headers):
    """q=Alpha → 只返回名称含 Alpha 的项目,干扰项目被排除"""
    await _insert_project(db_session, registered_user["user_id"], "Alpha 电商平台")
    await _insert_project(db_session, registered_user["user_id"], "Beta 支付系统")  # 干扰项

    resp = await client.get("/api/projects", params={"q": "Alpha"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    names = [it["name"] for it in body["data"]["items"]]
    assert any("Alpha" in n for n in names), f"匹配项目未返回: {names}"
    assert all("Beta" not in n for n in names), f"q 未生效,干扰项目未被过滤: {names}"
    assert body["data"]["total"] == 1


# ---------------------------------------------------------------------------
# 2. 需求列表接口 q 搜索(按标题)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requirement_list_search_by_title(client, db_session, registered_user, auth_headers):
    """q=登录 → 只返回标题含"登录"的需求,干扰需求被排除"""
    project = await _insert_project(db_session, registered_user["user_id"], "需求搜索项目A")
    uid = registered_user["user_id"]
    await _insert_requirement(db_session, project, uid, "用户登录模块")
    await _insert_requirement(db_session, project, uid, "订单导出功能")  # 干扰项

    resp = await client.get(
        f"/api/projects/{project.project_id}/requirements",
        params={"q": "登录"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    titles = [it["title"] for it in body["data"]["items"]]
    assert any("登录" in t for t in titles), f"匹配需求未返回: {titles}"
    assert all("订单导出" not in t for t in titles), f"q 未生效,干扰需求未被过滤: {titles}"
    assert body["data"]["total"] == 1


# ---------------------------------------------------------------------------
# 2b. 需求列表接口 q 搜索(按描述)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requirement_list_search_by_description(client, db_session, registered_user, auth_headers):
    """q 命中 description(标题不含关键字)→ 返回该需求,干扰需求被排除"""
    project = await _insert_project(db_session, registered_user["user_id"], "需求搜索项目B")
    uid = registered_user["user_id"]
    await _insert_requirement(db_session, project, uid, "报表中心", description="支持导出 Excel 报表")
    await _insert_requirement(db_session, project, uid, "消息通知", description="站内信推送")  # 干扰项

    resp = await client.get(
        f"/api/projects/{project.project_id}/requirements",
        params={"q": "Excel"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    titles = [it["title"] for it in body["data"]["items"]]
    assert "报表中心" in titles, f"按描述匹配的需求未返回: {titles}"
    assert "消息通知" not in titles, f"q 未生效,干扰需求未被过滤: {titles}"
    assert body["data"]["total"] == 1


# ---------------------------------------------------------------------------
# 3. 搜索不区分大小写
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_search_case_insensitive(client, db_session, registered_user, auth_headers):
    """名称 PlatformX,q=platformx(全小写)→ 命中;干扰项排除"""
    await _insert_project(db_session, registered_user["user_id"], "PlatformX 运营平台")
    await _insert_project(db_session, registered_user["user_id"], "完全不匹配的项目")  # 干扰项

    resp = await client.get("/api/projects", params={"q": "platformx"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    names = [it["name"] for it in body["data"]["items"]]
    assert any("PlatformX" in n for n in names), f"大小写不敏感匹配失败: {names}"
    assert all("完全不匹配" not in n for n in names), f"q 未生效,干扰项目未被过滤: {names}"


@pytest.mark.asyncio
async def test_requirement_search_case_insensitive(client, db_session, registered_user, auth_headers):
    """标题 payment dashboard,q=PAYMENT(全大写)→ 命中;干扰项排除"""
    project = await _insert_project(db_session, registered_user["user_id"], "需求搜索项目C")
    uid = registered_user["user_id"]
    await _insert_requirement(db_session, project, uid, "payment dashboard 改版")
    await _insert_requirement(db_session, project, uid, "完全不匹配的需求")  # 干扰项

    resp = await client.get(
        f"/api/projects/{project.project_id}/requirements",
        params={"q": "PAYMENT"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    titles = [it["title"] for it in body["data"]["items"]]
    assert any("payment dashboard" in t.lower() for t in titles), f"大小写不敏感匹配失败: {titles}"
    assert all("完全不匹配" not in t for t in titles), f"q 未生效,干扰需求未被过滤: {titles}"


# ---------------------------------------------------------------------------
# 4. 搜索无匹配 → 空列表,不报错
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_search_no_match_returns_empty(client, db_session, registered_user, auth_headers):
    """q=不存在的关键字 → code=0 且 items=[]、total=0(有数据但不匹配)"""
    await _insert_project(db_session, registered_user["user_id"], "存在的项目甲")
    await _insert_project(db_session, registered_user["user_id"], "存在的项目乙")

    resp = await client.get("/api/projects", params={"q": "不存在的关键字xyz"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == [], f"无匹配时应返回空列表,实际: {[it['name'] for it in body['data']['items']]}"
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_requirement_search_no_match_returns_empty(client, db_session, registered_user, auth_headers):
    """q=不存在的关键字 → code=0 且 items=[]、total=0(有数据但不匹配)"""
    project = await _insert_project(db_session, registered_user["user_id"], "需求搜索项目D")
    uid = registered_user["user_id"]
    await _insert_requirement(db_session, project, uid, "存在的需求")

    resp = await client.get(
        f"/api/projects/{project.project_id}/requirements",
        params={"q": "不存在的关键字xyz"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == [], f"无匹配时应返回空列表,实际: {[it['title'] for it in body['data']['items']]}"
    assert body["data"]["total"] == 0
