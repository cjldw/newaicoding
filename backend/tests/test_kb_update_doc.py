"""
R2.F4 kb update_doc 保存回归(BUG-KB-004 阻断项)
==================================================
- 现象:PUT /knowledge-bases/{kb_id}/docs/{doc_id} 恒 500 —— kb_service.update_doc
  在 `await db.flush()` 后直接读 `doc.updated_at`,`onupdate=func.now()` 使属性过期,
  属性访问触发隐式同步 SELECT → async SQLAlchemy MissingGreenlet。
- 期望:保存 200(code=0),返回 updated_at,且库中 updated_at 被刷新。
- 脚手架照抄 tests/test_kb_api.py 的 blank 建库链路。
"""
import uuid
from datetime import datetime

import pytest
import sqlalchemy

from app.models.knowledge_base import KnowledgeDoc
from app.models.project import Project

from tests.test_projects_api import _seed_gitlab_settings


async def _setup_blank_kb(db_session, client, auth_headers, registered_user):
    """空模板建库 + 建页面,返回 (kb_id, doc_id)"""
    await _seed_gitlab_settings(db_session)
    project = Project(name="p-ud", slug=f"pud-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()

    resp = await client.post(
        f"/api/projects/{project.project_id}/knowledge-bases",
        headers=auth_headers,
        json={"name": f"编辑库-{uuid.uuid4().hex[:4]}", "source_type": "blank"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    kb_id = data["data"]["kb_id"]

    resp = await client.post(
        f"/api/knowledge-bases/{kb_id}/docs",
        headers=auth_headers,
        json={"title": "首页"},
    )
    data = resp.json()
    assert data["code"] == 0, data
    doc_id = data["data"]["doc_id"]
    return kb_id, doc_id


@pytest.mark.asyncio
async def test_update_doc_returns_200_and_refreshes_updated_at(
    client, auth_headers, db_session, registered_user
):
    """保存页面:200 + updated_at 刷新(修复前:flush 后读过期属性 → 500)"""
    kb_id, doc_id = await _setup_blank_kb(db_session, client, auth_headers, registered_user)

    # 哨兵:把 updated_at 拨回过去(core UPDATE 不触发 ORM onupdate),
    # 保存后应被 onupdate=func.now() 刷新为当前时间(秒级精度下仍必然 ≠ 哨兵)
    await db_session.execute(
        sqlalchemy.text(
            "UPDATE knowledge_docs SET updated_at='2020-01-01 00:00:00' WHERE doc_id=:d"
        ).bindparams(d=doc_id)
    )
    db_session.expire_all()

    resp = await client.put(
        f"/api/knowledge-bases/{kb_id}/docs/{doc_id}",
        headers=auth_headers,
        json={"title": "首页(改)", "content": "# 新内容\n- a\n- b"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["doc_id"] == doc_id
    assert data["data"]["updated_at"], data

    # 库内复核:content 落库 + updated_at 已离开哨兵
    doc = (await db_session.execute(
        sqlalchemy.select(KnowledgeDoc).where(KnowledgeDoc.doc_id == doc_id)
    )).scalars().one()
    assert doc.content == "# 新内容\n- a\n- b"
    assert doc.title == "首页(改)"
    assert doc.updated_at != datetime(2020, 1, 1)
    assert doc.updated_at.year >= 2026


@pytest.mark.asyncio
async def test_rename_kb_returns_200_and_refreshes_updated_at(
    client, auth_headers, db_session, registered_user
):
    """重命名库:同病同修 —— rename_kb flush 后 _kb_brief 读 kb.updated_at 同样触发
    MissingGreenlet(PATCH /knowledge-bases/{kb_id} 恒 500)"""
    from app.models.knowledge_base import KnowledgeBase

    await _seed_gitlab_settings(db_session)
    project = Project(name="p-rn", slug=f"prn-{uuid.uuid4().hex[:6]}",
                      owner_id=registered_user["user_id"])
    db_session.add(project)
    await db_session.flush()
    kb = KnowledgeBase(project_id=project.project_id, name="旧名", source_type="blank",
                       import_status="idle", created_by=registered_user["user_id"])
    db_session.add(kb)
    await db_session.flush()
    kb_id = kb.kb_id

    resp = await client.patch(
        f"/api/projects/{project.project_id}/knowledge-bases/{kb_id}",
        headers=auth_headers,
        json={"name": "新名"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["name"] == "新名"
    assert data["data"]["updated_at"], data
