"""
R34.F1 需求分支默认策略(用户口径):req-{id8} → feat/{需求名首拼≤10}{日期YYYYMMDD}

- gen_req_branch_slug:汉字拼音首字母 + ASCII 首字母,截 10,空回退 req
- default_req_branch:feat/{slug}{Asia/Shanghai 日期}
- create_requirement:未填 req_branch 走新策略;显式填写优先(旧行为不变)
"""
import uuid
from unittest.mock import patch

import httpx
import pytest

from app.services.requirement_service import default_req_branch, gen_req_branch_slug
from tests.test_requirements_api import _gitlab_branch_handler, _setup_project


# ---------------------------------------------------------------------------
# 生成策略单测(纯函数)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("title,expected", [
    ("用户登录功能优化", "yhdlgnyh"),
    ("登录", "dl"),
    ("需求", "xq"),
    ("任务", "rw"),
    ("发布", "fb"),
    ("测试管理", "csgl"),
    ("AI 助手", "azs"),
    ("Payment Gateway", "pg"),
    ("订单状态机重构与兼容方案设计实战", "ddztjzgyjr"),  # 截断 10
    ("", "req"),
    ("!!!", "req"),
    ("  ", "req"),
])
def test_gen_req_branch_slug(title, expected):
    assert gen_req_branch_slug(title) == expected


def test_default_req_branch_uses_shanghai_date():
    with patch("app.services.requirement_service.datetime") as mock_dt:
        from datetime import datetime as real_dt
        from zoneinfo import ZoneInfo

        mock_dt.now.return_value = real_dt(2026, 9, 26, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        branch = default_req_branch("用户登录功能优化")
        assert branch == "feat/yhdlgnyh20260926"


# ---------------------------------------------------------------------------
# 创建链路:默认走新策略;显式填写优先
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_requirement_default_branch_feat_strategy(client, auth_headers, db_session, registered_user):
    """未填 req_branch → feat/{首拼}{日期},不再是 req-{id8}"""
    project = await _setup_project(db_session, registered_user)
    calls: list = []

    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "用户登录功能", "description": "支持手机号登录"},
        )
    data = resp.json()
    assert data["code"] == 0, data
    branch = data["data"]["req_branch"]
    assert branch.startswith("feat/yhdlgn")
    assert not branch.startswith("req-")
    # GitLab 侧收到的 branch 名与落库一致
    assert any("repository/branches" in u for _, u in calls)


@pytest.mark.asyncio
async def test_create_requirement_explicit_branch_kept(client, auth_headers, db_session, registered_user):
    """显式填写 req_branch → 原样使用(覆盖默认策略)"""
    project = await _setup_project(db_session, registered_user)

    with httpx.MockTransport(_gitlab_branch_handler([])):
        resp = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "用户登录功能", "description": "d", "req_branch": "feat/custom-login"},
        )
    data = resp.json()
    assert data["code"] == 0, data
    assert data["data"]["req_branch"] == "feat/custom-login"


@pytest.mark.asyncio
async def test_create_requirement_default_branch_conflict_suffix(client, auth_headers, db_session, registered_user):
    """同项目同日同名首拼撞分支 → 查重兜底生效(不撞 500)"""
    project = await _setup_project(db_session, registered_user)

    with httpx.MockTransport(_gitlab_branch_handler([])):
        r1 = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "用户登录功能", "description": "d1"},
        )
        r2 = await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json={"title": "用户登录功能", "description": "d2"},
        )
    d1, d2 = r1.json(), r2.json()
    assert d1["code"] == 0 and d2["code"] == 0, (d1, d2)
    assert d1["data"]["req_branch"] != d2["data"]["req_branch"]
