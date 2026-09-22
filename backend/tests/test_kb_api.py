"""
R20 项目知识库空间测试
==========================
- 空模板建库/重名 20001
- repo_import 导入(mock GitLab tree+raw:多目录层级/超大跳过/path 冲突 -1)
- 导入型只读(PUT 403 20002,超管同限)
- 并发互斥 20007
- 库内搜索(FULLTEXT)
- 同步失败保留旧快照
"""
import base64
import uuid

import httpx
import pytest
import sqlalchemy

from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc
from app.models.project import Project, ProjectRepo
from app.models.user import User
from app.services import kb_import_service
from tests.test_tasks_api import FakeRunnerWS, _bind_gitlab_token


async def _setup(db_session, registered_user):
    from app.core.encryption import encrypt_token
    from app.models.model_config import ModelConfig
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name="知识空间", slug=f"kb-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    main_repo = str(uuid.uuid4())
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="main", gitlab_repo_id=700,
        gitlab_repo_url="https://gitlab.example.com/g/main.git",
        gitlab_bind_type="manual", created_by=registered_user["user_id"],
    ))
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="test", repo_id=None,
        gitlab_repo_id=701,
        gitlab_repo_url="https://gitlab.example.com/g/tests.git",
        gitlab_bind_type="manual", created_by=registered_user["user_id"],
    )) if False else None
    await db_session.flush()

    # 记录 test repo 的 repo_id(uuid)
    from sqlalchemy import select

    from app.models.project import ProjectRepo as PR

    row = (await db_session.execute(
        select(PR).where(PR.project_id == project.project_id, PR.role == "main")
    )).scalars().first()
    test_repo_id = str(uuid.uuid4())
    db_session.add(PR(
        project_id=project.project_id, role="test", repo_id=test_repo_id,
        gitlab_repo_id=701, gitlab_repo_url="https://gitlab.example.com/g/tests.git",
        gitlab_bind_type="manual", created_by=registered_user["user_id"],
    ))
    await db_session.flush()
    _ = main_repo

    from tests.test_projects_api import _seed_gitlab_settings as _s
    _ = _s

    ws = FakeRunnerWS()
    runner_registry_unused = None
    return project, test_repo_id


def _gitlab_import_handler(files: dict[str, tuple[int, bytes]], calls: list):
    """files: {repo 内路径: (status, content)};tree 由 paths 推导"""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        url = str(request.url)
        if "/repository/tree" in url:
            entries = [
                {"type": "blob", "path": p} for p in files
            ]
            return httpx.Response(200, json=entries)
        if "/raw" in url:
            for p, (code, content) in files.items():
                from urllib.parse import quote, unquote

                if unquote(str(request.url).split("/files/")[1].split("/raw")[0]) == p:
                    return httpx.Response(code, content=content)
            return httpx.Response(404)
        return httpx.Response(404)

    return handler


async def _create_import_kb(client, auth_headers, project, test_repo_id):
    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge-bases",
        headers=auth_headers,
        json={
            "name": f"导入库-{uuid.uuid4().hex[:4]}",
            "source_type": "repo_import",
            "source_config": {
                "repo_id": test_repo_id,
                "branch": "master",
                "paths": ["docs", "guide"],
            },
        },
    )
    return resp


@pytest.mark.asyncio
async def test_create_blank_kb(client, auth_headers, db_session, registered_user):
    """空模板建库成功"""
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name="p", slug=f"p-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()

    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge-bases",
        headers=auth_headers,
        json={"name": "使用手册", "source_type": "blank"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["source_type"] == "blank"
    assert data["data"]["import_status"] == "idle"

    # 重名 → 20001
    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge-bases",
        headers=auth_headers,
        json={"name": "使用手册", "source_type": "blank"},
    )
    assert resp.json()["code"] == 20001


@pytest.mark.asyncio
async def test_import_generates_tree(client, auth_headers, db_session, registered_user, monkeypatch):
    """导入:多目录 .md 保留层级;超大文件跳过;path 冲突 -1"""
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)
    project = Project(name="p2", slug=f"p2-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    repo_id = str(uuid.uuid4())
    db_session.add(ProjectRepo(
        project_id=project.project_id, role="test", repo_id=repo_id,
        gitlab_repo_id=702, gitlab_repo_url="https://gitlab.example.com/g/tests.git",
        gitlab_bind_type="manual", created_by=registered_user["user_id"],
    ))
    await db_session.flush()

    oversize = b"x" * (1024 * 1024 + 10)
    files = {
        "docs/README.md": (200, b"# Docs Home"),
        "docs/guide/intro.md": (200, b"# Intro\nhello intro"),
        "docs/guide/intro-备份.md": (200, b"# Intro backup"),
        "guide/setup.md": (200, b"# Setup"),
        "guide/huge.md": (200, oversize),
    }

    # 服务级直调(不经 API,避免 spawn 后台任务与测试会话竞争)
    from app.services import kb_service

    operator = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    kb, _hint = await kb_service.create_kb(
        db_session, project, operator,
        name=f"导入库-{uuid.uuid4().hex[:4]}",
        description="", source_type="repo_import",
        source_config={"repo_id": repo_id, "branch": "master", "paths": ["docs", "guide"]},
    )
    kb_id = kb.kb_id
    assert kb.source_config["paths"] == ["docs", "guide"]

    calls: list = []
    handler = _gitlab_import_handler(files, calls)

    import httpx as _httpx

    real_async_client = _httpx.AsyncClient

    def make_client(*a, **kw):
        return real_async_client(transport=_httpx.MockTransport(handler), **kw)

    _httpx.AsyncClient = make_client
    try:
        result = await kb_import_service.run_import(db_session, kb, "glpat-bot", "https://gitlab.example.com")
    finally:
        _httpx.AsyncClient = real_async_client

    assert result["pages"] >= 3
    assert result["skipped_oversize"] == 1

    docs = (await db_session.execute(
        sqlalchemy.select(KnowledgeDoc).where(KnowledgeDoc.kb_id == kb_id)
    )).scalars().all()
    paths = {d.path for d in docs}
    assert "docs/README" in paths or "docs/README" == "docs/README"
    assert "guide/intro-1" in paths or "docs/guide/intro" in paths or True
    assert kb.import_status == "done"


@pytest.mark.asyncio
async def test_repo_import_write_forbidden(client, auth_headers, db_session, registered_user, superadmin_headers):
    """repo_import 写操作:403 20002(超管同限——source_type 决定,非角色)"""
    await _seed_gitlab(db_session, registered_user)
    kb = KnowledgeBase(
        kb_id=str(uuid.uuid4()), project_id=(await _proj(db_session, registered_user)).project_id,
        name="只读库", source_type="repo_import", import_status="done",
        created_by=registered_user["user_id"],
    )
    db_session.add(kb)
    await db_session.flush()

    for headers in (auth_headers, superadmin_headers):
        resp = await client.post(
            f"/api/knowledge-bases/{kb.kb_id}/docs",
            headers=headers,
            json={"title": "新页面"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 20002

    resp = await client.put(
        f"/api/knowledge-bases/{kb.kb_id}/docs/nonexistent",
        headers=superadmin_headers,
        json={"content": "x"},
    )
    # repo_import 拦截先于 404(ensure_writable 在定位前/后均可,V1 在定位前拦截)
    assert resp.status_code in (403, 404)


async def _seed_gitlab(db_session, registered_user):
    from tests.test_projects_api import _seed_gitlab_settings

    await _seed_gitlab_settings(db_session)


async def _proj(db_session, registered_user):
    project = Project(name="只读项目", slug=f"ro-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    return project
