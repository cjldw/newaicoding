"""
BUG-UI-071 修复验证 — GET /api/requirements/{req_id}/archive 恒 500
==================================================================
根因:backend/app/api/knowledge.py 归档端点函数体内遗留无效 import
`from app.services.project_service import get_requirement_or_404 as _get_req`
(该函数实际定义在 app/services/requirement_service.py),每次请求执行到该行
必抛 ImportError → 恒 500。

验证口径:
1. 存在的需求(项目 owner 调用)→ 200 code=0
2. 不存在的需求 id → 非 500(404 业务语义)
"""
import uuid

import pytest

from app.models.project import Project
from app.models.requirement import Requirement


async def _mk_project_with_req(db_session, owner_id):
    project = Project(name="bug071项目", slug=f"b71-{uuid.uuid4().hex[:6]}",
                      owner_id=owner_id)
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()), title="归档需求", description="d",
        status="doing", req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=owner_id, project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    return project, req


@pytest.mark.asyncio
async def test_archive_endpoint_not_500_for_existing_requirement(
    client, auth_headers, db_session, registered_user
):
    """存在的需求:GET archive 必须 200(修复前恒 500 ImportError)"""
    _project, req = await _mk_project_with_req(db_session, registered_user["user_id"])

    resp = await client.get(
        f"/api/requirements/{req.req_id}/archive", headers=auth_headers
    )
    assert resp.status_code != 500, (
        f"BUG-UI-071 仍存在:archive 端点 500, resp={resp.text[:300]}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "timeline" in data["data"]


@pytest.mark.asyncio
async def test_archive_endpoint_not_500_for_missing_requirement(
    client, auth_headers
):
    """不存在的需求:非 500(404 业务语义即可;修复前连 404 都到不了,恒 500)"""
    resp = await client.get(
        f"/api/requirements/{uuid.uuid4()}/archive", headers=auth_headers
    )
    assert resp.status_code != 500, (
        f"BUG-UI-071 仍存在:archive 端点 500, resp={resp.text[:300]}"
    )
    assert resp.status_code == 404
