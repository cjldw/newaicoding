"""
R14 归档与知识库测试
==========================
- 归档数据(时间线/总结路径/需求 done 自动归档 → archived)
- 知识条目:创建(published)/发布(draft→published)/提升平台级/搜索/tag 过滤/平台 Tab 口径
"""
import uuid

import pytest
import sqlalchemy

from app.models.knowledge_entry import KnowledgeEntry
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.task import Task
from app.models.user import User
from app.services import archive_service, knowledge_service


async def _setup(db_session, registered_user):
    project = Project(name="归档项目", slug=f"ar-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project


async def _mk_done_requirement_with_release(db_session, project, creator_id):
    """done 需求 + 已部署 release 任务(触发自动归档的口径)"""
    req = Requirement(
        req_id=str(uuid.uuid4()), title="下单流程重构", description="d",
        status="done", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=creator_id, project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    release = Task(
        task_id=str(uuid.uuid4()), req_id=req.req_id, project_id=project.project_id,
        type="release", title="发布", description="d",
        base_branch="master", work_branch="master",
        status="done", conversation_id=str(uuid.uuid4()),
        created_by=creator_id,
        extended_attributes={"deploy_phase": "deployed", "deploy_host": "x.example.com",
                             "deploy_port": 10080},
    )
    db_session.add(release)
    await db_session.flush()
    return req, release


@pytest.mark.asyncio
async def test_archive_success(client, auth_headers, db_session, registered_user):
    """自动归档:done 需求 → archived;时间线/总结路径/知识条目(draft)齐备"""
    project = await _setup(db_session, registered_user)
    req, _release = await _mk_done_requirement_with_release(db_session, project, registered_user["user_id"])

    await archive_service.archive_requirement(db_session, req, project)
    await db_session.refresh(req)
    assert req.status == "archived"

    data = await archive_service.get_archive_data(db_session, req)
    assert data["summary_file_path"].startswith("docs/")
    assert data["summary_file_path"].endswith("_archive/summary.md")
    types = [n["type"] for n in data["timeline"]]
    assert "requirement_created" in types
    assert "deployed" in types
    assert len(data["knowledge"]) == 1
    assert data["knowledge"][0]["status"] == "draft"


@pytest.mark.asyncio
async def test_archive_skip_non_done(db_session, registered_user):
    """非 done 需求调用归档:跳过(不置 archived)"""
    project = await _setup(db_session, registered_user)
    req = Requirement(
        req_id=str(uuid.uuid4()), title="t", description="d",
        status="reviewing", req_branch="req-x",
        created_by=registered_user["user_id"], project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    await archive_service.archive_requirement(db_session, req, project)
    await db_session.refresh(req)
    assert req.status == "reviewing"


@pytest.mark.asyncio
async def test_create_and_publish_knowledge(client, auth_headers, db_session, registered_user):
    """创建知识条目(human/published)→ 发布接口对 draft 生效"""
    project = await _setup(db_session, registered_user)
    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge",
        headers=auth_headers,
        json={"type": "code_snippet", "title": "重试装饰器",
              "content": "tenacity 用法示例", "tags": ["python", "retry"]},
    )
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "published"

    entry_id = data["data"]["entry_id"]

    # AI 草稿条目(直插 draft)→ 发布
    draft = KnowledgeEntry(
        entry_id=str(uuid.uuid4()), project_id=project.project_id,
        req_id="req-x", type="pitfall", title="时区坑",
        content="UTC 转换注意", tags=["tz"], status="draft", created_by="ai",
    )
    db_session.add(draft)
    await db_session.flush()
    resp = await client.post(f"/api/knowledge/{draft.entry_id}/publish", headers=auth_headers)
    assert resp.json()["code"] == 0
    await db_session.refresh(draft)
    assert draft.status == "published"


@pytest.mark.asyncio
async def test_promote_knowledge_to_platform(client, auth_headers, db_session, registered_user):
    """提升到平台级:project_id 置 null;平台 Tab 仅 published"""
    project = await _setup(db_session, registered_user)
    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge",
        headers=auth_headers,
        json={"type": "pattern", "title": "通用分页", "content": "cursor 分页模式", "tags": ["db"]},
    )
    entry_id = resp.json()["data"]["entry_id"]

    resp = await client.post(f"/api/knowledge/{entry_id}/promote", headers=auth_headers)
    assert resp.json()["code"] == 0
    entry = (await db_session.execute(
        sqlalchemy.select(KnowledgeEntry).where(KnowledgeEntry.entry_id == entry_id)
    )).scalars().first()
    assert entry.project_id is None

    # 平台知识库列表可见
    resp = await client.get("/api/knowledge", headers=auth_headers)
    items = resp.json()["data"]["items"]
    assert any(i["entry_id"] == entry_id for i in items)


@pytest.mark.asyncio
async def test_search_knowledge(client, auth_headers, db_session, registered_user):
    """搜索:关键词命中 + tag 过滤"""
    project = await _setup(db_session, registered_user)
    for title, tag in (("redis 缓存实践", "redis"), ("celery 队列", "celery")):
        resp = await client.post(
            f"/api/projects/{project.project_id}/knowledge",
            headers=auth_headers,
            json={"type": "pattern", "title": title, "content": f"{title} 正文", "tags": [tag]},
        )
        assert resp.json()["code"] == 0
    await db_session.commit()  # FULLTEXT 仅索引已提交行

    # 关键词搜索(q=redis → FULLTEXT/LIKE 命中标题)
    resp = await client.get(
        f"/api/projects/{project.project_id}/knowledge",
        headers=auth_headers,
        params={"q": "redis"},
    )
    titles = [i["title"] for i in resp.json()["data"]["items"]]
    assert titles == ["redis 缓存实践"]

    # tag 过滤
    resp = await client.get(
        f"/api/projects/{project.project_id}/knowledge",
        headers=auth_headers,
        params={"tag": "celery"},
    )
    titles = [i["title"] for i in resp.json()["data"]["items"]]
    assert titles == ["celery 队列"]
